"""Replenishment navigation scaffold."""

from __future__ import annotations

from src.llm.agents.descriptor import AgentDescriptor
from src.llm.agents.retail.retail import dashboard

DESCRIPTOR = AgentDescriptor(
    id="retail.replenishment",
    folder="retail",
    name="replenishment",
    display="Replenishment",
    description="Review retail replenishment needs.",
    prompt="Ask Replenishment...",
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
