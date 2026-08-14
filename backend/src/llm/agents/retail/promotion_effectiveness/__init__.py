"""Agent 4 · Promotion Effectiveness."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import PROMOTION_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.retail.promotion_effectiveness import dashboard
from src.llm.agents.retail.promotion_effectiveness.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="retail.promotion_effectiveness",
    folder="retail",
    name="promotion_effectiveness",
    display="Promotion Effectiveness",
    description="Measure promo uplift, incremental margin and ROI, and route the campaign plan.",
    prompt="Ask Promotion...",
    # Each opener reaches for a decision the board's own cards would not put
    # next to each other: the margin quality behind the uplift, the supplier
    # funding that decides whether a high-uplift promo is worth running, and the
    # pre-buy that has to land before valid-from or the promo stocks out.
    starter_prompts=(
        "Which promotions are actually paying for themselves?",
        "Where is high uplift being given away without supplier funding?",
        "Which campaigns need a pre-buy before they go live?",
    ),
    chat_agent="retail.promotion_effectiveness.chat",
    simulation_agent="retail.promotion_effectiveness.simulation",
    action_agent="retail.promotion_effectiveness.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="retail.promotion_effectiveness.monitoring.margin_quality",
            instructions=(
                "Monitor promo ROI and incremental margin: verticals or SKUs "
                "whose modeled uplift is high but whose cannibalization drag or "
                "low margin erodes the incremental margin, and campaigns whose "
                "planned uplift is not converting into ROI. ROI is a stored KPI "
                "with no exposed investment column, so frame findings against "
                "incremental margin rather than a derived spend."
            ),
        ),
        MonitoringPass(
            agent_name="retail.promotion_effectiveness.monitoring.funding",
            instructions=(
                "Monitor supplier funding gaps: campaigns and verticals where "
                "expected uplift is high but supplier funding sits below the "
                "guardrail, meaning the promo cost is largely unrecovered. "
                "Funding is a planned offset, not guaranteed cash collection."
            ),
        ),
        MonitoringPass(
            agent_name="retail.promotion_effectiveness.monitoring.prebuy_cannib",
            instructions=(
                "Monitor pre-buy exposure and cannibalization: campaigns whose "
                "pre-buy uplift units are material enough to require an A3 "
                "replenishment handoff before valid-from, and promo-eligible "
                "SKUs whose cannibalization cap is breached so the promo eats "
                "base sales. Pre-buy units need A3 for vendor lead, MOQ and "
                "open-PO feasibility."
            ),
        ),
    ),
    db_domain="retail_promotion",
    snapshot_tool="get_promotion_effectiveness_snapshot",
    schema_tool="describe_retail_promotion_tables",
    import_agent_name="retail_dataset",
    allowed_tables=PROMOTION_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
