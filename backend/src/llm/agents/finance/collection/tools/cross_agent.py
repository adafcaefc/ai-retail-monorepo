"""Cross-agent tool: collection recovery -> treasury buffer impact."""

from __future__ import annotations

from typing import Any

from src.llm.agents.finance.collection.tools.collection_data import (
    get_collections_snapshot,
)
from src.llm.agents.finance.treasury.cashflow.service import get_baseline


def simulate_collection_to_treasury(
    top_n: int = 5,
    week_number: int = 5,
    use_expected_recovery: bool = True,
) -> dict[str, Any]:
    """Estimate the treasury buffer impact if the top-N overdue customers pay.

    Pulls overdue from Collection and the weekly cash position from Treasury,
    both from the same `newdata` ledger, and returns the combined effect on
    the selected week's headroom.
    """
    # --- Collection side ---
    col = get_collections_snapshot()
    customers = col.get("customers") or []
    ranked = sorted(
        customers,
        key=lambda r: float(r.get("overdue_idr_mn") or 0),
        reverse=True,
    )[:top_n]

    gross_overdue = sum(float(r.get("overdue_idr_mn") or 0) for r in ranked)

    # expected recovery from worklist if available, else gross
    worklist = {w.get("customer_name"): w for w in (col.get("worklist") or [])}
    expected = 0.0
    for r in ranked:
        w = worklist.get(r.get("customer_name"))
        if w and w.get("expected_recovery_idr_mn") is not None:
            expected += float(w["expected_recovery_idr_mn"])
        else:
            expected += float(r.get("overdue_idr_mn") or 0)

    cash_injected = expected if use_expected_recovery else gross_overdue

    # --- Treasury side ---
    baseline = get_baseline().model_dump(mode="json")
    week = next(
        (w for w in baseline["weekly_positions"]
         if int(w["week_number"]) == week_number),
        None,
    )
    if week is None:
        raise ValueError(f"Week {week_number} not found in forecast.")

    buffer = float(baseline["minimum_buffer_idr_mn"])
    cash_before = float(week["closing_cash_idr_mn"])
    headroom_before = float(week["headroom_idr_mn"])

    cash_after = cash_before + cash_injected
    headroom_after = cash_after - buffer

    return {
        "week_number": week_number,
        "top_n": top_n,
        "collection": {
            "top_customers": [r.get("customer_name") for r in ranked],
            "gross_overdue_idr_mn": round(gross_overdue, 2),
            "expected_recovery_idr_mn": round(expected, 2),
            "cash_injected_idr_mn": round(cash_injected, 2),
        },
        "treasury": {
            "cash_before_idr_mn": round(cash_before, 2),
            "minimum_buffer_idr_mn": round(buffer, 2),
            "headroom_before_idr_mn": round(headroom_before, 2),
            "cash_after_idr_mn": round(cash_after, 2),
            "headroom_after_idr_mn": round(headroom_after, 2),
        },
        "buffer_safe_after": headroom_after >= 0,
        "assumption": (
            "Assumes the selected recovery lands in the chosen week. "
            "Uses expected_recovery (worklist) by default, not gross overdue."
        ),
    }


TOOLS = {
    "simulate_collection_to_treasury": simulate_collection_to_treasury,
}

__all__ = ["TOOLS", "simulate_collection_to_treasury"]