from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.llm.agents.common.dashboard_blocks import _scoped_where
from src.llm.agents.common.tools.db import (
    _available_months,
    _latest_batch_id,
    _legal_entities,
    _read_connection,
    _rows,
)
from src.llm.agents.common.tools.scope import active_legal_entity_id, active_period

# Same twelve-month window Finance uses (to September 2026), read off the
# case's own month so leakage and performance cover the same span.
WINDOW_START = "2025-10-01"

BATCH_NAME = "new_dataset"

# Split/threshold flags are a control weakness, not lost cash, so they are
# excluded from the direct-loss bars. They are *not* excluded from at-risk:
# the dataset's 9,795 includes their 1,950, which is why a category chart's
# direct-loss bars can total less than the flagged card above it. The charts
# say so rather than hiding the gap.
_CONTROL_TYPES = {
    "split / threshold",
    "split/threshold",
    "split invoice",
    "split",
}

# Where each case's money stands is `leakage_status`, not `payment_status`.
# The two are different questions: payment_status is whether the invoice has
# been settled, leakage_status is whether the leaked cash was stopped, is
# clawable, or is gone. Splitting on payment_status put all 9,795 into
# "blocked" and left recoverable and lost at zero, because the dataset never
# marks a leakage case as paid -- see 50_Agent_KPIs, which states the split as
# 6,250 / 3,450 / 95.
_BLOCKED_STATUS = "blocked before payment"
_RECOVERABLE_STATUS = "paid - recoverable"
_LOST_STATUS = "lost - not recoverable"


def _is_direct_loss(leakage_type: str) -> bool:
    return str(leakage_type).strip().lower() not in _CONTROL_TYPES


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _summary_row(
    connection: Connection,
    window: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """One summary row in the shape `leakage.py` reads from `summary[0]`."""
    row = connection.execute(
        text(
            f"""
            SELECT
                COALESCE(SUM(leakage_amount_idr_mn), 0)  AS at_risk,
                COUNT(*)                                 AS flagged,
                COALESCE(SUM(leakage_amount_idr_mn) FILTER (
                    WHERE lower(leakage_status) = :blocked_status
                ), 0)                                    AS blocked,
                COALESCE(SUM(leakage_amount_idr_mn) FILTER (
                    WHERE lower(leakage_status) = :recoverable_status
                ), 0)                                    AS recoverable,
                COALESCE(SUM(leakage_amount_idr_mn) FILTER (
                    WHERE lower(leakage_status) = :lost_status
                ), 0)                                    AS lost
            FROM newdata.leakage_cases
            WHERE {window}
              AND leakage_type IS NOT NULL
            """
        ),
        {
            **params,
            "blocked_status": _BLOCKED_STATUS,
            "recoverable_status": _RECOVERABLE_STATUS,
            "lost_status": _LOST_STATUS,
        },
    ).mappings().one()

    at_risk = _num(row["at_risk"])
    blocked = _num(row["blocked"])
    recoverable = _num(row["recoverable"])
    # Read lost rather than inferring it from the remainder: a status the
    # dataset adds later would otherwise be silently counted as lost cash.
    lost = _num(row["lost"])

    # No "total protected" here on purpose. Blocked cash is certain, but the
    # recoverable half has not been clawed back yet, so any single protected
    # figure depends on a claw-back rate. That rate is a dashboard/simulator
    # assumption, and keeping it in one place is what stops the card and the
    # simulator disagreeing on the same screen. The four facts below are what
    # 50_Agent_KPIs states, and they partition at-risk exactly:
    #     blocked + recoverable + lost == at_risk
    return {
        "id": 1,
        "total_amount_at_risk_idr_mn": round(at_risk, 2),
        "items_flagged": int(row["flagged"]),
        "blocked_before_payment_idr_mn": round(blocked, 2),
        "recoverable_already_paid_idr_mn": round(recoverable, 2),
        "lost_this_cycle_idr_mn": round(lost, 2),
        "source_sheet": "61_Leakage_Cases",
    }


def _period(connection: Connection, window: str, params: dict[str, Any]) -> str:
    """The span these cases cover, read from the case month."""
    row = connection.execute(
        text(
            f"""
            SELECT MIN(month) AS first_month, MAX(month) AS last_month
            FROM newdata.leakage_cases
            WHERE {window}
            """
        ),
        params,
    ).mappings().one()
    first, last = row["first_month"], row["last_month"]
    if first is None or last is None:
        return "No period recorded"
    if first == last:
        return f"invoices scanned {first:%b %Y}"
    return f"invoices scanned {first:%b %Y} – {last:%b %Y}"


def get_payment_leakage_snapshot(
    legal_entity_id: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    """Return the latest bounded leakage summary, anomalies, and action data.

    `legal_entity_id` and `period`, when given, scope every query below to
    one entity and/or one month. `leakage_cases` and `fact_ap_invoices` both
    carry `legal_entity_id` and `month`, so this is a real slice of the
    ledger, not a client-side re-filter of an already aggregated total. Bound
    as query parameters, never spliced into the SQL text, since the values
    now arrive from an HTTP query string.

    No `category_group` parameter: `leakage_cases`/`fact_ap_invoices` carry
    no `category_id` — only `spend_category`, a different, AP-specific
    classification. See `_category_group_filter`'s docstring.

    Falls back to the live chat turn's scoped entity/period when called with
    no argument -- see common/tools/scope.py.
    """
    if legal_entity_id is None:
        legal_entity_id = active_legal_entity_id()
    if period is None:
        period = active_period()

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(connection, BATCH_NAME)
        window, params = _scoped_where(
            "month >= :window_start",
            {"window_start": WINDOW_START},
            legal_entity_id=legal_entity_id,
            month=period,
        )

        categories = _rows(
            connection,
            f"""
            SELECT
                leakage_type                       AS category_name,
                SUM(leakage_amount_idr_mn)         AS amount,
                COUNT(*)                           AS count
            FROM newdata.leakage_cases
            WHERE {window}
              AND leakage_type IS NOT NULL
            GROUP BY leakage_type
            ORDER BY SUM(leakage_amount_idr_mn) DESC
            """,
            params,
        )
        for row in categories:
            row["is_direct_loss"] = _is_direct_loss(row["category_name"])

        anomalies_where = f"{window} AND leakage_amount_idr_mn > 0"
        cases = _rows(
            connection,
            f"""
            SELECT
                vendor_name,
                leakage_type                       AS anomaly_type,
                leakage_amount_idr_mn              AS amount_at_risk_idr_mn,
                payment_status,
                leakage_status,
                bank_account_changed,
                approval_level
            FROM newdata.leakage_cases
            WHERE {anomalies_where}
            ORDER BY leakage_amount_idr_mn DESC
            LIMIT 40
            """,
            params,
        )

        # QC-054 kept: a real per-day series. `leakage_cases` carries only a
        # month, so the daily date comes from the AP invoice it joins to.
        # Aliased separately from `window` above: this query joins two tables,
        # so the bare column names in `window` would be ambiguous here.
        daily_window, daily_params = _scoped_where(
            "c.month >= :window_start",
            {"window_start": WINDOW_START},
            **{"c.legal_entity_id": legal_entity_id, "c.month": period},
        )
        daily = _rows(
            connection,
            f"""
            SELECT
                f.issue_date        AS on_date,
                c.leakage_type      AS anomaly_type,
                c.payment_status    AS payment_status,
                c.leakage_amount_idr_mn AS amount
            FROM newdata.leakage_cases c
            JOIN newdata.fact_ap_invoices f USING (ap_invoice_id)
            WHERE {daily_window}
              AND c.leakage_amount_idr_mn > 0
              AND f.issue_date IS NOT NULL
            ORDER BY f.issue_date
            """,
            daily_params,
        )

        return {
            "import_batch_id": import_batch_id,
            "period": _period(connection, window, params),
            "summary": [_summary_row(connection, window, params)],
            "category_breakdowns": categories,
            "anomalies": cases,
            "action_worklist": cases[:20],
            "daily_at_risk": daily,
            "legal_entity_id": legal_entity_id,
            "legal_entities": _legal_entities(connection),
            "period_value": period,
            "available_months": _available_months(
                connection,
                "leakage_cases",
                "month >= :window_start",
                {"window_start": WINDOW_START},
            ),
        }


TOOLS = {
    "get_payment_leakage_snapshot": get_payment_leakage_snapshot,
}


__all__ = ["TOOLS", "get_payment_leakage_snapshot"]
