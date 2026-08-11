"""Demand Forecasting navigation scaffold."""

from __future__ import annotations

from src.llm.agents.descriptor import AgentDescriptor
from src.llm.agents.retail.retail import dashboard

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
    dashboard_only=True,
)

__all__ = ["DESCRIPTOR"]
