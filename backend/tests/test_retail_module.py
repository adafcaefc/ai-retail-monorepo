"""Retail navigation scaffolds and empty-dashboard contract."""

from __future__ import annotations

import asyncio

from src.api.finance_agents_html import list_agents
from src.llm.agents import AGENT_REGISTRY
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


def test_retail_dashboards_are_intentionally_empty() -> None:
    expected = {
        "agent": "retail",
        "default_view": "",
        "kpis": [],
        "views": {},
        "side": {},
        "filters": [],
        "simulator": None,
    }

    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]
        assert descriptor.build_dashboard() == expected
        assert descriptor.build_dashboard("entity", "period", "category") == expected


def test_agents_api_exposes_three_retail_destinations() -> None:
    payload = asyncio.run(list_agents())
    retail = [item for item in payload["items"] if item["folder"] == "retail"]

    assert [item["id"] for item in retail] == [item[0] for item in RETAIL_MODULES]
    assert [item["display"] for item in retail] == [item[1] for item in RETAIL_MODULES]
    assert all(item["dashboard_only"] is True for item in retail)
    assert all(item["id"] != "retail.retail" for item in payload["items"])
