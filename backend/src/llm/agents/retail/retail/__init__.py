"""Retail dashboard module."""

from __future__ import annotations

from src.llm.agents.descriptor import AgentDescriptor
from src.llm.agents.retail.retail import dashboard

DESCRIPTOR = AgentDescriptor(
    id="retail.retail",
    folder="retail",
    name="retail",
    display="Retail",
    description="Review retail performance, trends, and operational insights.",
    prompt="Retail chat is not connected yet.",
    starter_prompts=(
        "Summarize retail performance trends.",
        "Which retail operations need attention?",
    ),
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
