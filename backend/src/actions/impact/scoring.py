"""Rank actions and state how much to trust each one.

QC-061 wants a next best action; QC-055 wants every action to carry a
confidence with its basis. Both need the same thing first: a number that does
not move between monitoring runs.

So neither is asked of the model. The model proposes the actions and writes
the sentence explaining why one comes first — that judgement is the point of
having an agent. Every figure underneath it is derived here, from the
simulator, on the read path. A score written into `chat.actions` would last
exactly until the next Recalculate rewrites the table.

Confidence is not a probability and does not pretend to be one. It reports
three facts about how the number was produced, and the wording says which:

    traceable   sized from a named row (an invoice, a customer, a vendor)
                rather than from a blended assumption
    uncapped    the book does not limit the action below its nominal effect
    computed    derived from the simulator at all, rather than left as the
                sentence the model wrote when the action was seeded
"""

from __future__ import annotations

import re
from typing import Any

HIGH, MEDIUM, LOW = "high", "medium", "low"

# What each band is worth when ranking. A big number nobody can source should
# not outrank a smaller one tied to a named invoice, which is why confidence
# carries real weight rather than being decoration on the card.
_BAND_WEIGHT = {HIGH: 1.0, MEDIUM: 0.6, LOW: 0.3}

# Size decides most of the order, but not all of it.
_MAGNITUDE_WEIGHT = 0.6
_CONFIDENCE_WEIGHT = 0.4


# A sentence carrying a figure is the one thing the model's reason may not do.
# Two numbers for the same thing on the same card is exactly the confusion
# QC-011, QC-016 and QC-032 each report, and the model's copy is the one that
# is regenerated on every run, so it is the one that goes.
_HAS_FIGURE = re.compile(r"\d")
# Split on sentence ends, keeping the terminator, so a clean sentence survives
# a neighbour that quoted a number.
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")


def clean_reason(reason: str | None) -> str | None:
    """The model's justification with any figure-bearing sentence removed.

    Dropping whole sentences rather than the digits inside them: "recovers
    3,139 mn of exposure" with the number cut out becomes "recovers of
    exposure", which reads like a bug and is worse than saying less. If every
    sentence quotes a figure, nothing is returned and the card shows the
    computed lines alone.
    """
    if not reason:
        return None
    kept = [
        sentence.strip()
        for sentence in _SENTENCE.findall(reason)
        if sentence.strip() and not _HAS_FIGURE.search(sentence)
    ]
    return " ".join(kept) or None


def confidence_of(computed) -> tuple[str, str]:
    """The band for one computed impact, and the sentence that justifies it.

    `computed` is a ComputedImpact. Actions with none are handled by the
    caller: an impact that was never computed cannot be graded on how it was
    computed, and is reported as such rather than as low confidence.
    """
    if computed.traceable and not computed.capped:
        return HIGH, (
            "computed from the live book, sized from named rows, "
            "and not limited by any book constraint"
        )
    if computed.traceable:
        return MEDIUM, (
            "computed from the live book and sized from named rows, but "
            "the book limits it below its nominal effect"
        )
    if not computed.capped:
        return MEDIUM, (
            "computed from the live book, but sized from a blended "
            "assumption rather than a named row"
        )
    return LOW, (
        "computed from the live book, but sized from a blended assumption "
        "and limited by the book"
    )


def rank(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score and order one agent's actions, best first.

    Magnitudes are normalised against the strongest action *of the same
    agent*. Treasury moves headroom, Finance moves EBITDA, Collection moves
    days and cash — comparing those raw would rank agents, not actions, so no
    cross-agent ordering is implied and none should be read into it.
    """
    scored = [item for item in items if isinstance(item.get("score_magnitude"), float)]
    top = max((item["score_magnitude"] for item in scored), default=0.0)

    for item in items:
        magnitude = item.get("score_magnitude")
        band = item.get("confidence")
        if not isinstance(magnitude, float) or band not in _BAND_WEIGHT:
            # Nothing was computed for this one. It keeps its stored wording
            # and sorts last, but it is not deleted: a monitoring agent
            # proposing "improve visibility" is making a real point that
            # simply has no cash lever behind it.
            item["score"] = 0.0
            continue
        relative = magnitude / top if top else 0.0
        item["score"] = round(
            _MAGNITUDE_WEIGHT * relative + _CONFIDENCE_WEIGHT * _BAND_WEIGHT[band],
            4,
        )

    # Ties are common and not a flaw: several actions genuinely pull the same
    # lever at the same size, which is QC-021/QC-023 showing through rather
    # than a scoring bug. But "next best" must not change between runs, and
    # the rows arrive in whatever order the last monitoring run wrote them, so
    # the tie is broken on the action name — arbitrary, and reproducible.
    items.sort(key=lambda item: (-(item.get("score") or 0.0), str(item.get("action") or "")))
    for position, item in enumerate(items, start=1):
        item["rank"] = position
    return items


__all__ = ["HIGH", "LOW", "MEDIUM", "clean_reason", "confidence_of", "rank"]
