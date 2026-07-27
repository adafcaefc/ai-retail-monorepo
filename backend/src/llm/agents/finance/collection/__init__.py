"""Collection (receivables) agent."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import COLLECTIONS_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.finance.collection import dashboard
from src.llm.agents.finance.collection.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="finance.collection",
    folder="finance",
    name="collection",
    display="Collection",
    chat_agent="finance.collection.chat",
    simulation_agent="finance.collection.simulation",
    action_agent="finance.collection.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="finance.collection.monitoring.overdue",
            instructions=(
                "Monitor overdue AR concentration, aging breaches, and DSO "
                "deterioration."
            ),
        ),
        MonitoringPass(
            agent_name="finance.collection.monitoring.credit_risk",
            instructions=(
                "Monitor high credit exposure, deteriorating risk tiers, and "
                "accounts needing credit hold or prepayment."
            ),
        ),
        MonitoringPass(
            agent_name="finance.collection.monitoring.recovery",
            instructions=(
                "Monitor recoverable cash opportunities, early-pay discount "
                "candidates, and high-potential worklist items."
            ),
        ),
        MonitoringPass(
            agent_name="finance.collection.monitoring.concentration",
            instructions=(
                "Monitor customer concentration risk where a small set of "
                "accounts drives most overdue exposure."
            ),
        ),
    ),
    db_domain="collection",
    snapshot_tool="get_collections_monitoring_context",
    schema_tool="describe_collections_tables",
    import_agent_name="collections_credit_agent",
    allowed_tables=COLLECTIONS_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
)

__all__ = ["DESCRIPTOR"]
