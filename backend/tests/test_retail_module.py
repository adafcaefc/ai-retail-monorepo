"""Retail sidebar module and empty-dashboard contract."""

from __future__ import annotations

import asyncio

from src.api.finance_agents_html import list_agents
from src.llm.agents import AGENT_REGISTRY
from src.llm.agents.modules import ENABLED_MODULES


def test_retail_is_a_separate_single_dashboard_folder() -> None:
    finance = [item for item in ENABLED_MODULES if item.startswith("finance.")]
    retail = [item for item in ENABLED_MODULES if item.startswith("retail.")]

    assert finance == [
        "finance.finance",
        "finance.treasury",
        "finance.collection",
        "finance.leakage",
    ]
    assert retail == ["retail.retail"]


def test_retail_metadata_is_dashboard_only() -> None:
    descriptor = AGENT_REGISTRY["retail.retail"]

    assert descriptor.folder == "retail"
    assert descriptor.display == "Retail"
    assert descriptor.description == (
        "Review retail performance, trends, and operational insights."
    )
    assert descriptor.prompt == "Retail chat is not connected yet."
    assert len(descriptor.starter_prompts) == 2
    assert descriptor.dashboard_only is True
    assert descriptor.monitoring_passes == ()
    assert descriptor.tools == {}


def test_retail_dashboard_is_intentionally_empty() -> None:
    payload = AGENT_REGISTRY["retail.retail"].build_dashboard()

    assert payload == {
        "agent": "retail",
        "default_view": "",
        "kpis": [],
        "views": {},
        "side": {},
        "filters": [],
        "simulator": None,
    }


def test_agents_api_exposes_retail_capability() -> None:
    payload = asyncio.run(list_agents())
    retail = next(item for item in payload["items"] if item["id"] == "retail.retail")

    assert retail["folder"] == "retail"
    assert retail["display"] == "Retail"
    assert retail["dashboard_only"] is True
