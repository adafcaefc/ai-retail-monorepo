"""Retail navigation scaffolds and empty-dashboard contract."""

from __future__ import annotations

import asyncio

from src.api.agents_html import list_agents
from src.llm.agents import AGENT_REGISTRY
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.modules import ENABLED_MODULES


RETAIL_MODULES = (
    ("retail.demand_forecasting", "Demand Forecasting", "Ask Demand..."),
    ("retail.inventory_risk", "Inventory Risk", "Ask Inventory..."),
    ("retail.replenishment", "Replenishment", "Ask Replenishment..."),
)


def test_retail_folder_contains_three_navigation_modules() -> None:
    retail = [item for item in ENABLED_MODULES if item.startswith("retail.")]

    assert retail == [item[0] for item in RETAIL_MODULES]
    assert "retail.retail" not in ENABLED_MODULES


def test_retail_modules_are_dashboard_only() -> None:
    for agent_id, display, prompt in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]

        assert descriptor.folder == "retail"
        assert descriptor.display == display
        assert descriptor.prompt == prompt
        assert descriptor.starter_prompts == ()
        assert descriptor.dashboard_only is True
        assert descriptor.chat_agent == ""
        assert descriptor.monitoring_passes == ()
        assert descriptor.tools == {}


def test_each_retail_module_has_its_own_builder() -> None:
    """All three used to share one stub that returned an empty payload.

    They now read Postgres, each from its own module. Asserted because the
    shared stub is still on disk (`retail/retail/dashboard.py`) and pointing a
    descriptor back at it would silently empty a board.
    """
    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]
        module = descriptor.build_dashboard.__module__

        assert module.endswith(f"{agent_id.split('.')[1]}.dashboard"), (
            f"{agent_id} builds from {module}"
        )


def test_retail_dashboards_declare_the_filters_they_apply() -> None:
    """Two are applied in SQL; the rest are reported back as ignored.

    The board narrows by the others itself, over the rows it is handed — but an
    API caller that is not the board gets told, which is the whole point of
    `ignored_filters`. A filter that appears to work and does nothing is worse
    than one that refuses.
    """
    scope = DashboardScope(legal_entity_id="GRC", store_id="ST-001", reorder_only=True)

    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]

        assert descriptor.supported_filters == frozenset(
            {"legal_entity_id", "category_group"}
        )
        assert scope.ignored_by(descriptor.supported_filters) == (
            "store_id",
            "reorder_only",
        )


def test_agents_api_exposes_three_retail_destinations() -> None:
    payload = asyncio.run(list_agents())
    retail = [item for item in payload["items"] if item["folder"] == "retail"]

    assert [item["id"] for item in retail] == [item[0] for item in RETAIL_MODULES]
    assert [item["display"] for item in retail] == [item[1] for item in RETAIL_MODULES]
    assert all(item["dashboard_only"] is True for item in retail)
    assert all(item["id"] != "retail.retail" for item in payload["items"])
