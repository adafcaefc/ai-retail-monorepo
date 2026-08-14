from __future__ import annotations

import os

import pytest

from src.retrieval.planner import AdaptiveQueryPlanner


pytestmark = pytest.mark.azure_openai


def _live_planner() -> AdaptiveQueryPlanner:
    if os.getenv("RUN_AZURE_OPENAI_INTEGRATION") != "1":
        pytest.skip("set RUN_AZURE_OPENAI_INTEGRATION=1 to call Azure OpenAI")
    return AdaptiveQueryPlanner()


def test_live_forecast_prompt_returns_strict_query_plan_without_fallback() -> None:
    planner = _live_planner()
    plan = planner.plan(
        "Forecast demand for the next 7 days, including forecast basket and "
        "forecast accuracy using backtested MAPE."
    )
    assert plan.structured_requirements
    assert any(item.metric_id == "demand.forecast_7d" for item in plan.structured_requirements)
    assert planner.last_failure_category is None
    assert planner._model_agent is not None


def test_live_unseen_inventory_question_returns_strict_query_plan_without_fallback() -> None:
    planner = _live_planner()
    plan = planner.plan(
        "Rank categories by inventory exposure and explain which categories appear "
        "to need the most replenishment attention."
    )
    assert plan.structured_requirements or plan.semantic_requirements
    assert planner.last_failure_category is None
    assert planner._model_agent is not None
