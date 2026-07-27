"""Finance (performance) agent."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import FINANCE_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.finance.finance import dashboard
from src.llm.agents.finance.finance.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="finance.finance",
    folder="finance",
    name="finance",
    display="Finance",
    chat_agent="finance.finance.chat",
    simulation_agent="finance.finance.simulation",
    action_agent="finance.finance.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="finance.finance.monitoring.margin",
            instructions=(
                "Monitor gross-margin deterioration, product/customer margin "
                "compression, and margin misses versus target."
            ),
        ),
        MonitoringPass(
            agent_name="finance.finance.monitoring.price",
            instructions=(
                "Monitor price erosion, unnecessary discounting, and adverse "
                "price variance versus plan."
            ),
        ),
        MonitoringPass(
            agent_name="finance.finance.monitoring.cost",
            instructions=(
                "Monitor cost inflation, opex overruns, and budget-versus-actual "
                "cost breaches."
            ),
        ),
        MonitoringPass(
            agent_name="finance.finance.monitoring.mix",
            instructions=(
                "Monitor adverse product/customer/region mix shifts that drag "
                "average margin."
            ),
        ),
    ),
    db_domain="finance",
    snapshot_tool="get_financial_performance_snapshot",
    schema_tool="describe_financial_performance_tables",
    import_agent_name="financial_performance_agent",
    allowed_tables=FINANCE_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
)

__all__ = ["DESCRIPTOR"]
