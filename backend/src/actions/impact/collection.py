"""Collection impact, sized from the ranked worklist.

The worklist is the one collections table that ships finished: each row names
a customer and carries the cash that customer is expected to release and the
DSO days that releases. So a chase action can be sized from the rows it would
actually touch, and the resulting line can name them — the same standard the
Treasury deferral meets by naming AP-000579.

Two units are reported because collections is judged on both, but they are
kept on separate legs. Mixing cash and days into one before/after is the
defect QC-005 reports on the Treasury side.
"""

from __future__ import annotations

import re
from typing import Any

COLLECTION_AGENTS = frozenset({"finance.collection", "collection", "collections"})
AGENTS = COLLECTION_AGENTS

ESCALATE = "escalate"
HOLD = "hold"
SETTLE = "settle"

# How many worklist rows each lever reaches. "Top 5 by priority" is the
# dashboard's own phrase for the same slice (QC-008), so the two surfaces
# cannot drift apart on what "top 5" means.
_REACH = {ESCALATE: 5, HOLD: 3, SETTLE: 2}

_LEVER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        ESCALATE,
        re.compile(
            r"escalat\w+|chase|dunn\w+|follow[-\s]?up|collection sprint"
            r"|recovery|concentration|outreach|campaign|restructur\w+"
            r"|intensif\w+|accelerat\w+ (?:settlement|collection)",
            re.I,
        ),
    ),
    (
        HOLD,
        re.compile(
            r"credit (?:hold|freeze|limit|tighten\w*)|prepayment|stop supply"
            r"|block\w* (?:new )?orders",
            re.I,
        ),
    ),
    (
        SETTLE,
        re.compile(r"settle\w*|discount|payment plan|instal\w+", re.I),
    ),
)


def load_baseline() -> dict[str, Any]:
    from src.llm.agents.finance.collection.tools.collection_data import (
        get_collections_snapshot,
    )

    return get_collections_snapshot()


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


def _summary(baseline: dict[str, Any]) -> dict[str, Any]:
    summary = baseline.get("summary")
    if isinstance(summary, list):
        return summary[0] if summary else {}
    return summary or {}


def compute(title: str, spec: str, baseline: dict[str, Any]):
    from src.actions.impact import ComputedImpact

    levers = detect_levers(title, spec)
    worklist = baseline.get("worklist") or []
    if not levers or not worklist:
        return None

    lever = levers[0]
    rows = worklist[: _REACH[lever]]
    freed = sum(_num(r.get("expected_recovery_idr_mn")) for r in rows)
    days = sum(_num(r.get("dso_days_released")) for r in rows)
    if not freed:
        return None

    summary = _summary(baseline)
    overdue = _num(summary.get("overdue_ar_idr_mn"))
    dso = _num(summary.get("current_dso_days"))
    if not overdue or not dso:
        return None

    # Rounded endpoints first, then the delta from them, so the figures add up
    # at the precision they are shown at. Same rule as treasury._leg.
    overdue_before, overdue_after = round(overdue, 1), round(overdue - freed, 1)
    dso_before, dso_after = round(dso, 1), round(dso - days, 1)
    names = ", ".join(
        str(r.get("customer_name") or "").strip() for r in rows if r.get("customer_name")
    )
    line = (
        f"Overdue AR: {overdue_before:,.1f} "
        f"{overdue_after - overdue_before:+,.1f} -> {overdue_after:,.1f} IDR mn · "
        f"DSO: {dso_before:,.1f} {dso_after - dso_before:+,.1f} -> {dso_after:,.1f} days "
        f"({len(rows)} accounts · {names})"
    )
    return ComputedImpact(
        line=line,
        magnitude=freed,
        # Every figure came from named worklist rows.
        traceable=bool(names),
        # A settlement buys the cash with a discount the worklist does not
        # price, so its nominal recovery is the optimistic end of the range.
        capped=lever == SETTLE,
        levers=(lever,),
    )


__all__ = [
    "AGENTS",
    "COLLECTION_AGENTS",
    "compute",
    "detect_levers",
    "load_baseline",
]
