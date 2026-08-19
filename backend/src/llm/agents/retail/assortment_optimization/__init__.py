"""Agent 6 · Assortment Optimization."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import ASSORTMENT_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.retail.assortment_optimization import dashboard
from src.llm.agents.retail.assortment_optimization.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="retail.assortment_optimization",
    folder="retail",
    name="assortment_optimization",
    display="Assortment Optimization",
    description="Decide what to delist and what to grow, and what capital that frees.",
    prompt="Ask Assortment...",
    starter_prompts=(
        "Which SKUs should we delist?",
        "How much capital would delisting the tail free?",
        "Which lines earn their shelf space?",
    ),
    chat_agent="retail.assortment_optimization.chat",
    simulation_agent="retail.assortment_optimization.simulation",
    action_agent="retail.assortment_optimization.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="retail.assortment_optimization.monitoring.delist",
            instructions=(
                "Monitor tail SKUs (lowest 25% contribution per day), capital "
                "trapped in delist candidates, and product rationalization "
                "opportunities across verticals."
            ),
        ),
        MonitoringPass(
            agent_name="retail.assortment_optimization.monitoring.grow",
            instructions=(
                "Monitor GMROI performance, healthy winner SKUs in the top "
                "quartile of GMROI eligible for shelf space expansion, and "
                "capital efficiency."
            ),
        ),
        # The board offers four best-action tabs; delist and grow above cover
        # two. Space and vendor are the other two, and they are the decisions
        # that stop being per-SKU: a category losing half its range is a
        # planogram conversation, a vendor carrying eight delist candidates is
        # a supplier one. Without this pass those two tabs raise nothing.
        MonitoringPass(
            agent_name="retail.assortment_optimization.monitoring.space",
            instructions=(
                "Monitor where rationalization stops being a line-by-line "
                "decision: categories whose delist candidates take half the "
                "range or more, and vendors carrying enough delist candidates "
                "to warrant a supplier review rather than per-SKU cuts."
            ),
        ),
    ),
    db_domain="retail_assortment",
    snapshot_tool="get_assortment_performance_snapshot",
    schema_tool="describe_retail_assortment_tables",
    import_agent_name="retail_dataset",
    allowed_tables=ASSORTMENT_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
