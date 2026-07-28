"""Collection (receivables) agent data tools."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text

from src.llm.agents.common.tools.db import (
    _latest_batch_id,
    _read_connection,
    _rows,
)


def get_collections_snapshot() -> dict[str, Any]:
    """Return the latest exact collections, DSO, aging, risk, and worklist data."""

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(
            connection,
            "collections_credit_agent",
        )
        parameters = {"import_batch_id": import_batch_id}
        summary = _rows(
            connection,
            """
            SELECT total_ar_idr_mn, current_ar_idr_mn, overdue_ar_idr_mn,
                   overdue_percentage, annual_credit_sales_idr_mn,
                   daily_credit_sales_idr_mn, current_dso_days,
                   target_dso_days, dso_gap_days,
                   cash_freed_at_target_idr_mn,
                   high_risk_provision_idr_mn
            FROM collections.dso_cash_impact
            WHERE import_batch_id = :import_batch_id
            """,
            parameters,
        )
        customers = _rows(
            connection,
            """
            SELECT customer_id, customer_name, customer_segment,
                   payment_terms, days_beyond_terms, payment_trend,
                   has_dispute, on_time_percentage, total_ar_idr_mn,
                   overdue_idr_mn, overdue_percentage,
                   current_idr_mn,
                   overdue_1_30_idr_mn, overdue_31_60_idr_mn,
                   overdue_61_90_idr_mn, overdue_90_plus_idr_mn,
                   credit_limit_idr_mn, credit_utilization
            FROM collections.customer_credit_aging
            WHERE import_batch_id = :import_batch_id
            ORDER BY overdue_idr_mn DESC, customer_name
            LIMIT 25
            """,
            parameters,
        )
        risk_tiers = _rows(
            connection,
            """
            SELECT risk_tier, customer_count, exposure_idr_mn,
                   percentage_of_ar, notes
            FROM collections.risk_tier_exposure
            WHERE import_batch_id = :import_batch_id
            ORDER BY exposure_idr_mn DESC
            """,
            parameters,
        )
        worklist = _rows(
            connection,
            """
            SELECT priority_rank, customer_name, overdue_idr_mn,
                   oldest_aging_bucket, risk_tier, risk_score,
                   recommended_action, recovery_percentage,
                   expected_recovery_idr_mn
            FROM collections.worklist
            WHERE import_batch_id = :import_batch_id
            ORDER BY priority_rank
            LIMIT 20
            """,
            parameters,
        )
        return {
            "import_batch_id": import_batch_id,
            "summary": summary[0] if summary else {},
            "customers": customers,
            "risk_tiers": risk_tiers,
            "worklist": worklist,
        }


_AGING_BUCKETS = (
    ("current", "current_idr_mn"),
    ("overdue_1_30", "overdue_1_30_idr_mn"),
    ("overdue_31_60", "overdue_31_60_idr_mn"),
    ("overdue_61_90", "overdue_61_90_idr_mn"),
    ("overdue_90_plus", "overdue_90_plus_idr_mn"),
)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _share(part: float, whole: float) -> float:
    return round(part / whole * 100, 2) if whole else 0.0


def _collections_derived(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Precompute the aggregates the monitoring passes used to query for.

    Every value here comes from rows already in the snapshot, so this costs no
    extra database round trips. Each pass that reads these instead of calling a
    tool saves a full model round trip.
    """
    customers = snapshot.get("customers") or []
    worklist = snapshot.get("worklist") or []
    summary = snapshot.get("summary") or {}

    total_overdue = sum(
        _number(row.get("overdue_idr_mn")) for row in customers
    )
    ranked = sorted(
        customers,
        key=lambda row: _number(row.get("overdue_idr_mn")),
        reverse=True,
    )

    concentration: list[dict[str, Any]] = []
    running = 0.0
    for rank, row in enumerate(ranked, start=1):
        overdue = _number(row.get("overdue_idr_mn"))
        if overdue <= 0:
            continue
        running += overdue
        concentration.append(
            {
                "rank": rank,
                "customer_name": row.get("customer_name"),
                "overdue_idr_mn": round(overdue, 2),
                "share_pct": _share(overdue, total_overdue),
                "cumulative_share_pct": _share(running, total_overdue),
                "payment_trend": row.get("payment_trend"),
                "has_dispute": row.get("has_dispute"),
            }
        )

    def _top_share(count: int) -> float:
        return _share(
            sum(
                _number(row.get("overdue_idr_mn"))
                for row in ranked[:count]
            ),
            total_overdue,
        )

    aging_totals = {
        label: round(
            sum(_number(row.get(column)) for row in customers), 2
        )
        for label, column in _AGING_BUCKETS
    }
    aging_totals["overdue_61_plus"] = round(
        aging_totals["overdue_61_90"] + aging_totals["overdue_90_plus"], 2
    )

    utilization = sorted(
        (
            {
                "customer_name": row.get("customer_name"),
                "credit_limit_idr_mn": round(
                    _number(row.get("credit_limit_idr_mn")), 2
                ),
                "total_ar_idr_mn": round(
                    _number(row.get("total_ar_idr_mn")), 2
                ),
                "credit_utilization": row.get("credit_utilization"),
                "headroom_idr_mn": round(
                    _number(row.get("credit_limit_idr_mn"))
                    - _number(row.get("total_ar_idr_mn")),
                    2,
                ),
                "payment_trend": row.get("payment_trend"),
            }
            for row in customers
            if _number(row.get("credit_limit_idr_mn")) > 0
        ),
        key=lambda row: _number(row.get("credit_utilization")),
        reverse=True,
    )

    # Same arithmetic as calculate_collection_scenario, precomputed for the
    # largest overdue balances at 0% and 1% so a pass can cite an outcome
    # without spending a tool call.
    total_ar = _number(summary.get("total_ar_idr_mn"))
    daily_sales = _number(summary.get("daily_credit_sales_idr_mn"))
    dso_before = _number(summary.get("current_dso_days"))
    scenarios: list[dict[str, Any]] = []
    for row in ranked[:5]:
        overdue = _number(row.get("overdue_idr_mn"))
        if overdue <= 0 or daily_sales <= 0:
            continue
        dso_after = (total_ar - overdue) / daily_sales
        scenarios.append(
            {
                "customer_name": row.get("customer_name"),
                "cash_collected_idr_mn": round(overdue, 2),
                "discount_cost_at_1pct_idr_mn": round(overdue * 0.01, 2),
                "dso_before_days": round(dso_before, 2),
                "dso_after_days": round(dso_after, 2),
                "dso_change_days": round(dso_after - dso_before, 2),
            }
        )

    return {
        "note": (
            "Precomputed from the snapshot rows below. Full-balance collection "
            "assumed for each scenario; customer acceptance is unverified."
        ),
        "total_overdue_idr_mn": round(total_overdue, 2),
        "top_1_overdue_share_pct": _top_share(1),
        "top_2_overdue_share_pct": _top_share(2),
        "top_3_overdue_share_pct": _top_share(3),
        "top_5_overdue_share_pct": _top_share(5),
        "overdue_by_customer": concentration,
        "portfolio_aging_idr_mn": aging_totals,
        "credit_utilization_ranked": utilization,
        "settlement_scenarios": scenarios,
        "expected_recovery_total_idr_mn": round(
            sum(
                _number(row.get("expected_recovery_idr_mn"))
                for row in worklist
            ),
            2,
        ),
    }


def get_collections_monitoring_context() -> dict[str, Any]:
    """Return the collections snapshot plus precomputed monitoring aggregates."""

    snapshot = get_collections_snapshot()
    return {**snapshot, "derived": _collections_derived(snapshot)}


def calculate_collection_scenario(
    customer_name: str,
    cash_to_collect_idr_mn: float,
    discount_pct: float = 0,
) -> dict[str, Any]:
    """Calculate exact cash, discount cost, customer overdue, and portfolio DSO."""

    if not customer_name.strip():
        raise ValueError("customer_name must not be empty.")
    amount = Decimal(str(cash_to_collect_idr_mn))
    discount = Decimal(str(discount_pct))
    if not amount.is_finite() or amount <= 0:
        raise ValueError("cash_to_collect_idr_mn must be greater than zero.")
    if not discount.is_finite() or discount < 0 or discount > 100:
        raise ValueError("discount_pct must be between 0 and 100.")

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(
            connection,
            "collections_credit_agent",
        )
        customer = connection.execute(
            text(
                """
                SELECT customer_id, customer_name, total_ar_idr_mn,
                       overdue_idr_mn
                FROM collections.customer_credit_aging
                WHERE import_batch_id = :import_batch_id
                  AND lower(customer_name) LIKE '%' || lower(:customer_name) || '%'
                ORDER BY
                    CASE WHEN lower(customer_name) = lower(:customer_name)
                         THEN 0 ELSE 1 END,
                    overdue_idr_mn DESC
                LIMIT 1
                """
            ),
            {
                "import_batch_id": import_batch_id,
                "customer_name": customer_name.strip(),
            },
        ).mappings().one_or_none()
        if customer is None:
            raise ValueError(f"Customer was not found: {customer_name}")

        overdue_before = Decimal(customer["overdue_idr_mn"])
        if amount > overdue_before:
            raise ValueError(
                "Requested collection exceeds the customer's overdue balance "
                f"of IDR {overdue_before:,.2f} million."
            )

        portfolio = connection.execute(
            text(
                """
                SELECT total_ar_idr_mn, daily_credit_sales_idr_mn,
                       current_dso_days
                FROM collections.dso_cash_impact
                WHERE import_batch_id = :import_batch_id
                """
            ),
            {"import_batch_id": import_batch_id},
        ).mappings().one()

    total_ar_before = Decimal(portfolio["total_ar_idr_mn"])
    daily_credit_sales = Decimal(portfolio["daily_credit_sales_idr_mn"])
    total_ar_after = total_ar_before - amount
    dso_before = Decimal(portfolio["current_dso_days"])
    dso_after = total_ar_after / daily_credit_sales
    discount_cost = amount * discount / Decimal("100")

    return {
        "import_batch_id": import_batch_id,
        "customer_id": customer["customer_id"],
        "customer_name": customer["customer_name"],
        "cash_collected_idr_mn": round(float(amount), 2),
        "discount_pct": round(float(discount), 4),
        "discount_cost_idr_mn": round(float(discount_cost), 2),
        "customer_overdue_before_idr_mn": round(float(overdue_before), 2),
        "customer_overdue_after_idr_mn": round(float(overdue_before - amount), 2),
        "total_ar_before_idr_mn": round(float(total_ar_before), 2),
        "total_ar_after_idr_mn": round(float(total_ar_after), 2),
        "dso_before_days": round(float(dso_before), 2),
        "dso_after_days": round(float(dso_after), 2),
        "dso_change_days": round(float(dso_after - dso_before), 2),
        "assumption": (
            "The requested gross cash amount is received and total AR falls "
            "by the same amount. Customer acceptance requires verification."
        ),
    }


TOOLS = {
    "get_collections_snapshot": get_collections_snapshot,
    "get_collections_monitoring_context": get_collections_monitoring_context,
    "calculate_collection_scenario": calculate_collection_scenario,
}


__all__ = [
    "TOOLS",
    "get_collections_snapshot",
    "get_collections_monitoring_context",
    "calculate_collection_scenario",
]
