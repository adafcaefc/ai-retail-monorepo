"""The enabled modules, in sidebar order.

Single source of truth for both sides of the app: the registry
(`src.llm.agents`) discovers exactly these, `GET /api/html/agents` serves
them, and the frontend sidebar is built from that response.

Adding a module: create `agents/<folder>/<name>/` with a `DESCRIPTOR`, then
add its canonical id here. Removing one: delete the id (the folder may stay).
"""

from __future__ import annotations

ENABLED_MODULES: tuple[str, ...] = (
    # "finance.finance",
    # "finance.treasury",
    # "finance.collection",
    # "finance.leakage",
    # Built: chat, monitoring, actions and a Postgres-backed board.
    "retail.demand_forecasting",
    "retail.inventory_risk",
    "retail.replenishment",
    # Agent 3.1: the line-level evidence behind Agent 3's recommendations.
    # Sits directly below its parent because list order is sidebar order --
    # there is no parent/child field, and adjacency is how the relationship is
    # expressed.
    "retail.replenishment_detail",
    "retail.promotion_effectiveness",
    # Navigation-only: reachable in the sidebar, nothing wired behind them yet.
    "retail.pricing_markdown",
    "retail.assortment_optimization",
    "retail.workforce_optimizer",
    "retail.vendor_brand_performance",
    "retail.ai_explanation_summary",
)

__all__ = ["ENABLED_MODULES"]
