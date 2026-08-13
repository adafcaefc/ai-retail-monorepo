"""Demand Forecasting navigation scaffold."""

from __future__ import annotations

from src.llm.agents.descriptor import AgentDescriptor
from src.llm.agents.retail.demand_forecasting import dashboard

DESCRIPTOR = AgentDescriptor(
    id="retail.demand_forecasting",
    folder="retail",
    name="demand_forecasting",
    display="Demand Forecasting",
    description="Review retail demand forecasts.",
    prompt="Ask Demand...",
    starter_prompts=(),
    chat_agent="",
    simulation_agent="",
    action_agent="",
    monitoring_passes=(),
    db_domain="",
    snapshot_tool="",
    schema_tool="",
    import_agent_name="",
    allowed_tables=(),
    tools={},
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
    dashboard_only=True,
)

__all__ = ["DESCRIPTOR"]
