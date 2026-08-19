"""`render_ui_blocks` passthrough for the `dashboard_action` component format.

`dashboard_action` lets the Demand Forecasting chat agent patch the live
dashboard's filters/What-if levers (see
retail_demand_forecasting_chat.json's DASHBOARD_ACTION_CONTENT_SCHEMA). Like
`chart`/`simulation`/`next_route`, it is entirely LLM-authored: the renderer
only needs to pass the model's JSON straight through into a `UiBlock`, the
same as the two cases this mirrors. No LLM involved here -- a fake component
object with just the two attributes `render_ui_blocks` reads (`format`,
`content`) is enough.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from src.llm.html_renderer import UiBlock, render_ui_blocks  # noqa: E402


def _component(format_: str, content: dict) -> SimpleNamespace:
    return SimpleNamespace(format=format_, content=json.dumps(content))


def test_dashboard_action_passes_through_as_its_own_block_type():
    payload = {
        "title": "Switch to Grocery, daily grain",
        "summary": "Scoped the board to the Grocery legal entity at daily grain.",
        "query": {"legal_entity_id": "GRC", "grain": "daily"},
        "levers": {"promo": 15},
        "run_scenario": True,
    }

    blocks = render_ui_blocks([_component("dashboard_action", payload)])

    assert len(blocks) == 1
    block = blocks[0]
    assert isinstance(block, UiBlock)
    assert block.type == "dashboard_action"
    # Verbatim passthrough -- render_ui_blocks reshapes nothing for this
    # format, same as chart/simulation/next_route.
    assert block.data == payload


def test_dashboard_action_accepts_a_query_only_or_levers_only_patch():
    query_only = render_ui_blocks(
        [_component("dashboard_action", {"title": "t", "summary": "s", "query": {"store_id": "S1"}})]
    )
    assert query_only[0].data["query"] == {"store_id": "S1"}
    assert "levers" not in query_only[0].data

    levers_only = render_ui_blocks(
        [_component("dashboard_action", {"title": "t", "summary": "s", "levers": {"lead": -1}})]
    )
    assert levers_only[0].data["levers"] == {"lead": -1}
    assert "query" not in levers_only[0].data


def test_unrelated_formats_are_unaffected():
    blocks = render_ui_blocks(
        [
            _component("chart", {"title": "c"}),
            _component("next_route", {"title": "r", "routes": []}),
        ]
    )
    assert [block.type for block in blocks] == ["chart", "next_route"]
