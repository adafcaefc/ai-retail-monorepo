"""Cross-agent tool: treasury shortfall -> collection priority list."""

from __future__ import annotations

from typing import Any

from src.llm.agents.finance.treasury.cashflow.service import get_baseline
from src.llm.agents.finance.collection.tools.collection_data import (
    get_collections_snapshot,
)


def prioritize_collection_for_week(
    week_number: int = 5,
) -> dict[str, Any]:
    """Rank overdue customers to close the selected week's buffer breach."""
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
    shortfall = max(0.0, buffer - cash_before)

    # --- Collection side ---
    col = get_collections_snapshot()
    customers = col.get("customers") or []
    worklist = {
        w.get("customer_name"): w for w in (col.get("worklist") or [])
    }

    ranked = sorted(
        (c for c in customers if float(c.get("overdue_idr_mn") or 0) > 0),
        key=lambda c: float(c.get("overdue_idr_mn") or 0),
        reverse=True,
    )

    priorities: list[dict[str, Any]] = []
    cumulative = 0.0
    covered_at_rank: int | None = None
    for rank, c in enumerate(ranked, start=1):
        name = c.get("customer_name")
        overdue = float(c.get("overdue_idr_mn") or 0)
        w = worklist.get(name)
        expected = (
            float(w["expected_recovery_idr_mn"])
            if w and w.get("expected_recovery_idr_mn") is not None
            else overdue
        )
        cumulative += expected
        priorities.append({
            "priority_rank": rank,
            "customer_name": name,
            "risk_tier": c.get("risk_tier"),
            "overdue_idr_mn": round(overdue, 2),
            "expected_recovery_idr_mn": round(expected, 2),
            "cumulative_recovery_idr_mn": round(cumulative, 2),
            "clears_shortfall": cumulative >= shortfall,
        })
        if covered_at_rank is None and cumulative >= shortfall:
            covered_at_rank = rank

    keep = max(covered_at_rank or len(priorities), 1)
    keep = min(max(keep, 5), 8)

    return {
        "week_number": week_number,
        "treasury": {
            "cash_before_idr_mn": round(cash_before, 2),
            "minimum_buffer_idr_mn": round(buffer, 2),
            "headroom_before_idr_mn": round(headroom_before, 2),
            "shortfall_idr_mn": round(shortfall, 2),
        },
        "customers_needed_to_clear": covered_at_rank,
        "priorities": priorities[:keep],
        "buffer_clears_with_top_n": covered_at_rank is not None,
        "assumption": (
            "Ranks by overdue size and uses expected recovery (worklist) where "
            "available. Assumes accelerated cash lands in the selected week. "
            "Acceleration mainly shifts timing and may reduce later-week "
            "inflows. Customer commitment is unconfirmed."
        ),
    }


TOOLS = {
    "prioritize_collection_for_week": prioritize_collection_for_week,
}

__all__ = ["TOOLS", "prioritize_collection_for_week"]