"""Treasury (cash & FX) agent data tools."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.tools.db import _read_connection
from src.llm.agents.common.tools.period import treasury_period
from src.llm.agents.finance.treasury.cashflow import service as cashflow_service
from src.llm.agents.finance.treasury.cashflow.models import CashFlowSimulationRequest


def get_cashflow_baseline() -> dict[str, Any]:
    """Return the latest verified cash-flow forecast, assumptions, and drivers."""

    baseline = cashflow_service.get_baseline().model_dump(mode="json")
    # The forecast model carries week numbers but no dates (QC-035), so the
    # span is read from the weeks themselves rather than added to the model.
    with _read_connection() as connection:
        baseline["period"] = treasury_period(
            connection,
            baseline.get("import_batch_id"),
        )
    return baseline


def simulate_cashflow(
    accelerate_collection_idr_mn: float = 0,
    defer_payment_idr_mn: float = 0,
    credit_line_draw_idr_mn: float = 0,
    hedge_usd: float = 0,
) -> dict[str, Any]:
    """Recalculate Weeks 5-7 using validated liquidity and FX levers."""

    request = CashFlowSimulationRequest(
        accelerate_collection_idr_mn=accelerate_collection_idr_mn,
        defer_payment_idr_mn=defer_payment_idr_mn,
        credit_line_draw_idr_mn=credit_line_draw_idr_mn,
        hedge_usd=hedge_usd,
    )
    return cashflow_service.simulate(request).model_dump(mode="json")


TOOLS = {
    "get_cashflow_baseline": get_cashflow_baseline,
    "simulate_cashflow": simulate_cashflow,
}


__all__ = ["TOOLS", "get_cashflow_baseline", "simulate_cashflow"]
