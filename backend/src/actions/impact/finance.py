"""Finance impact, sized from the EBITDA bridge.

The bridge is the one place Finance states, in the ledger, how much each driver
cost: `variance_drivers` holds a named step and an `impact_idr_mn` for each.
That makes it the honest size for a Finance lever, in the same way the
forecast's deferrable payable sizes a Treasury deferral — a figure someone can
be shown, rather than one read out of the action's own sentence.

An action is only credited with the driver it names. "Recover discount
leakage" is sized at the discount/price step and nothing else; it is not given
the whole variance, because an action that claims every driver is the defect
QC-016 reports rather than a fix for it.
"""

from __future__ import annotations

import re
from typing import Any

FINANCE_AGENTS = frozenset({"finance.finance", "finance", "performance"})
AGENTS = FINANCE_AGENTS

PRICE = "price"
COST = "cost"
VOLUME = "volume"
MIX = "mix"
OPEX = "opex"

# Which bridge step each lever is measured against. Matched loosely because
# the bridge's own wording has changed with the dataset ("Price" became
# "Discount & price erosion"), and a lever that silently stops matching would
# retire itself the way QC-046's severity term did.
_DRIVER_PATTERNS: dict[str, re.Pattern[str]] = {
    PRICE: re.compile(r"price|discount", re.I),
    COST: re.compile(r"cost|input|fx", re.I),
    VOLUME: re.compile(r"volume", re.I),
    MIX: re.compile(r"mix", re.I),
    OPEX: re.compile(r"opex|operating expense", re.I),
}

# What the action's own wording has to say to claim each lever. Deliberately
# narrower than the driver patterns: the bridge may call a step "Discount &
# price erosion", but an action only pulls that lever if it talks about
# pricing or discounting, not merely about "erosion".
_LEVER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (PRICE, re.compile(r"pric\w+|discount|realis\w+ rate|list rate", re.I)),
    (COST, re.compile(r"cost|procure\w*|supplier rate|input|hedge|fx", re.I)),
    (VOLUME, re.compile(r"volume|throughput|units", re.I)),
    (MIX, re.compile(r"\bmix\b|category shift|product shift", re.I)),
    (OPEX, re.compile(r"opex|operating expense|overhead|headcount", re.I)),
)


def load_baseline() -> dict[str, Any]:
    from src.llm.agents.finance.finance.tools.performance_data import (
        get_financial_performance_snapshot,
    )

    return get_financial_performance_snapshot()


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def detect_levers(title: str, spec: str) -> list[str]:
    """Levers the wording names, title first — see treasury.detect_levers."""
    for text in (title, spec):
        found = [
            (match.start(), lever)
            for lever, pattern in _LEVER_PATTERNS
            if (match := pattern.search(text or ""))
        ]
        if found:
            return [lever for _, lever in sorted(found)]
    return []


def _steps(baseline: dict[str, Any]) -> dict[str, tuple[str, float]]:
    """Bridge steps that hurt, keyed by the lever that addresses them.

    Only negative steps are offered as levers: an action cannot recover a
    driver that already helped, and offering Volume (+2,055) as something to
    "recover" would put a positive number behind a corrective action.
    """
    out: dict[str, tuple[str, float]] = {}
    for row in baseline.get("variance_drivers") or []:
        name = str(row.get("driver_name") or "").strip()
        impact = _num(row.get("impact_idr_mn"))
        if not name or impact >= 0:
            continue
        for lever, pattern in _DRIVER_PATTERNS.items():
            if pattern.search(name) and lever not in out:
                out[lever] = (name, impact)
    return out


def _ebitda(baseline: dict[str, Any]) -> float:
    for row in baseline.get("profit_summary") or []:
        if str(row.get("metric_name") or "").strip().lower() == "ebitda":
            return _num(row.get("actual_value"))
    return 0.0


def compute(title: str, spec: str, baseline: dict[str, Any]):
    from src.actions.impact import ComputedImpact

    steps = _steps(baseline)
    levers = [lever for lever in detect_levers(title, spec) if lever in steps]
    if not levers:
        return None

    # One driver per action, the first the wording names. Summing several
    # would double-count: the bridge steps are already additive against the
    # same budget, so an action claiming two of them claims part of the same
    # gap twice (QC-022).
    lever = levers[0]
    driver_name, drag = steps[lever]
    ebitda = _ebitda(baseline)
    if not ebitda:
        return None

    recovered = abs(drag)
    after = ebitda + recovered
    line = (
        f"EBITDA: {ebitda:,.1f} +{recovered:,.1f} -> {after:,.1f} "
        f"(IDR mn · closes the {driver_name} bridge step in full)"
    )
    return ComputedImpact(
        line=line,
        magnitude=recovered,
        # The size is a named row of the published bridge, which is as
        # traceable as Finance gets.
        traceable=True,
        # Recovering a whole bridge step is the ceiling, not a forecast: no
        # book limit is being hit, so nothing is capped.
        capped=False,
        levers=(lever,),
    )


__all__ = ["AGENTS", "FINANCE_AGENTS", "compute", "detect_levers", "load_baseline"]
