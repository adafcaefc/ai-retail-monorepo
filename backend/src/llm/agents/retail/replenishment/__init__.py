"""Agent 3 · Replenishment."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import (
    REPLENISHMENT_ALLOWED_TABLES,
)
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.retail.replenishment import dashboard
from src.llm.agents.retail.replenishment.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="retail.replenishment",
    folder="retail",
    name="replenishment",
    display="Replenishment",
    description="Build the purchase plan in buy units, and route it for approval.",
    prompt="Ask Replenishment...",
    # The third opener crosses into Inventory Risk's book on purpose: whether
    # to buy or to mark down is precisely the question neither board answers
    # alone.
    starter_prompts=(
        "What should we order today, in buy units?",
        "Where are we paying more than the best available price?",
        "Which shortages should we buy out of rather than mark down?",
    ),
    chat_agent="retail.replenishment.chat",
    simulation_agent="retail.replenishment.simulation",
    action_agent="retail.replenishment.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="retail.replenishment.monitoring.coverage",
            instructions=(
                "Monitor lines below reorder point that open purchase orders "
                "do not cover, ranked by days of cover remaining against the "
                "vendor's lead time."
            ),
        ),
        MonitoringPass(
            agent_name="retail.replenishment.monitoring.vendor",
            instructions=(
                "Monitor vendor service risk on reorder lines - OTIF, fill, "
                "defect and lead adherence - weighted by the order value each "
                "vendor actually carries, plus vendor concentration."
            ),
        ),
        MonitoringPass(
            agent_name="retail.replenishment.monitoring.sourcing",
            instructions=(
                "Monitor savings available from best-price versus designated "
                "vendors and the service trade behind them, purchase value "
                "routed to the wrong ERP approval tier, and pack-factor "
                "rounding waste in buy units."
            ),
        ),
    ),
    db_domain="retail_replenishment",
    snapshot_tool="get_replenishment_snapshot",
    schema_tool="describe_retail_replenishment_tables",
    import_agent_name="retail_dataset",
    allowed_tables=REPLENISHMENT_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
