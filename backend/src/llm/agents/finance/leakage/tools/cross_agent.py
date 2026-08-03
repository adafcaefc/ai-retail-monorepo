"""Cross-agent tool: leakage exposure -> finance EBITDA impact."""

from __future__ import annotations

from typing import Any

from src.llm.agents.finance.leakage.tools.leakage_data import (
    get_payment_leakage_snapshot,
)
from src.llm.agents.finance.finance.tools.performance_data import (
    get_financial_performance_snapshot,
)


def _kpi(fin: dict[str, Any], name: str) -> float:
    for row in fin.get("kpis") or []:
        if str(row.get("metric_name")) == name:
            return float(row.get("actual_value") or 0)
    return 0.0


def simulate_leakage_to_ebitda(
    only_direct_loss: bool = False,
) -> dict[str, Any]:
    """Estimate EBITDA if leakage exposure becomes a realized loss."""
    # --- Leakage side ---
    leak = get_payment_leakage_snapshot()
    summary = (leak.get("summary") or [{}])[0]
    at_risk = float(summary.get("total_amount_at_risk_idr_mn") or 0)

    if only_direct_loss:
        at_risk = sum(
            float(c.get("amount") or 0)
            for c in (leak.get("category_breakdowns") or [])
            if c.get("is_direct_loss", True)
        )

    # --- Finance side ---
    fin = get_financial_performance_snapshot()
    revenue = _kpi(fin, "Revenue (IDR mn)")
    ebitda_before = _kpi(fin, "EBITDA (IDR mn)")
    ebitda_after = ebitda_before - at_risk

    margin_before = (ebitda_before / revenue * 100) if revenue else 0.0
    margin_after = (ebitda_after / revenue * 100) if revenue else 0.0

    return {
        "finance": {
            "revenue_idr_mn": round(revenue, 2),
            "ebitda_before_idr_mn": round(ebitda_before, 2),
            "ebitda_margin_before_pct": round(margin_before, 2),
        },
        "leakage": {
            "exposure_idr_mn": round(at_risk, 2),
            "only_direct_loss": only_direct_loss,
        },
        "ebitda_after_idr_mn": round(ebitda_after, 2),
        "ebitda_margin_after_pct": round(margin_after, 2),
        "ebitda_impact_idr_mn": round(-at_risk, 2),
        "ebitda_margin_impact_pct": round(margin_after - margin_before, 2),
        "assumption": (
            "Worst case: the full at-risk exposure becomes a realized loss "
            "with zero recovery and no blocking. Most exposure is currently "
            "blocked or recoverable, so this is an upper bound, not a forecast."
        ),
    }


TOOLS = {
    "simulate_leakage_to_ebitda": simulate_leakage_to_ebitda,
}

__all__ = ["TOOLS", "simulate_leakage_to_ebitda"]