"""Agent 5 · Pricing & Markdown."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import PRICING_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.retail.pricing_markdown import dashboard
from src.llm.agents.retail.pricing_markdown.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="retail.pricing_markdown",
    folder="retail",
    name="pricing_markdown",
    display="Pricing & Markdown",
    description="Recover value from at-risk stock before it becomes a write-off.",
    prompt="Ask Pricing...",
    # Each opener reaches for a decision the board's own cards would not put
    # next to each other: which SKU to act on first, what a given depth
    # actually recovers, and the coordination gap with Replenishment that the
    # board's own Suppress Reorder tab exists to catch.
    starter_prompts=(
        "What should we mark down first?",
        "How much value is recoverable at this depth?",
        "Which Overstock SKUs need reorder suppressed before A3 orders more?",
    ),
    chat_agent="retail.pricing_markdown.chat",
    simulation_agent="retail.pricing_markdown.simulation",
    action_agent="retail.pricing_markdown.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="retail.pricing_markdown.monitoring.expiry_backlog",
            instructions=(
                "Monitor Expiry-state markdown candidates with large "
                "recoverable value and no action taken. Expiry is the one "
                "candidate state with a hard clock -- days of supply already "
                "exceeds shelf life -- so exposure here is the closest to "
                "becoming a pure write-off with no markdown possible at all."
            ),
        ),
        MonitoringPass(
            agent_name="retail.pricing_markdown.monitoring.write_off_growth",
            instructions=(
                "Monitor recovery rate (recoverable / at-risk) by vertical "
                "and category: verticals where most at-risk value is heading "
                "to write-off rather than being recoverable through markdown, "
                "weighted by exposure so a low rate on a small total is not "
                "raised over a smaller gap on a much larger one."
            ),
        ),
        MonitoringPass(
            agent_name="retail.pricing_markdown.monitoring.suppress_reorder_conflict",
            instructions=(
                "Monitor Overstock candidates that still carry open PO -- "
                "inbound supply that will worsen an already-excess position "
                "unless Replenishment (A3) suppresses the reorder. This is "
                "a coordination gap between A3 and A5, not a pricing call, "
                "and needs an A3 handoff rather than a markdown action."
            ),
        ),
    ),
    db_domain="retail_pricing",
    snapshot_tool="get_pricing_markdown_snapshot",
    schema_tool="describe_retail_pricing_tables",
    import_agent_name="retail_dataset",
    allowed_tables=PRICING_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
