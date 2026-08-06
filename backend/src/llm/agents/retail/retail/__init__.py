"""Retail demand & inventory agent."""

from __future__ import annotations

from src.llm.agents.descriptor import AgentDescriptor
from src.llm.agents.retail.retail import dashboard
from src.llm.agents.retail.retail.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="retail.retail",
    folder="retail",
    name="retail",
    display="Retail",
    description="Review retail demand, stock positions, and inventory risk.",
    prompt="Ask Retail about demand, stock, and reorder needs...",
    starter_prompts=(
        "Which SKUs need reordering right now?",
        "Which items are going viral?",
        "Show me the lowest days-of-cover items.",
    ),
    chat_agent="retail.retail.chat",
    simulation_agent="",
    action_agent="",
    monitoring_passes=(),
    db_domain="",
    snapshot_tool="",
    schema_tool="",
    import_agent_name="",
    allowed_tables=(),
    tools=TOOLS,
    build_dashboard=dashboard.build,
    dashboard_only=False,
)

__all__ = ["DESCRIPTOR"]