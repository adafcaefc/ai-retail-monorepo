"""Treasury cash-flow service — reads the `newdata` star schema.

get_baseline() reads newdata.fact_cashflow_weekly, newdata.fact_cashflow_lines
and newdata.fx_assumptions by raw SQL. Simulator caps use ABS() (outflows are
stored negative in newdata) and pick the deferrable payment by
commitment_type = 'Deferrable'. All arithmetic below get_baseline() is
unchanged from the pre-migration logic.
"""

from __future__ import annotations

from sqlalchemy import text

from src.llm.agents.common.tools.db import _latest_batch_id, _read_connection
from .models import (
    CashFlowBaselineResponse,
    CashFlowDriver,
    CashFlowSimulationRequest,
    CashFlowSimulationResponse,
    WeeklyCashPosition,
)

BATCH_NAME = "new_dataset"


class CashFlowDataError(RuntimeError):
    """Raised when a required forecast row is missing."""


def _week_number(label: object) -> int:
    """'W5' -> 5. The forecast keeps the week as text in newdata."""
    digits = "".join(ch for ch in str(label) if ch.isdigit())
    return int(digits) if digits else 0


def _fx_assumptions(connection) -> dict[str, float]:
    return {
        str(row["metric"]): float(row["value"] or 0)
        for row in connection.execute(
            text("SELECT metric, value FROM newdata.fx_assumptions")
        ).mappings()
    }


def get_baseline(session=None) -> CashFlowBaselineResponse:
    """The verified forecast, assumptions and drivers, read from newdata.

    `session` is accepted and ignored so callers that still pass one keep
    working; the read uses a bounded read-only connection instead.
    """
    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(connection, BATCH_NAME)

        weekly_rows = connection.execute(
            text(
                """
                SELECT week, opening_cash_idr_mn, closing_cash_idr_mn,
                       min_buffer_idr_mn, headroom_idr_mn, status
                FROM newdata.fact_cashflow_weekly
                """
            )
        ).mappings().all()

        weekly_positions = sorted(
            (
                WeeklyCashPosition(
                    week_number=_week_number(row["week"]),
                    opening_cash_idr_mn=float(row["opening_cash_idr_mn"] or 0),
                    closing_cash_idr_mn=float(row["closing_cash_idr_mn"] or 0),
                    minimum_buffer_idr_mn=float(row["min_buffer_idr_mn"] or 0),
                    headroom_idr_mn=float(row["headroom_idr_mn"] or 0),
                    status=str(row["status"] or "OK"),
                )
                for row in weekly_rows
            ),
            key=lambda p: p.week_number,
        )

        available = {p.week_number for p in weekly_positions}
        if not {5, 6, 7}.issubset(available):
            raise CashFlowDataError(
                "Week 5, Week 6, and Week 7 forecast rows must be available."
            )

        minimum_buffer = (
            weekly_positions[0].minimum_buffer_idr_mn if weekly_positions else 0.0
        )

        # Every FX figure is already computed on 43_FX_Assumptions.
        fx = _fx_assumptions(connection)
        spot = fx.get("Spot rate (IDR/USD)", 0.0)
        adverse = fx.get("Adverse scenario rate (IDR/USD)", 0.0)
        forward_points = fx.get("Forward points (IDR/USD)", 0.0)
        net_usd_exposure = fx.get("Net USD exposure (USD)", 0.0)
        recommended_hedge = fx.get("Recommended hedge (USD)", 0.0)
        forward_rate = spot + forward_points

        # Simulator caps. Outflows are stored NEGATIVE in newdata, so ABS() is
        # used both to sort and to return a positive cap. The deferrable
        # payment is the largest one tagged commitment_type = 'Deferrable'
        # (tax and other 'Committed' outflows cannot be deferred).
        accel = connection.execute(
            text(
                """
                SELECT reference, counterparty,
                       ABS(amount_idr_mn) AS amount_idr_mn, week
                FROM newdata.fact_cashflow_lines
                WHERE direction = 'Inflow'
                ORDER BY ABS(amount_idr_mn) DESC
                LIMIT 1
                """
            )
        ).mappings().first()

        defer = connection.execute(
            text(
                """
                SELECT reference, counterparty,
                       ABS(amount_idr_mn) AS amount_idr_mn, week
                FROM newdata.fact_cashflow_lines
                WHERE direction = 'Outflow'
                  AND commitment_type = 'Deferrable'
                ORDER BY ABS(amount_idr_mn) DESC
                LIMIT 1
                """
            )
        ).mappings().first()
        if defer is None:  # no deferrable line -> largest outflow as fallback
            defer = connection.execute(
                text(
                    """
                    SELECT reference, counterparty,
                           ABS(amount_idr_mn) AS amount_idr_mn, week
                    FROM newdata.fact_cashflow_lines
                    WHERE direction = 'Outflow'
                    ORDER BY ABS(amount_idr_mn) DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()

    customer_driver = CashFlowDriver(
        reference_number=str((accel or {}).get("reference") or "AR"),
        counterparty_name=str((accel or {}).get("counterparty") or "Top customer"),
        amount_idr_mn=float((accel or {}).get("amount_idr_mn") or 0),
        original_week=_week_number((accel or {}).get("week")) or None,
        expected_week=_week_number((accel or {}).get("week")) or None,
        description="Largest movable customer receipt (simulator cap).",
    )

    payment_driver = CashFlowDriver(
        reference_number=str((defer or {}).get("reference") or "AP"),
        counterparty_name=str((defer or {}).get("counterparty") or "Vendor"),
        amount_idr_mn=float((defer or {}).get("amount_idr_mn") or 0),
        payment_week=_week_number((defer or {}).get("week")) or None,
        is_deferrable=True,
        description="Largest deferrable vendor payment (simulator cap).",
    )

    return CashFlowBaselineResponse(
        import_batch_id=import_batch_id,
        workbook_name="new_dataset",
        workbook_version=None,
        weekly_positions=weekly_positions,
        minimum_buffer_idr_mn=minimum_buffer,
        net_usd_exposure=net_usd_exposure,
        recommended_hedge_usd=recommended_hedge,
        spot_rate_idr_per_usd=spot,
        forward_rate_idr_per_usd=forward_rate,
        adverse_rate_idr_per_usd=adverse,
        customer_delay_driver=customer_driver,
        deferrable_payment_driver=payment_driver,
    )


def get_week_position(
    baseline: CashFlowBaselineResponse,
    week_number: int,
) -> WeeklyCashPosition:
    for position in baseline.weekly_positions:
        if position.week_number == week_number:
            return position

    raise CashFlowDataError(
        f"Week {week_number} baseline is unavailable."
    )


def determine_status(
    week5_cash: float,
    week6_cash: float,
    week7_cash: float,
    minimum_buffer: float,
) -> str:
    if week5_cash < minimum_buffer:
        return "SHORTAGE"

    if week6_cash < minimum_buffer:
        return "WEEK 6 RISK"

    if week7_cash < minimum_buffer:
        return "WEEK 7 RISK"

    return "SAFE"


def build_recommendation(
    status: str,
    request: CashFlowSimulationRequest,
) -> str:
    if status == "SHORTAGE":
        return (
            "Week 5 remains below the minimum cash buffer. "
            "Increase accelerated collection, use a controlled "
            "credit-line draw, or evaluate the eligible payment "
            "deferral."
        )

    if status == "WEEK 6 RISK":
        return (
            "The Week 5 shortfall is resolved, but the payment "
            "deferral creates a Week 6 buffer breach. Reduce the "
            "deferral or add another Week 6 inflow."
        )

    if status == "WEEK 7 RISK":
        return (
            "The Week 5 shortfall is resolved, but too much cash "
            "has been pulled forward from Week 7. Reduce the "
            "accelerated collection amount."
        )

    if request.credit_line_draw_idr_mn > 0:
        return (
            "Liquidity remains above the minimum buffer across "
            "Weeks 5 to 7. Confirm interest cost and available "
            "facility headroom before approving the credit-line "
            "draw."
        )

    if request.defer_payment_idr_mn > 0:
        return (
            "Liquidity remains above the minimum buffer across "
            "Weeks 5 to 7. Confirm that the revised payment date "
            "remains within vendor terms."
        )

    return (
        "Liquidity remains above the minimum buffer across "
        "Weeks 5 to 7. Accelerated collection restores the Week 5 "
        "buffer without using debt or creating a later shortfall."
    )


def simulate(
    request: CashFlowSimulationRequest,
) -> CashFlowSimulationResponse:
    """Recalculate Weeks 5-7. get_baseline() manages its own connection."""
    return simulate_with_baseline(request, get_baseline())


def simulate_with_baseline(
    request: CashFlowSimulationRequest,
    baseline: CashFlowBaselineResponse,
) -> CashFlowSimulationResponse:
    week5 = get_week_position(baseline, 5)
    week6 = get_week_position(baseline, 6)
    week7 = get_week_position(baseline, 7)

    maximum_collection = baseline.customer_delay_driver.amount_idr_mn
    maximum_deferral = baseline.deferrable_payment_driver.amount_idr_mn

    if request.accelerate_collection_idr_mn > maximum_collection:
        raise ValueError(
            "Accelerated collection cannot exceed "
            f"IDR {maximum_collection:,.2f} million."
        )

    if request.defer_payment_idr_mn > maximum_deferral:
        raise ValueError(
            "Deferred payment cannot exceed "
            f"IDR {maximum_deferral:,.2f} million."
        )

    if request.hedge_usd > baseline.net_usd_exposure:
        raise ValueError(
            "Hedge amount cannot exceed the net USD exposure of "
            f"USD {baseline.net_usd_exposure:,.2f}."
        )

    week5_cash = (
        week5.closing_cash_idr_mn
        + request.accelerate_collection_idr_mn
        + request.defer_payment_idr_mn
        + request.credit_line_draw_idr_mn
    )
    week6_cash = week6.closing_cash_idr_mn - request.defer_payment_idr_mn
    week7_cash = week7.closing_cash_idr_mn - request.accelerate_collection_idr_mn

    minimum_buffer = baseline.minimum_buffer_idr_mn

    week5_headroom = week5_cash - minimum_buffer
    week6_headroom = week6_cash - minimum_buffer
    week7_headroom = week7_cash - minimum_buffer

    headrooms = [week5_headroom, week6_headroom, week7_headroom]
    weeks_below_buffer = sum(headroom < 0 for headroom in headrooms)

    status = determine_status(
        week5_cash, week6_cash, week7_cash, minimum_buffer
    )

    hedge_coverage = 0.0
    if baseline.net_usd_exposure > 0:
        hedge_coverage = (
            request.hedge_usd / baseline.net_usd_exposure * 100
        )

    adverse_rate_difference = (
        baseline.adverse_rate_idr_per_usd - baseline.spot_rate_idr_per_usd
    )
    forward_rate_difference = (
        baseline.forward_rate_idr_per_usd - baseline.spot_rate_idr_per_usd
    )

    downside_avoided = (
        request.hedge_usd * adverse_rate_difference / 1_000_000
    )
    forward_premium = (
        request.hedge_usd * forward_rate_difference / 1_000_000
    )
    residual_exposure = baseline.net_usd_exposure - request.hedge_usd

    warnings: list[str] = []
    if request.accelerate_collection_idr_mn > 0:
        warnings.append(
            "Accelerated collection depends on the customer agreeing to "
            "pay earlier."
        )
    if request.defer_payment_idr_mn > 0:
        warnings.append(
            "Payment deferral requires confirmation that the revised date "
            "remains within vendor terms."
        )
    if request.credit_line_draw_idr_mn > 0:
        warnings.append(
            "Credit-line utilization creates interest cost and uses "
            "committed facility headroom."
        )
    if request.hedge_usd > 0:
        warnings.append(
            "Forward pricing is indicative and must be refreshed with the "
            "treasury bank before execution."
        )

    assumptions = [
        "Accelerated collection moves cash from Week 7 into Week 5.",
        "Deferred vendor payment moves cash from Week 5 into Week 6.",
        "Credit-line draw increases Week 5 liquidity without including "
        "interest expense in this simulation.",
        "Forward hedge reduces FX exposure without immediate Week 5 cash "
        "outflow.",
        "Interest, fees and FX settlement timing are outside this "
        "simulation.",
    ]

    return CashFlowSimulationResponse(
        import_batch_id=baseline.import_batch_id,
        accelerate_collection_idr_mn=round(
            request.accelerate_collection_idr_mn, 2
        ),
        defer_payment_idr_mn=round(request.defer_payment_idr_mn, 2),
        credit_line_draw_idr_mn=round(request.credit_line_draw_idr_mn, 2),
        hedge_usd=round(request.hedge_usd, 2),
        week5_cash_idr_mn=round(week5_cash, 2),
        week6_cash_idr_mn=round(week6_cash, 2),
        week7_cash_idr_mn=round(week7_cash, 2),
        week5_headroom_idr_mn=round(week5_headroom, 2),
        week6_headroom_idr_mn=round(week6_headroom, 2),
        week7_headroom_idr_mn=round(week7_headroom, 2),
        minimum_buffer_idr_mn=round(minimum_buffer, 2),
        lowest_headroom_idr_mn=round(min(headrooms), 2),
        weeks_below_buffer=weeks_below_buffer,
        net_usd_exposure=round(baseline.net_usd_exposure, 2),
        residual_usd_exposure=round(residual_exposure, 2),
        hedge_coverage_pct=round(hedge_coverage, 2),
        fx_downside_avoided_idr_mn=round(downside_avoided, 2),
        forward_premium_idr_mn=round(forward_premium, 2),
        status=status,
        recommendation=build_recommendation(status, request),
        assumptions=assumptions,
        warnings=warnings,
    )
