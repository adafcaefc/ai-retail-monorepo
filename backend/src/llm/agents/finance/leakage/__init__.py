"""Leakage (payment integrity) agent."""

from __future__ import annotations

from src.llm.agents.common.tools.freeform_query import LEAKAGE_ALLOWED_TABLES
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.finance.leakage import dashboard
from src.llm.agents.finance.leakage.tools import TOOLS

DESCRIPTOR = AgentDescriptor(
    id="finance.leakage",
    folder="finance",
    name="leakage",
    display="Leakage",
    description="Review billing gaps and revenue leakage.",
    prompt="Ask Leakage about revenue exposure...",
    # QC-042 — see the note in finance/finance/__init__.py.
    starter_prompts=(
        "Does the blocked fraud change the cash forecast?",
        "Which leakage issues should be investigated first?",
        "Which vendor is riskiest, and why does it rank first?",
    ),
    chat_agent="finance.leakage.chat",
    simulation_agent="finance.leakage.simulation",
    action_agent="finance.leakage.action",
    monitoring_passes=(
        MonitoringPass(
            agent_name="finance.leakage.monitoring.fraud",
            instructions=(
                "Monitor suspected fraud, suspicious vendor/bank-account "
                "changes, callback failures, and high-risk payment anomalies."
            ),
        ),
        MonitoringPass(
            agent_name="finance.leakage.monitoring.duplicate_payment",
            instructions=(
                "Monitor duplicate invoices/payments, repeated vendor payment "
                "patterns, and recoverable duplicate cash leakage."
            ),
        ),
        MonitoringPass(
            agent_name="finance.leakage.monitoring.overpayment",
            instructions=(
                "Monitor overpayments, overbilling versus PO/contract/GRN, and "
                "recoverable excess payouts."
            ),
        ),
        MonitoringPass(
            agent_name="finance.leakage.monitoring.controls",
            instructions=(
                "Monitor payment-control weaknesses such as missing three-way "
                "match, weak vendor-master controls, and approval gaps."
            ),
        ),
    ),
    db_domain="leakage",
    snapshot_tool="get_payment_leakage_snapshot",
    schema_tool="describe_payment_leakage_tables",
    import_agent_name="payment_leakage_fraud_agent",
    allowed_tables=LEAKAGE_ALLOWED_TABLES,
    tools=TOOLS,
    build_dashboard=dashboard.build,
    supported_filters=dashboard.SUPPORTED_FILTERS,
)

__all__ = ["DESCRIPTOR"]
