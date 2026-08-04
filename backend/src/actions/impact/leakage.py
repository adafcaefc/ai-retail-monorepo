"""Leakage impact, sized from the flagged cases.

Each lever is worth exactly the flagged amount of the leakage type it acts on,
read from the same `anomalies` rows the category chart is built from. That
keeps an action's claim and the bar behind it on one number — the split the
QC-032 evidence describes ("the same 900 mn under three names") comes from
each surface sizing itself independently.

The claw-back rates are the dashboard's own recovery assumptions, not new
ones, and every line states the rate it used so the figure can be argued with.
"""

from __future__ import annotations

import re
from typing import Any

LEAKAGE_AGENTS = frozenset({"finance.leakage", "leakage", "payment_leakage"})
AGENTS = LEAKAGE_AGENTS

BLOCK = "block"
DUPLICATE = "duplicate"
OVERBILL = "overbill"
SPLIT = "split"

# Which flagged type each lever acts on, and how much of it the dashboard
# assumes is actually recoverable. Blocking is certain because the money has
# not left; a claw-back is a negotiation, which is why it is rated lower and
# reported as capped.
_TARGETS: dict[str, tuple[re.Pattern[str], float]] = {
    BLOCK: (re.compile(r"bank[-\s]?change|fraud", re.I), 1.00),
    DUPLICATE: (re.compile(r"duplicate", re.I), 0.95),
    OVERBILL: (re.compile(r"overbill|3-way|po[-/\s]?grn", re.I), 0.90),
    # Threshold splitting is a control breach, not lost cash: the exposure is
    # real but the money is stopped, which is why the category sits outside
    # the direct-loss bars (QC-015) and why this lever prevents rather than
    # recovers.
    SPLIT: (re.compile(r"split|threshold", re.I), 1.00),
}

_LEVER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        BLOCK,
        re.compile(
            r"block\w*|hold payment|dual verification|bank[-\s]?(?:detail|change)"
            r"|verify\w* bank|vendor callback|freeze payment|fraud",
            re.I,
        ),
    ),
    (
        DUPLICATE,
        re.compile(r"duplicate|double[-\s]?pay\w*|recall|clawback|claw[-\s]back", re.I),
    ),
    (
        OVERBILL,
        re.compile(r"overbill\w*|3-way|three[-\s]way|po[-/\s]?grn|variance", re.I),
    ),
    (
        SPLIT,
        re.compile(
            r"split[-\s]?invoice|threshold|cumulative (?:invoice|approval)"
            r"|policy bypass|approval limit",
            re.I,
        ),
    ),
)


def load_baseline() -> dict[str, Any]:
    from src.llm.agents.finance.leakage.tools.leakage_data import (
        get_payment_leakage_snapshot,
    )

    return get_payment_leakage_snapshot()


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def detect_levers(title: str, spec: str) -> list[str]:
    for text in (title, spec):
        found = [
            (match.start(), lever)
            for lever, pattern in _LEVER_PATTERNS
            if (match := pattern.search(text or ""))
        ]
        if found:
            return [lever for _, lever in sorted(found)]
    return []


def _flagged(baseline: dict[str, Any], pattern: re.Pattern[str]) -> float:
    total = 0.0
    for row in baseline.get("anomalies") or []:
        kind = str(
            row.get("anomaly_type") or row.get("leakage_type") or ""
        ).strip()
        if pattern.search(kind):
            total += _num(
                row.get("amount_at_risk_idr_mn") or row.get("leakage_amount_idr_mn")
            )
    return total


def compute(title: str, spec: str, baseline: dict[str, Any]):
    from src.actions.impact import ComputedImpact

    levers = detect_levers(title, spec)
    if not levers:
        return None

    lever = levers[0]
    pattern, rate = _TARGETS[lever]
    exposure = _flagged(baseline, pattern)
    if not exposure:
        return None

    recovered = round(exposure * rate, 1)
    before = round(exposure, 1)
    after = round(before - recovered, 1)
    basis = {
        BLOCK: "blocked before payment",
        DUPLICATE: "duplicate claw-back",
        OVERBILL: "overbilling claw-back",
        SPLIT: "stopped at approval",
    }[lever]
    line = (
        f"Exposure: {before:,.1f} {after - before:+,.1f} -> {after:,.1f} "
        f"(IDR mn · {basis} at {rate:.0%})"
    )
    return ComputedImpact(
        line=line,
        magnitude=recovered,
        # Sized from the flagged rows themselves, each of which names an
        # invoice and a vendor.
        traceable=True,
        # Money already out of the door has to be negotiated back. A block and
        # a threshold control both stop it before it leaves, so neither is
        # limited by anyone else's willingness to pay.
        capped=lever not in (BLOCK, SPLIT),
        levers=(lever,),
    )


__all__ = ["AGENTS", "LEAKAGE_AGENTS", "compute", "detect_levers", "load_baseline"]
