"""Collection (receivables) agent data tools, reading the `newdata` star schema.

The old `collections.*` tables held finished answers — `dso_cash_impact`,
`customer_credit_aging`, `risk_tier_exposure` were all pre-computed. `newdata`
keeps only `collection_worklist` finished; the DSO, the aging book and the
tier exposure are aggregated here from `fact_ar_invoices` + `dim_customer`,
the same way Finance aggregates its P&L from the sales facts.

The return contract is deliberately unchanged: `get_collections_snapshot`
still returns `summary`, `customers`, `risk_tiers` and `worklist` in the same
row shapes, `get_collections_monitoring_context` still adds `derived`, and
`calculate_collection_scenario` still returns the same keys, so `dashboard.py`
and the chat agent are untouched.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.llm.agents.common.tools.db import (
    _latest_batch_id,
    _read_connection,
    _rows,
)

BATCH_NAME = "new_dataset"

# Trailing-twelve-month window for the credit-sales denominator, matching the
# Finance window (to September 2026). AR balances are NOT windowed — an open
# invoice is outstanding whatever month it was issued.
SALES_WINDOW = "month >= '2025-10-01'"

# Illustrative target, same figure the old workbook carried on
# `04 DSO & Cash Impact`. Confirm against the client's own benchmark.
TARGET_DSO_DAYS = 47.0

# Illustrative ECL proxy on the high-risk tier, same rate as the old workbook.
HIGH_RISK_LOSS_RATE = 0.5

# Open = not settled. Verify the exact spelling of the paid status if a tier
# ever reads empty; everything here keys off "not paid".
_OPEN_PREDICATE = "UPPER(status) <> 'PAID'"


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _share(part: float, whole: float) -> float:
    return round(part / whole * 100, 2) if whole else 0.0


def _annual_credit_sales(connection: Connection) -> float:
    row = connection.execute(
        text(
            f"""
            SELECT COALESCE(SUM(net_revenue_idr_mn), 0) AS sales
            FROM newdata.fact_sales
            WHERE {SALES_WINDOW}
            """
        )
    ).mappings().one()
    return _number(row["sales"])


def _customer_rows(connection: Connection) -> list[dict[str, Any]]:
    """The receivables book per customer, aged from `days_past_due`.

    Buckets are derived from `days_past_due` rather than the stored
    `aging_bucket` string so the split is robust to label spelling. Balance is
    the open invoice amount; paid invoices drop out.
    """
    return _rows(
        connection,
        f"""
        SELECT
            a.customer_id,
            a.customer_name,
            c.segment                              AS customer_segment,
            c.payment_terms_days                   AS payment_terms,
            c.on_time_payment_pct                  AS on_time_percentage,
            c.credit_limit_idr_mn                  AS credit_limit_idr_mn,
            COALESCE(a.risk_tier, c.risk_tier)     AS risk_tier,
            MAX(a.days_past_due)                    AS days_beyond_terms,
            BOOL_OR(a.status ILIKE '%dispute%')     AS has_dispute,
            SUM(a.invoice_amount_idr_mn)           AS total_ar_idr_mn,
            SUM(a.invoice_amount_idr_mn) FILTER (
                WHERE a.days_past_due <= 0)         AS current_idr_mn,
            SUM(a.invoice_amount_idr_mn) FILTER (
                WHERE a.days_past_due BETWEEN 1 AND 30)  AS overdue_1_30_idr_mn,
            SUM(a.invoice_amount_idr_mn) FILTER (
                WHERE a.days_past_due BETWEEN 31 AND 60) AS overdue_31_60_idr_mn,
            SUM(a.invoice_amount_idr_mn) FILTER (
                WHERE a.days_past_due BETWEEN 61 AND 90) AS overdue_61_90_idr_mn,
            SUM(a.invoice_amount_idr_mn) FILTER (
                WHERE a.days_past_due > 90)         AS overdue_90_plus_idr_mn,
            SUM(a.invoice_amount_idr_mn) FILTER (
                WHERE a.days_past_due > 0)          AS overdue_idr_mn
        FROM newdata.fact_ar_invoices a
        LEFT JOIN newdata.dim_customer c USING (customer_id)
        WHERE {_OPEN_PREDICATE}
        GROUP BY a.customer_id, a.customer_name, c.segment,
                 c.payment_terms_days, c.on_time_payment_pct,
                 c.credit_limit_idr_mn, COALESCE(a.risk_tier, c.risk_tier)
        HAVING SUM(a.invoice_amount_idr_mn) > 0
        ORDER BY SUM(a.invoice_amount_idr_mn) FILTER (
            WHERE a.days_past_due > 0) DESC NULLS LAST, a.customer_name
        """,
        {},
    )


def _finalise_customer(row: dict[str, Any]) -> dict[str, Any]:
    total = _number(row.get("total_ar_idr_mn"))
    overdue = _number(row.get("overdue_idr_mn"))
    limit = _number(row.get("credit_limit_idr_mn"))
    row["overdue_percentage"] = round(overdue / total, 6) if total else 0.0
    row["credit_utilization"] = round(total / limit, 6) if limit else 0.0
    row["payment_trend"] = row.get("payment_trend") or None
    return row


def get_collections_snapshot() -> dict[str, Any]:
    """Return the latest exact collections, DSO, aging, risk, and worklist data."""

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(connection, BATCH_NAME)

        customers = [_finalise_customer(row) for row in _customer_rows(connection)]

        total_ar = sum(_number(r.get("total_ar_idr_mn")) for r in customers)
        current_ar = sum(_number(r.get("current_idr_mn")) for r in customers)
        overdue_ar = sum(_number(r.get("overdue_idr_mn")) for r in customers)

        annual_sales = _annual_credit_sales(connection)
        daily_sales = annual_sales / 365.0 if annual_sales else 0.0
        current_dso = total_ar / daily_sales if daily_sales else 0.0
        dso_gap = current_dso - TARGET_DSO_DAYS
        cash_freed = dso_gap * daily_sales if daily_sales else 0.0

        # Tier exposure, aggregated from the same customer rows.
        tiers: dict[str, dict[str, float]] = {}
        for row in customers:
            tier = str(row.get("risk_tier") or "Unrated")
            bucket = tiers.setdefault(tier, {"count": 0, "exposure": 0.0})
            bucket["count"] += 1
            bucket["exposure"] += _number(row.get("total_ar_idr_mn"))

        risk_tiers = [
            {
                "risk_tier": tier,
                "customer_count": int(data["count"]),
                "exposure_idr_mn": round(data["exposure"], 2),
                "percentage_of_ar": round(data["exposure"] / total_ar, 6)
                if total_ar
                else 0.0,
                "notes": None,
            }
            for tier, data in sorted(
                tiers.items(), key=lambda kv: kv[1]["exposure"], reverse=True
            )
        ]

        high_exposure = sum(
            data["exposure"]
            for tier, data in tiers.items()
            if tier.lower() == "high"
        )
        provision = round(high_exposure * HIGH_RISK_LOSS_RATE, 2)

        summary = {
            "total_ar_idr_mn": round(total_ar, 2),
            "current_ar_idr_mn": round(current_ar, 2),
            "overdue_ar_idr_mn": round(overdue_ar, 2),
            "overdue_percentage": round(overdue_ar / total_ar, 6)
            if total_ar
            else 0.0,
            "annual_credit_sales_idr_mn": round(annual_sales, 2),
            "daily_credit_sales_idr_mn": round(daily_sales, 8),
            "current_dso_days": round(current_dso, 6),
            "target_dso_days": TARGET_DSO_DAYS,
            "dso_gap_days": round(dso_gap, 6),
            "cash_freed_at_target_idr_mn": round(cash_freed, 8),
            "high_risk_provision_idr_mn": provision,
        }

        # The worklist is the one collections table that ships finished.
        worklist = _rows(
            connection,
            """
            SELECT
                priority_rank,
                customer_name,
                risk_tier,
                overdue_idr_mn,
                expected_recovery_idr_mn,
                oldest_dpd,
                open_invoices,
                dso_days_released
            FROM newdata.collection_worklist
            ORDER BY priority_rank
            LIMIT 20
            """,
            {},
        )
        # Backfill the two names the old worklist carried that this table
        # does not, so the dashboard's column reads still resolve.
        for row in worklist:
            row["oldest_aging_bucket"] = row.get("oldest_dpd")
            row.setdefault("risk_score", None)
            row.setdefault("recommended_action", None)
            row.setdefault("recovery_percentage", None)

        return {
            "import_batch_id": import_batch_id,
            "period": (
                f"AR ageing snapshot · DSO on a 365-day basis "
                f"({round(current_dso, 1)} days)"
            ),
            "summary": summary,
            "customers": customers[:25],
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


def _collections_derived(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Precompute the monitoring aggregates, from the snapshot rows only."""
    customers = snapshot.get("customers") or []
    worklist = snapshot.get("worklist") or []
    summary = snapshot.get("summary") or {}

    total_overdue = sum(_number(r.get("overdue_idr_mn")) for r in customers)
    ranked = sorted(
        customers,
        key=lambda r: _number(r.get("overdue_idr_mn")),
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
            sum(_number(r.get("overdue_idr_mn")) for r in ranked[:count]),
            total_overdue,
        )

    aging_totals = {
        label: round(sum(_number(r.get(col)) for r in customers), 2)
        for label, col in _AGING_BUCKETS
    }
    aging_totals["overdue_61_plus"] = round(
        aging_totals["overdue_61_90"] + aging_totals["overdue_90_plus"], 2
    )

    utilization = sorted(
        (
            {
                "customer_name": r.get("customer_name"),
                "credit_limit_idr_mn": round(
                    _number(r.get("credit_limit_idr_mn")), 2
                ),
                "total_ar_idr_mn": round(_number(r.get("total_ar_idr_mn")), 2),
                "credit_utilization": r.get("credit_utilization"),
                "headroom_idr_mn": round(
                    _number(r.get("credit_limit_idr_mn"))
                    - _number(r.get("total_ar_idr_mn")),
                    2,
                ),
                "payment_trend": r.get("payment_trend"),
            }
            for r in customers
            if _number(r.get("credit_limit_idr_mn")) > 0
        ),
        key=lambda r: _number(r.get("credit_utilization")),
        reverse=True,
    )

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
            sum(_number(r.get("expected_recovery_idr_mn")) for r in worklist), 2
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
        import_batch_id = _latest_batch_id(connection, BATCH_NAME)

        customer = connection.execute(
            text(
                f"""
                SELECT
                    customer_id,
                    MAX(customer_name) AS customer_name,
                    SUM(invoice_amount_idr_mn) AS total_ar_idr_mn,
                    SUM(invoice_amount_idr_mn) FILTER (
                        WHERE days_past_due > 0) AS overdue_idr_mn
                FROM newdata.fact_ar_invoices
                WHERE {_OPEN_PREDICATE}
                  AND lower(customer_name) LIKE '%' || lower(:name) || '%'
                GROUP BY customer_id
                ORDER BY
                    CASE WHEN lower(MAX(customer_name)) = lower(:name)
                         THEN 0 ELSE 1 END,
                    SUM(invoice_amount_idr_mn) FILTER (
                        WHERE days_past_due > 0) DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"name": customer_name.strip()},
        ).mappings().one_or_none()
        if customer is None:
            raise ValueError(f"Customer was not found: {customer_name}")

        overdue_before = Decimal(str(_number(customer["overdue_idr_mn"])))
        if amount > overdue_before:
            raise ValueError(
                "Requested collection exceeds the customer's overdue balance "
                f"of IDR {overdue_before:,.2f} million."
            )

        book = connection.execute(
            text(
                f"""
                SELECT COALESCE(SUM(invoice_amount_idr_mn), 0) AS total_ar
                FROM newdata.fact_ar_invoices
                WHERE {_OPEN_PREDICATE}
                """
            )
        ).mappings().one()
        annual_sales = _annual_credit_sales(connection)

    total_ar_before = Decimal(str(_number(book["total_ar"])))
    daily_credit_sales = Decimal(str(annual_sales / 365.0)) if annual_sales else Decimal("0")
    total_ar_after = total_ar_before - amount
    dso_before = (
        total_ar_before / daily_credit_sales if daily_credit_sales else Decimal("0")
    )
    dso_after = (
        total_ar_after / daily_credit_sales if daily_credit_sales else Decimal("0")
    )
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
