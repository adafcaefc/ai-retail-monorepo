"""Recomputed action impacts, one adapter per agent.

`treasury.py` came first and is the reference: an action's stored `impact` is a
sentence the model wrote when the action was seeded, so this layer reads the
wording only to decide *which levers* the action pulls and takes every figure
from that agent's own simulator. See its module docstring for why — QC-004 and
QC-005 are the worked examples.

The same split now applies to all four agents, because ranking actions needs a
number that does not move between monitoring runs (QC-061), and a confidence
level has to be derived from something checkable rather than asserted
(QC-055). Each adapter module exposes the same three names:

    AGENTS            the agent keys it answers for
    load_baseline()   that agent's baseline, read fresh
    compute(title, spec, baseline) -> ComputedImpact | None

`compute` returns None when an action names no lever this agent can size —
pure "improve visibility" advice keeps its stored wording rather than being
given an invented number.

Everything here lives on the read path and is never written back. That is not
because a monitoring run replaces `chat.actions` (it does not: populate_alerts
only ever appends, see `actions/service.py`) but because `chat.actions` only
grows, so a persisted score would drift stale the moment a later run added
context, and it would need to record which scope (e.g. status=planned) it was
ranked within to mean anything on a later read.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# The Treasury surface predates the package and is re-exported unchanged:
# `service.py` and `tests/test_action_impact.py` both address these names
# through `impact.<name>`, and the move to a package is meant to be invisible
# to them.
from src.actions.impact.treasury import (  # noqa: F401
    ACCELERATE,
    CREDIT,
    DEFER,
    HEDGE,
    LEVER_PATTERNS,
    TREASURY_AGENTS,
    apply_computed_impact,
    build_request,
    compute_impact,
    detect_levers,
    lever_sizes,
    render,
)


@dataclass(frozen=True)
class ComputedImpact:
    """One action's effect, derived from a simulator rather than from prose.

    `line` is what a reader sees. The other three fields exist so the action
    can be ranked and given a confidence without anyone re-parsing `line`:

      magnitude  how much this action moves, in that agent's own unit. Only
                 ever compared with other actions of the same agent, so no
                 cross-agent normalisation is implied or safe.
      traceable  the lever was sized from a named row in the ledger (an
                 invoice, a customer, a vendor) rather than from a blended
                 assumption. The strongest confidence signal available.
      capped     the lever hit a limit the book imposes, so the action cannot
                 deliver its full nominal effect.
    """

    line: str
    magnitude: float
    traceable: bool
    capped: bool
    levers: tuple[str, ...]


def _adapters():
    """The per-agent adapters, imported on first use.

    Late because each one reaches into its agent's data layer, and `impact` is
    imported at module level by `actions.service`; importing four data layers
    at import time turns a lightweight helper into the heaviest module in the
    process.
    """
    from src.actions.impact import collection, finance, leakage, treasury

    return (treasury, finance, collection, leakage)


def adapter_for(agent: str):
    """The adapter that answers for `agent`, or None."""
    key = str(agent or "")
    for module in _adapters():
        if key in module.AGENTS:
            return module
    return None


def enrich_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a computed impact, a confidence and a rank to every action.

    Ordering happens per agent, because the magnitudes are in each agent's own
    unit (see `scoring.rank`). A caller that asked for one agent therefore
    gets exactly what it expects; a caller that asked for everything gets each
    agent's list ranked within itself.

    Nothing here is written back to the database. `chat.actions` only grows
    now (populate_alerts appends; nothing deletes it), so a stored rank would
    need to say which scope it was computed within to stay meaningful — the
    same reasoning that put the Treasury impact correction on the read path
    in the first place.
    """
    from src.actions.impact import scoring

    by_agent: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_agent.setdefault(str(item.get("agent") or ""), []).append(item)

    ordered: list[dict[str, Any]] = []
    for agent, group in by_agent.items():
        module = adapter_for(agent)
        baseline = None
        if module is not None:
            try:
                baseline = module.load_baseline()
            except Exception:  # noqa: BLE001
                # Loud, not silent: an agent whose baseline will not load
                # serves stored wording, and the log says which and why.
                # Swallowing this is what hid QC-004/QC-005 for a release.
                logger.exception(
                    "Baseline unavailable for %s; serving stored impacts", agent
                )

        for item in group:
            item.setdefault("impact_source", "stored")
            # The model keeps the sentence; the ledger keeps the numbers.
            item["reason"] = scoring.clean_reason(item.get("reason"))
            if baseline is None:
                continue
            try:
                computed = module.compute(
                    str(item.get("action") or ""),
                    str(item.get("spec") or ""),
                    baseline,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Impact computation failed for %r", item.get("action")
                )
                continue
            if computed is None:
                continue
            item["impact_stored"] = item.get("impact")
            item["impact"] = computed.line
            item["impact_source"] = "computed"
            item["score_magnitude"] = float(computed.magnitude)
            item["levers"] = list(computed.levers)
            band, basis = scoring.confidence_of(computed)
            item["confidence"] = band
            item["confidence_basis"] = basis

        ordered.extend(scoring.rank(group))

    return ordered


__all__ = [
    "ACCELERATE",
    "CREDIT",
    "ComputedImpact",
    "DEFER",
    "HEDGE",
    "LEVER_PATTERNS",
    "TREASURY_AGENTS",
    "adapter_for",
    "apply_computed_impact",
    "build_request",
    "compute_impact",
    "detect_levers",
    "enrich_actions",
    "lever_sizes",
    "render",
]
