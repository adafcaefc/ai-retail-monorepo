from __future__ import annotations

from src.cashflow import repository
from src.cashflow.models import (
    CashFlowBaselineResponse,
    CashFlowDriver,
    CashFlowSimulationRequest,
    CashFlowSimulationResponse,
    WeeklyCashPosition,
)


def get_baseline() -> CashFlowBaselineResponse:
    import_batch = repository.get_latest_import_batch()
    import_batch_id = int(import_batch["id"])

    weekly_rows = repository.get_weekly_positions(
        import_batch_id
    )

    weekly_positions = [
        WeeklyCashPosition(
            week_number=int(row["week_number"]),
            opening_cash_idr_mn=float(
                row["opening_cash_idr_mn"]
            ),
            closing_cash_idr_mn=float(
                row["closing_cash_idr_mn"]
            ),
            minimum_buffer_idr_mn=float(
                row["minimum_buffer_idr_mn"]
            ),
            headroom_idr_mn=float(
                row["headroom_idr_mn"]
            ),
            status=str(row["status"]),
        )
        for row in weekly_rows
    ]

    minimum_buffer = repository.get_numeric_assumption(
        import_batch_id,
        "Minimum cash buffer (IDR mn)",
    )

    spot_rate = repository.get_numeric_assumption(
        import_batch_id,
        "Spot USD/IDR",
    )

    forward_rate = repository.get_numeric_assumption(
        import_batch_id,
        "13-week forward USD/IDR",
    )

    adverse_rate = repository.get_numeric_assumption(
        import_batch_id,
        "Adverse rate  = spot x (1+adverse)",
    )

    net_usd_exposure = repository.get_net_usd_exposure(
        import_batch_id
    )

    customer_driver_row = (
        repository.get_customer_delay_driver(
            import_batch_id
        )
    )

    payment_driver_row = (
        repository.get_deferrable_payment_driver(
            import_batch_id
        )
    )

    return CashFlowBaselineResponse(
        import_batch_id=import_batch_id,
        workbook_name=str(import_batch["workbook_name"]),
        workbook_version=import_batch.get(
            "workbook_version"
        ),
        weekly_positions=weekly_positions,
        minimum_buffer_idr_mn=minimum_buffer,
        net_usd_exposure=net_usd_exposure,
        recommended_hedge_usd=2_000_000.0,
        spot_rate_idr_per_usd=spot_rate,
        forward_rate_idr_per_usd=forward_rate,
        adverse_rate_idr_per_usd=adverse_rate,
        customer_delay_driver=CashFlowDriver(
            reference_number=str(
                customer_driver_row["reference_number"]
            ),
            counterparty_name=str(
                customer_driver_row["counterparty_name"]
            ),
            amount_idr_mn=float(
                customer_driver_row["amount_idr_mn"]
            ),
            original_week=int(
                customer_driver_row["original_week"]
            ),
            expected_week=int(
                customer_driver_row["expected_week"]
            ),
            description=customer_driver_row.get(
                "description"
            ),
        ),
        deferrable_payment_driver=CashFlowDriver(
            reference_number=str(
                payment_driver_row["reference_number"]
            ),
            counterparty_name=str(
                payment_driver_row["counterparty_name"]
            ),
            amount_idr_mn=float(
                payment_driver_row["amount_idr_mn"]
            ),
            payment_week=int(
                payment_driver_row["payment_week"]
            ),
            is_deferrable=bool(
                payment_driver_row["is_deferrable"]
            ),
            description=payment_driver_row.get(
                "description"
            ),
        ),
    )


def get_week_position(
    baseline: CashFlowBaselineResponse,
    week_number: int,
) -> WeeklyCashPosition:
    for position in baseline.weekly_positions:
        if position.week_number == week_number:
            return position

    raise repository.CashFlowDataError(
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
    baseline = get_baseline()

    week5 = get_week_position(baseline, 5)
    week6 = get_week_position(baseline, 6)
    week7 = get_week_position(baseline, 7)

    maximum_collection = (
        baseline.customer_delay_driver.amount_idr_mn
    )

    maximum_deferral = (
        baseline.deferrable_payment_driver.amount_idr_mn
    )

    if (
        request.accelerate_collection_idr_mn
        > maximum_collection
    ):
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

    week6_cash = (
        week6.closing_cash_idr_mn
        - request.defer_payment_idr_mn
    )

    week7_cash = (
        week7.closing_cash_idr_mn
        - request.accelerate_collection_idr_mn
    )

    minimum_buffer = baseline.minimum_buffer_idr_mn

    week5_headroom = week5_cash - minimum_buffer
    week6_headroom = week6_cash - minimum_buffer
    week7_headroom = week7_cash - minimum_buffer

    headrooms = [
        week5_headroom,
        week6_headroom,
        week7_headroom,
    ]

    weeks_below_buffer = sum(
        headroom < 0
        for headroom in headrooms
    )

    status = determine_status(
        week5_cash,
        week6_cash,
        week7_cash,
        minimum_buffer,
    )

    hedge_coverage = 0.0

    if baseline.net_usd_exposure > 0:
        hedge_coverage = (
            request.hedge_usd
            / baseline.net_usd_exposure
            * 100
        )

    adverse_rate_difference = (
        baseline.adverse_rate_idr_per_usd
        - baseline.spot_rate_idr_per_usd
    )

    forward_rate_difference = (
        baseline.forward_rate_idr_per_usd
        - baseline.spot_rate_idr_per_usd
    )

    downside_avoided = (
        request.hedge_usd
        * adverse_rate_difference
        / 1_000_000
    )

    forward_premium = (
        request.hedge_usd
        * forward_rate_difference
        / 1_000_000
    )

    residual_exposure = (
        baseline.net_usd_exposure
        - request.hedge_usd
    )

    warnings: list[str] = []

    if request.accelerate_collection_idr_mn > 0:
        warnings.append(
            "Accelerated collection depends on Customer A "
            "agreeing to pay earlier."
        )

    if request.defer_payment_idr_mn > 0:
        warnings.append(
            "Payment deferral requires confirmation that the "
            "revised date remains within vendor terms."
        )

    if request.credit_line_draw_idr_mn > 0:
        warnings.append(
            "Credit-line utilization creates interest cost and "
            "uses committed facility headroom."
        )

    if request.hedge_usd > 0:
        warnings.append(
            "Forward pricing is illustrative and must be refreshed "
            "with the treasury bank before execution."
        )

    assumptions = [
        (
            "Accelerated collection moves cash from Week 7 "
            "into Week 5."
        ),
        (
            "Deferred vendor payment moves cash from Week 5 "
            "into Week 6."
        ),
        (
            "Credit-line draw increases Week 5 liquidity without "
            "including interest expense in this simulation."
        ),
        (
            "Forward hedge reduces FX exposure without immediate "
            "Week 5 cash outflow."
        ),
        "All values are illustrative demo data.",
    ]

    return CashFlowSimulationResponse(
        import_batch_id=baseline.import_batch_id,
        accelerate_collection_idr_mn=round(
            request.accelerate_collection_idr_mn,
            2,
        ),
        defer_payment_idr_mn=round(
            request.defer_payment_idr_mn,
            2,
        ),
        credit_line_draw_idr_mn=round(
            request.credit_line_draw_idr_mn,
            2,
        ),
        hedge_usd=round(request.hedge_usd, 2),
        week5_cash_idr_mn=round(week5_cash, 2),
        week6_cash_idr_mn=round(week6_cash, 2),
        week7_cash_idr_mn=round(week7_cash, 2),
        week5_headroom_idr_mn=round(
            week5_headroom,
            2,
        ),
        week6_headroom_idr_mn=round(
            week6_headroom,
            2,
        ),
        week7_headroom_idr_mn=round(
            week7_headroom,
            2,
        ),
        minimum_buffer_idr_mn=round(
            minimum_buffer,
            2,
        ),
        lowest_headroom_idr_mn=round(
            min(headrooms),
            2,
        ),
        weeks_below_buffer=weeks_below_buffer,
        net_usd_exposure=round(
            baseline.net_usd_exposure,
            2,
        ),
        residual_usd_exposure=round(
            residual_exposure,
            2,
        ),
        hedge_coverage_pct=round(
            hedge_coverage,
            2,
        ),
        fx_downside_avoided_idr_mn=round(
            downside_avoided,
            2,
        ),
        forward_premium_idr_mn=round(
            forward_premium,
            2,
        ),
        status=status,
        recommendation=build_recommendation(
            status,
            request,
        ),
        assumptions=assumptions,
        warnings=warnings,
    )