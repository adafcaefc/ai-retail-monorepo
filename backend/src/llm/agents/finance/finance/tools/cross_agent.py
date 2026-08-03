"""Cross-agent tool: finance revenue shock -> treasury cash impact."""

from __future__ import annotations

from typing import Any

from src.llm.agents.finance.finance.tools.performance_data import (
    get_financial_performance_snapshot,
)
from src.llm.agents.finance.treasury.cashflow.service import get_baseline


def _kpi(fin: dict[str, Any], name: str) -> float:
    for row in fin.get("kpis") or []:
        if str(row.get("metric_name")) == name:
            return float(row.get("actual_value") or 0)
    return 0.0


def simulate_revenue_drop_to_cash(
    revenue_drop_pct: float = 10.0,
    week_number: int = 5,
) -> dict[str, Any]:
    """Estimate the treasury cash impact of a revenue drop."""
    if revenue_drop_pct <= 0 or revenue_drop_pct > 100:
        raise ValueError("revenue_drop_pct must be between 0 and 100.")

    # --- Finance side ---
    fin = get_financial_performance_snapshot()
    revenue = _kpi(fin, "Revenue (IDR mn)")
    gross_margin = _kpi(fin, "Gross margin (IDR mn)")
    ebitda_before = _kpi(fin, "EBITDA (IDR mn)")

    gm_pct = (gross_margin / revenue) if revenue else 0.0
    revenue_lost = revenue * revenue_drop_pct / 100.0
    ebitda_hit = revenue_lost * gm_pct
    ebitda_after = ebitda_before - ebitda_hit

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

    cash_after = cash_before - ebitda_hit
    headroom_after = cash_after - buffer

    return {
        "scenario": {
            "revenue_drop_pct": revenue_drop_pct,
            "week_number": week_number,
        },
        "finance": {
            "revenue_idr_mn": round(revenue, 2),
            "gross_margin_pct": round(gm_pct * 100, 2),
            "revenue_lost_idr_mn": round(revenue_lost, 2),
            "ebitda_before_idr_mn": round(ebitda_before, 2),
            "ebitda_after_idr_mn": round(ebitda_after, 2),
            "ebitda_hit_idr_mn": round(-ebitda_hit, 2),
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
            "First-order proxy: gross-margin % and opex held fixed, so EBITDA "
            "falls by the lost gross margin, and that shortfall is applied to "
            "the selected week's closing cash. Ignores working-capital timing, "
            "AR/AP lags, inventory, and FX. Directional, not a full forecast."
        ),
    }


TOOLS = {
    "simulate_revenue_drop_to_cash": simulate_revenue_drop_to_cash,
}

__all__ = ["TOOLS", "simulate_revenue_drop_to_cash"]