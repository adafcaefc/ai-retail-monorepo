"""Agent 3.1 · Replenishment Detail."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import (
    REPLENISHMENT_DETAIL_ALLOWED_TABLES,
)
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.retail.replenishment_detail import dashboard
from src.llm.agents.retail.replenishment_detail.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="retail.replenishment_detail",
    folder="retail",
    name="replenishment_detail",
    display="Replenishment Detail",
    description=(
        "Read the line-level evidence behind every replenishment "
        "recommendation, SKU by SKU."
    ),
    prompt="Ask Replenishment Detail...",
    # The second opener is the one this board exists for. Every other retail
    # board reports a figure; this one is asked to show its working, and a
    # planner who cannot reproduce a number will not sign a purchase order
    # against it.
    starter_prompts=(
        "Which lines cannot be actioned, and what is blocking them?",
        "Show me how the order quantity on GRC-001 was calculated.",
        "Where does rounding to whole packs cost us the most?",
    ),
    chat_agent="retail.replenishment_detail.chat",
    simulation_agent="retail.replenishment_detail.simulation",
    action_agent="retail.replenishment_detail.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="retail.replenishment_detail.monitoring.exceptions",
            instructions=(
                "Monitor lines that cannot be actioned - missing pack factor, "
                "buy UOM, vendor or trade-agreement price, and invalid ROP/Max "
                "pairs - ranked by the order value each exception blocks."
            ),
        ),
        MonitoringPass(
            agent_name="retail.replenishment_detail.monitoring.rounding",
            instructions=(
                "Monitor pack-factor rounding: sales units bought above the "
                "raw Max minus Position requirement, ranked by the capital the "
                "overshoot ties up, and segmented by buy UOM. Replenishment's "
                "sourcing pass counts this waste at chain level; report it per "
                "line, and name the SKUs whose pack size is the cause."
            ),
        ),
        MonitoringPass(
            agent_name="retail.replenishment_detail.monitoring.tie_out",
            instructions=(
                "Monitor whether the sheet reconciles against itself - Position "
                "against on-hand plus open PO, the reorder flag against "
                "Position below ROP, Amount against ordered sales units times "
                "unit price, and Saving against the designated-best price "
                "delta. Report a break as a data finding, never as a planning "
                "recommendation."
            ),
        ),
    ),
    db_domain="retail_replenishment_detail",
    snapshot_tool="get_replenishment_detail_snapshot",
    schema_tool="describe_retail_replenishment_detail_tables",
    import_agent_name="retail_dataset",
    allowed_tables=REPLENISHMENT_DETAIL_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
