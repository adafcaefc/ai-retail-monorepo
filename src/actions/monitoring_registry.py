"""Ordered specialized monitoring passes per domain agent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonitoringPass:
    agent_name: str
    instructions: str


MONITORING_PASSES_BY_DOMAIN: dict[str, tuple[MonitoringPass, ...]] = {
    "finance": (
        MonitoringPass(
            agent_name="finance_margin_monitoring_agent",
            instructions=(
                "Monitor gross-margin deterioration, product/customer margin "
                "compression, and margin misses versus target."
            ),
        ),
        MonitoringPass(
            agent_name="finance_price_monitoring_agent",
            instructions=(
                "Monitor price erosion, unnecessary discounting, and adverse "
                "price variance versus plan."
            ),
        ),
        MonitoringPass(
            agent_name="finance_cost_monitoring_agent",
            instructions=(
                "Monitor cost inflation, opex overruns, and budget-versus-actual "
                "cost breaches."
            ),
        ),
        MonitoringPass(
            agent_name="finance_mix_monitoring_agent",
            instructions=(
                "Monitor adverse product/customer/region mix shifts that drag "
                "average margin."
            ),
        ),
    ),
    "cashflow": (
        MonitoringPass(
            agent_name="cashflow_liquidity_monitoring_agent",
            instructions=(
                "Monitor cash-buffer breaches, projected weekly shortfalls, and "
                "periods below minimum cash thresholds."
            ),
        ),
        MonitoringPass(
            agent_name="cashflow_funding_monitoring_agent",
            instructions=(
                "Monitor funding gaps, committed-facility headroom, and needs "
                "for credit-line draws after operational levers."
            ),
        ),
        MonitoringPass(
            agent_name="cashflow_payment_timing_monitoring_agent",
            instructions=(
                "Monitor deferrable AP clusters, payment bunches that create "
                "breaches, and timing shifts that only move risk between weeks."
            ),
        ),
        MonitoringPass(
            agent_name="cashflow_fx_monitoring_agent",
            instructions=(
                "Monitor FX liquidity exposure, hedge gaps, and policy-tolerance "
                "breaches."
            ),
        ),
    ),
    "collection": (
        MonitoringPass(
            agent_name="collection_overdue_monitoring_agent",
            instructions=(
                "Monitor overdue AR concentration, aging breaches, and DSO "
                "deterioration."
            ),
        ),
        MonitoringPass(
            agent_name="collection_credit_risk_monitoring_agent",
            instructions=(
                "Monitor high credit exposure, deteriorating risk tiers, and "
                "accounts needing credit hold or prepayment."
            ),
        ),
        MonitoringPass(
            agent_name="collection_recovery_monitoring_agent",
            instructions=(
                "Monitor recoverable cash opportunities, early-pay discount "
                "candidates, and high-potential worklist items."
            ),
        ),
        MonitoringPass(
            agent_name="collection_concentration_monitoring_agent",
            instructions=(
                "Monitor customer concentration risk where a small set of "
                "accounts drives most overdue exposure."
            ),
        ),
    ),
    "leakage": (
        MonitoringPass(
            agent_name="leakage_fraud_monitoring_agent",
            instructions=(
                "Monitor suspected fraud, suspicious vendor/bank-account "
                "changes, callback failures, and high-risk payment anomalies."
            ),
        ),
        MonitoringPass(
            agent_name="leakage_duplicate_payment_monitoring_agent",
            instructions=(
                "Monitor duplicate invoices/payments, repeated vendor payment "
                "patterns, and recoverable duplicate cash leakage."
            ),
        ),
        MonitoringPass(
            agent_name="leakage_overpayment_monitoring_agent",
            instructions=(
                "Monitor overpayments, overbilling versus PO/contract/GRN, and "
                "recoverable excess payouts."
            ),
        ),
        MonitoringPass(
            agent_name="leakage_controls_monitoring_agent",
            instructions=(
                "Monitor payment-control weaknesses such as missing three-way "
                "match, weak vendor-master controls, and approval gaps."
            ),
        ),
    ),
}


def monitoring_passes_for(domain: str) -> tuple[MonitoringPass, ...]:
    return MONITORING_PASSES_BY_DOMAIN[domain]


__all__ = [
    "MONITORING_PASSES_BY_DOMAIN",
    "MonitoringPass",
    "monitoring_passes_for",
]
