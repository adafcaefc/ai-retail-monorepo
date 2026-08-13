"""Agent 1 · Demand Forecasting."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import DEMAND_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.retail.demand_forecasting import dashboard
from src.llm.agents.retail.demand_forecasting.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="retail.demand_forecasting",
    folder="retail",
    name="demand_forecasting",
    display="Demand Forecasting",
    description="Project the next seven days of demand and what it will outrun.",
    prompt="Ask Demand...",
    # The middle opener deliberately invites the honest answer rather than a
    # flattering one: the accuracy figure on the card is a typed constant, not
    # a backtest, and an agent that cannot say so is worse than no agent.
    starter_prompts=(
        "Which SKUs will demand outrun in the next 7 days?",
        "How accurate is this forecast, really?",
        "Which viral items are thin on cover?",
    ),
    chat_agent="retail.demand_forecasting.chat",
    simulation_agent="retail.demand_forecasting.simulation",
    action_agent="retail.demand_forecasting.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="retail.demand_forecasting.monitoring.accuracy",
            instructions=(
                "Monitor forecast integrity: computed figures that disagree "
                "with the workbook's published KPIs, forecasts that do not "
                "reconcile with ads x 7.45, and the fact that the 92.4% "
                "accuracy figure is a typed constant rather than a backtest."
            ),
        ),
        MonitoringPass(
            agent_name="retail.demand_forecasting.monitoring.stockout_risk",
            instructions=(
                "Monitor SKUs whose seven-day forecast exceeds current "
                "position, ranked by shortfall units and remaining days of "
                "cover. This compares demand against position, not position "
                "against reorder point."
            ),
        ),
        MonitoringPass(
            agent_name="retail.demand_forecasting.monitoring.trend",
            instructions=(
                "Monitor items flagged viral or carrying a growth index above "
                "1 that are also thin on cover, and verticals whose "
                "seasonality index is not reflected in their stock position."
            ),
        ),
    ),
    db_domain="retail_demand",
    snapshot_tool="get_demand_forecast_snapshot",
    schema_tool="describe_retail_demand_tables",
    import_agent_name="retail_dataset",
    allowed_tables=DEMAND_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
