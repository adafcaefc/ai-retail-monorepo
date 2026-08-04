"""Treasury (cash & FX) agent."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import CASHFLOW_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.finance.treasury import dashboard
from src.llm.agents.finance.treasury.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="finance.treasury",
    folder="finance",
    name="treasury",
    display="Treasury",
    description="Review liquidity and cash-flow forecasts.",
    prompt="Ask Treasury about liquidity...",
    # QC-042 — see the note in finance/finance/__init__.py.
    starter_prompts=(
        "If Collection pulls cash in earlier, what happens to Week 5?",
        "Which action restores the minimum cash buffer fastest?",
        "What does deferring the vendor payment cost us in Week 6?",
    ),
    chat_agent="finance.treasury.chat",
    simulation_agent="finance.treasury.simulation",
    action_agent="finance.treasury.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="finance.treasury.monitoring.liquidity",
            instructions=(
                "Monitor cash-buffer breaches, projected weekly shortfalls, and "
                "periods below minimum cash thresholds."
            ),
        ),
        MonitoringPass(
            agent_name="finance.treasury.monitoring.funding",
            instructions=(
                "Monitor funding gaps, committed-facility headroom, and needs "
                "for credit-line draws after operational levers."
            ),
        ),
        MonitoringPass(
            agent_name="finance.treasury.monitoring.payment_timing",
            instructions=(
                "Monitor deferrable AP clusters, payment bunches that create "
                "breaches, and timing shifts that only move risk between weeks."
            ),
        ),
        MonitoringPass(
            agent_name="finance.treasury.monitoring.fx",
            instructions=(
                "Monitor FX liquidity exposure, hedge gaps, and policy-tolerance "
                "breaches."
            ),
        ),
    ),
    db_domain="cashflow",
    snapshot_tool="get_cashflow_baseline",
    schema_tool="describe_cashflow_tables",
    import_agent_name="cashflow_agent",
    allowed_tables=CASHFLOW_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
)

__all__ = ["DESCRIPTOR"]
