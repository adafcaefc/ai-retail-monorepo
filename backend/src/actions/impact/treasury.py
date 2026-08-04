"""Recompute a Treasury action's impact line from the live cash-flow forecast.

QC-004 and QC-005 share one cause: `chat.actions.impact` stores a sentence the
model wrote when the action was seeded, and nothing ever checked it against the
forecast. Two ways it goes wrong, both reproducible today:

  QC-004  "week6 headroom: 1012.5 +3000 -> 4012.5" — moving a Week 5 payment
          into Week 6 must *lower* Week 6 headroom, to -1,987.5. The card shows
          the relief and hides the cost, so the trade-off disappears.

  QC-005  "headroom: -1002.5 -> +6997.5" — the line opens on headroom and
          closes on closing cash. The apparent 8,000 gain is exactly the
          minimum buffer, because headroom = closing cash - buffer. The action
          reads as if it conjured the buffer out of nothing.

Correcting the stored sentences would fix today's numbers and be wrong again on
the next dataset — and on the next monitoring run, which regenerates the whole
table. So this module derives the line instead. The wording is read only to
decide *which levers* an action pulls; every figure comes from
`cashflow/service.py:simulate`, whose arithmetic already models the trade-off
correctly (Week 5 gains the deferral, Week 6 pays for it).

Every rendered line obeys four rules:

  1. one metric per line
  2. one unit per line, named
  3. before + delta == after
  4. a lever that helps one week at another week's expense states both weeks

Two boundaries worth stating plainly:

  * Lever *sizes* come from the forecast, not from the wording. An action that
    proposes a partial move ("collect at least IDR 5,000mn") is still shown at
    the forecast's full lever, because sizing a claim from regenerated prose is
    what produced these findings. Partial sizing belongs to QC-017.
  * Actions with no identifiable cash lever (pure "reduce volatility" advice)
    keep their stored wording. Inventing a number for them would repeat the
    original mistake in the other direction.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from src.llm.agents.finance.treasury.cashflow.models import (
    CashFlowBaselineResponse,
    CashFlowSimulationRequest,
    CashFlowSimulationResponse,
)

# Agent keys that reach the Treasury forecast. The canonical id is
# `finance.treasury`; the others are older keys still present in chat.actions.
TREASURY_AGENTS = frozenset({"finance.treasury", "treasury", "cashflow"})

DEFER = "defer"
ACCELERATE = "accelerate"
CREDIT = "credit"
HEDGE = "hedge"

# Deliberately narrow. A lever is only claimed when the wording names the
# mechanism, not merely the symptom it addresses.
LEVER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        DEFER,
        re.compile(
            r"defer|reschedul|rephase|reprofil\w+|re-?time"
            r"|renegotiat\w*\s+\w*\s*timing"
            r"|move\s+\S+\s+.{0,30}payment|week\s*5\s*to\s*week\s*6"
            r"|synchroniz\w+\s+outbound",
            re.I,
        ),
    ),
    (
        ACCELERATE,
        re.compile(
            r"accelerat|expedit|collect\s+at\s+least|partial\s+advance"
            r"|pay\s+earlier|earlier\s+payment",
            re.I,
        ),
    ),
    (
        CREDIT,
        re.compile(
            # "revolver" and "revolving" are the same instrument and the
            # monitoring model uses both; matching only one left a real draw
            # action unsized and bottom-ranked.
            r"credit[-\s]?line|standby|revolv\w+|contingent\s+"
            r"(?:liquidity|credit|capacity)",
            re.I,
        ),
    ),
    (
        HEDGE,
        re.compile(r"hedg\w+|forward\s+contract|collar", re.I),
    ),
)

# Levers listed as alternatives ("accelerate ... or draw ...") are one choice,
# not a combined plan. Summing them would invent liquidity.
ALTERNATIVE_PATTERN = re.compile(r"\bor\b", re.I)


def _signed(value: float) -> str:
    return f"{value:+,.1f}"


def _plain(value: float) -> str:
    return f"{value:,.1f}"


def _matches_in(text: str) -> list[tuple[int, str, re.Pattern[str]]]:
    """Levers named in `text`, in the order they are written."""
    found = []
    for lever, pattern in LEVER_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            found.append((match.start(), lever, pattern))
    return sorted(found)


def detect_levers(title: str, spec: str) -> dict[str, re.Pattern[str]]:
    """Which levers an action pulls, keyed by lever name.

    The title is checked first: it names the mechanism in one phrase, while a
    spec often lists several. Only when the title names no mechanism does the
    spec decide — and there, levers offered as alternatives collapse to the
    first, because "accelerate the receivable or defer the payable" is one
    choice and charging the forecast for both invents liquidity.
    """
    from_title = _matches_in(title)
    if from_title:
        return {lever: pattern for _, lever, pattern in from_title}

    from_spec = _matches_in(spec)
    if len(from_spec) > 1:
        first_end = from_spec[0][0]
        second_start = from_spec[1][0]
        if ALTERNATIVE_PATTERN.search(spec, first_end, second_start):
            from_spec = from_spec[:1]

    return {lever: pattern for _, lever, pattern in from_spec}


def lever_sizes(baseline: CashFlowBaselineResponse) -> dict[str, float]:
    """What each lever is worth in this forecast.

    Sizes come from the forecast, never from the action wording. The wording is
    model-written and is regenerated on every monitoring run — reading a figure
    out of it reintroduces the very defect QC-004 and QC-005 report. The
    forecast is unambiguous: it holds exactly one deferrable payable and one
    delayed receivable, and a credit draw exists to close the shortfall.
    """
    shortfall = max(
        0.0,
        -min(
            (week.headroom_idr_mn for week in baseline.weekly_positions),
            default=0.0,
        ),
    )
    return {
        DEFER: baseline.deferrable_payment_driver.amount_idr_mn,
        ACCELERATE: baseline.customer_delay_driver.amount_idr_mn,
        CREDIT: shortfall,
        HEDGE: min(baseline.recommended_hedge_usd, baseline.net_usd_exposure),
    }


def build_request(
    title: str,
    spec: str,
    baseline: CashFlowBaselineResponse,
) -> CashFlowSimulationRequest | None:
    """Turn a detected lever set into simulator inputs, or None if none apply."""
    levers = detect_levers(title, spec)
    if not levers:
        return None

    sizes = lever_sizes(baseline)
    amounts = {lever: sizes[lever] for lever in levers}
    if not any(amounts.values()):
        return None

    return CashFlowSimulationRequest(
        accelerate_collection_idr_mn=amounts.get(ACCELERATE, 0.0),
        defer_payment_idr_mn=amounts.get(DEFER, 0.0),
        credit_line_draw_idr_mn=amounts.get(CREDIT, 0.0),
        hedge_usd=amounts.get(HEDGE, 0.0),
    )


def _week_headroom(
    baseline: CashFlowBaselineResponse,
    week_number: int,
) -> float:
    for week in baseline.weekly_positions:
        if week.week_number == week_number:
            return week.headroom_idr_mn
    raise LookupError(f"Week {week_number} is not in the forecast.")


def _leg(week_number: int, before: float, after: float) -> str:
    """One week's move, printed so that the printed figures add up.

    QC-005. The line is read off a screen at one decimal place. Rounding
    `before`, the delta and `after` independently lets a fraction in each land
    them on different sides: -1,387.95 and -4,526.91 print as -1,388.0 and
    -4,526.9, while the -3,138.96 between them prints as -3,139.0 — so a CFO
    adding up what is on screen gets -4,527.0 and concludes the card is wrong.
    The arithmetic has to close at the precision it is shown at, so the delta
    is derived from the rounded endpoints instead of being rounded on its own.
    """
    before_shown = round(before, 1)
    after_shown = round(after, 1)
    delta_shown = round(after_shown - before_shown, 1)
    return (
        f"Week {week_number} headroom: {_plain(before_shown)} "
        f"{_signed(delta_shown)} -> {_signed(after_shown)}"
    )


def _provenance(
    baseline: CashFlowBaselineResponse,
    request: CashFlowSimulationRequest,
) -> str:
    """Name the instrument behind each figure, so the number can be traced."""
    parts: list[str] = []
    if request.defer_payment_idr_mn:
        parts.append(
            f"defer {baseline.deferrable_payment_driver.reference_number} "
            f"{_plain(request.defer_payment_idr_mn)}"
        )
    if request.accelerate_collection_idr_mn:
        parts.append(
            f"accelerate {baseline.customer_delay_driver.reference_number} "
            f"{_plain(request.accelerate_collection_idr_mn)}"
        )
    if request.credit_line_draw_idr_mn:
        parts.append(f"draw {_plain(request.credit_line_draw_idr_mn)}")
    if request.hedge_usd:
        parts.append(f"hedge USD {request.hedge_usd / 1_000_000:,.1f}mn")
    return ", ".join(parts)


def render(
    baseline: CashFlowBaselineResponse,
    request: CashFlowSimulationRequest,
    result: CashFlowSimulationResponse,
) -> str | None:
    """Render the simulated outcome as one closed, single-unit statement."""
    legs: list[str] = []

    week5_before = _week_headroom(baseline, 5)
    week5_delta = result.week5_headroom_idr_mn - week5_before
    if abs(week5_delta) >= 0.05:
        legs.append(_leg(5, week5_before, result.week5_headroom_idr_mn))

    # A deferral buys Week 5 relief with Week 6 headroom; an acceleration buys
    # it with Week 7. Naming only the week that improves is QC-004.
    for week_number, after in (
        (6, result.week6_headroom_idr_mn),
        (7, result.week7_headroom_idr_mn),
    ):
        before = _week_headroom(baseline, week_number)
        delta = after - before
        if abs(delta) >= 0.05:
            legs.append(_leg(week_number, before, after))

    if legs:
        return f"{' · '.join(legs)} (IDR mn · {_provenance(baseline, request)})"

    if request.hedge_usd > 0:
        # Same rule as _leg: the two figures on screen must produce the net
        # that is printed beside them, so net comes from the rounded pair.
        avoided_shown = round(result.fx_downside_avoided_idr_mn, 1)
        premium_shown = round(result.forward_premium_idr_mn, 1)
        net = round(avoided_shown - premium_shown, 1)
        return (
            f"FX downside avoided: {_plain(avoided_shown)} "
            f"less premium {_plain(premium_shown)} -> "
            f"net {_signed(net)} (IDR mn · "
            f"{_provenance(baseline, request)}, "
            f"{result.hedge_coverage_pct:,.0f}% coverage)"
        )

    return None


def compute_impact(
    *,
    title: str,
    spec: str,
    baseline: CashFlowBaselineResponse,
    simulate: Callable[
        [CashFlowSimulationRequest], CashFlowSimulationResponse
    ],
) -> str | None:
    """The impact line for one action, or None when no lever is identifiable."""
    request = build_request(title, spec, baseline)
    if request is None:
        return None
    return render(baseline, request, simulate(request))


def apply_computed_impact(
    items: list[dict[str, Any]],
    *,
    baseline: CashFlowBaselineResponse,
    simulate: Callable[
        [CashFlowSimulationRequest], CashFlowSimulationResponse
    ],
) -> list[dict[str, Any]]:
    """Replace stored Treasury impact lines with recomputed ones, in place.

    The stored wording is kept under `impact_stored` so a reviewer can see what
    changed, and `impact_source` says which one is on screen. Nothing is
    written back to the database: the correction lives on the read path, so the
    dataset stays exactly as imported.
    """
    for item in items:
        if str(item.get("agent") or "") not in TREASURY_AGENTS:
            continue
        computed = compute_impact(
            title=str(item.get("action") or ""),
            spec=str(item.get("spec") or ""),
            baseline=baseline,
            simulate=simulate,
        )
        if computed is None:
            item["impact_source"] = "stored"
            continue
        item["impact_stored"] = item.get("impact")
        item["impact"] = computed
        item["impact_source"] = "computed"
    return items


# ---------------------------------------------------------------------------
# Uniform adapter — the shape every agent answers to (see impact/__init__.py)
# ---------------------------------------------------------------------------

AGENTS = TREASURY_AGENTS

# A lever is traceable when the forecast sized it from a row someone can look
# up. `deferrable_payment_driver` points at a real payable (AP-000579);
# `customer_delay_driver` currently points at "NEWSALES", a rolled-up
# placeholder standing in for "the largest movable receipt". Both are honest
# sizes, but only one can be produced when a CFO asks which invoice. Anything
# without a digit in its reference is treated as the rollup it is.
_REAL_REFERENCE = re.compile(r"\d")


def load_baseline():
    """The forecast, read fresh. Imported late: `cashflow.service` pulls in the
    database layer, and `impact` is imported by module-level code in
    `actions.service`."""
    from src.llm.agents.finance.treasury.cashflow.service import get_baseline

    return get_baseline()


def compute(title: str, spec: str, baseline):
    """This action's effect on the forecast, or None if it names no lever.

    Shares `build_request`/`render` with the Treasury path above rather than
    recomputing anything: the number an action is ranked by has to be the same
    number printed on its card, or the order stops matching what is on screen.
    """
    from src.actions.impact import ComputedImpact
    from src.llm.agents.finance.treasury.cashflow.service import (
        simulate_with_baseline,
    )

    request = build_request(title, spec, baseline)
    if request is None:
        return None

    result = simulate_with_baseline(request, baseline)
    line = render(baseline, request, result)
    if line is None:
        return None

    levers = tuple(sorted(detect_levers(title, spec)))

    # Rank Treasury actions by how much they lift the week that breaches, which
    # is the only week the agent is asked about. A hedge moves no cash, so it
    # is ranked on the downside it removes net of the premium paid for it.
    week5_before = _week_headroom(baseline, 5)
    magnitude = abs(result.week5_headroom_idr_mn - week5_before)
    if not magnitude and request.hedge_usd:
        magnitude = abs(
            result.fx_downside_avoided_idr_mn - result.forward_premium_idr_mn
        )

    traceable = any(
        (
            request.defer_payment_idr_mn
            and _REAL_REFERENCE.search(
                baseline.deferrable_payment_driver.reference_number or ""
            ),
            request.accelerate_collection_idr_mn
            and _REAL_REFERENCE.search(
                baseline.customer_delay_driver.reference_number or ""
            ),
        )
    )

    # A hedge the book cannot fully cover, and a draw sized to the shortfall
    # rather than to a committed facility, are both limited by the book.
    capped = bool(
        (request.hedge_usd and baseline.recommended_hedge_usd
         > baseline.net_usd_exposure)
        or request.credit_line_draw_idr_mn
    )

    return ComputedImpact(
        line=line,
        magnitude=float(magnitude),
        traceable=bool(traceable),
        capped=capped,
        levers=levers,
    )


__all__ = [
    "ACCELERATE",
    "AGENTS",
    "CREDIT",
    "DEFER",
    "HEDGE",
    "TREASURY_AGENTS",
    "apply_computed_impact",
    "build_request",
    "compute",
    "compute_impact",
    "detect_levers",
    "load_baseline",
    "render",
]
