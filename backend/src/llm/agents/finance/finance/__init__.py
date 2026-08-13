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
    description="Explore financial performance and plan variances.",
    prompt="Ask Finance about performance...",
    # QC-042. The openers used to restate the board ("Explain the main finance
    # performance risks"), which asks the agent for what the CFO is already
    # looking at. One opener per agent now crosses into another agent's book,
    # because a question no single dashboard can answer is the only thing here
    # a spreadsheet could not already do.
    starter_prompts=(
        "Which agent should fix the margin problem?",
        "What are the largest EBITDA variance drivers?",
        "Is the price decline or the cost overrun hurting margin more?",
    ),
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
    # The newdata import, not the retired financial_performance_agent one.
    # This id is stamped into the chat's action-simulation context, so leaving
    # it on the old importer told the model it was looking at batch 19 while
    # its snapshot came from batch 26.
    import_agent_name="new_dataset",
    allowed_tables=FINANCE_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
