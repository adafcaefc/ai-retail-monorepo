"""Agent 2 · Inventory Risk."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import INVENTORY_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.retail.inventory_risk import dashboard
from src.llm.agents.retail.inventory_risk.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="retail.inventory_risk",
    folder="retail",
    name="inventory_risk",
    display="Inventory Risk",
    description="Classify stock states and quantify the value at risk.",
    prompt="Ask Inventory...",
    # One opener crosses into another agent's book. An opener that restates
    # the board asks this agent for what the reader is already looking at;
    # a question no single dashboard answers is the only thing here a
    # spreadsheet could not already do. Same reasoning as QC-042 in Finance.
    starter_prompts=(
        "Where is capital trapped, and how much of it?",
        "Which SKUs are closest to stocking out?",
        "Should Replenishment or Pricing fix the at-risk value?",
    ),
    chat_agent="retail.inventory_risk.chat",
    simulation_agent="retail.inventory_risk.simulation",
    action_agent="retail.inventory_risk.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="retail.inventory_risk.monitoring.stockout",
            instructions=(
                "Monitor SKUs below reorder point (states Stockout and Low), "
                "the value they expose, and any vertical, category or vendor "
                "where that risk concentrates."
            ),
        ),
        MonitoringPass(
            agent_name="retail.inventory_risk.monitoring.expiry",
            instructions=(
                "Monitor perishable stock whose days of supply exceed its "
                "shelf life: expiry units, the value behind them, and how "
                "little time remains to recover it."
            ),
        ),
        MonitoringPass(
            agent_name="retail.inventory_risk.monitoring.overstock",
            instructions=(
                "Monitor overstock and slow-moving SKUs as trapped capital, "
                "and where inventory value concentrates relative to the value "
                "actually at risk by vertical, category and store."
            ),
        ),
    ),
    db_domain="retail_inventory",
    snapshot_tool="get_inventory_risk_snapshot",
    schema_tool="describe_retail_inventory_tables",
    import_agent_name="retail_dataset",
    allowed_tables=INVENTORY_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
