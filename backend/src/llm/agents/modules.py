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
    # Order is the agent's own number, which is what the sidebar shows and what
    # every spec, board and audit refers to. Status is marked per line rather
    # than per block, because the two no longer group: A6 is built while A5
    # above it is not, and reordering to keep the blocks tidy would renumber the
    # sidebar.
    #
    #   built  chat, monitoring, actions and a warehouse-backed board
    #   nav    reachable in the sidebar, nothing wired behind it yet
    "retail.demand_forecasting",        # A1  built
    "retail.inventory_risk",            # A2  built
    "retail.replenishment",             # A3  built
    "retail.promotion_effectiveness",   # A4  built
    "retail.pricing_markdown",          # A5  nav
    "retail.assortment_optimization",   # A6  built
    "retail.workforce_optimizer",       # A7  nav
    "retail.vendor_brand_performance",  # A8  nav
    "retail.ai_explanation_summary",    # A9  nav
)

__all__ = ["ENABLED_MODULES"]
