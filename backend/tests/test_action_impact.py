"""QC-004 and QC-005: the impact line on a Treasury action card.

Both findings are about the same sentence. QC-004 says a Week 5 deferral is
shown raising Week 6 headroom, hiding what the relief costs. QC-005 says a
comparison opens on headroom and closes on closing cash, so the minimum buffer
reads as if the action produced it.

These tests run against the real simulator (`cashflow/service.py:simulate`) but
a fixture forecast, so they hold whatever is in the database. The fixture uses
the figures the findings were written against: Week 5 headroom -1,002.5, Week 6
+1,012.5, minimum buffer 8,000, one deferrable payable of 3,000.
"""

from __future__ import annotations

import re

import pytest

from src.actions import impact
from src.llm.agents.finance.treasury.cashflow.models import (
    CashFlowBaselineResponse,
    CashFlowDriver,
    CashFlowSimulationRequest,
    CashFlowSimulationResponse,
    WeeklyCashPosition,
)

MINIMUM_BUFFER = 8000.0

# Week 5 is the shortfall week the findings are written about.
CLOSING_CASH = {
    5: 6997.5,
    6: 9012.5,
    7: 21112.5,
}


def week(number: int) -> WeeklyCashPosition:
    closing = CLOSING_CASH[number]
    return WeeklyCashPosition(
        week_number=number,
        opening_cash_idr_mn=closing,
        closing_cash_idr_mn=closing,
        minimum_buffer_idr_mn=MINIMUM_BUFFER,
        headroom_idr_mn=closing - MINIMUM_BUFFER,
        status="Below buffer" if closing < MINIMUM_BUFFER else "OK",
    )


@pytest.fixture
def baseline() -> CashFlowBaselineResponse:
    return CashFlowBaselineResponse(
        import_batch_id=2,
        workbook_name="fixture",
        weekly_positions=[week(5), week(6), week(7)],
        minimum_buffer_idr_mn=MINIMUM_BUFFER,
        net_usd_exposure=3_300_000,
        recommended_hedge_usd=2_000_000,
        spot_rate_idr_per_usd=17950,
        forward_rate_idr_per_usd=18120,
        adverse_rate_idr_per_usd=18488.5,
        customer_delay_driver=CashFlowDriver(
            reference_number="AR-012",
            counterparty_name="PT Anugerah Prima",
            amount_idr_mn=8000,
            original_week=5,
            expected_week=7,
        ),
        deferrable_payment_driver=CashFlowDriver(
            reference_number="AP-015",
            counterparty_name="PT Kemasan Prima",
            amount_idr_mn=3000,
            payment_week=5,
            is_deferrable=True,
        ),
    )


@pytest.fixture
def simulate(baseline):
    """The production simulator, fed the fixture forecast instead of the DB."""
    from src.llm.agents.finance.treasury.cashflow.service import (
        simulate_with_baseline,
    )

    def run(request: CashFlowSimulationRequest) -> CashFlowSimulationResponse:
        return simulate_with_baseline(request, baseline)

    return run


def line_for(title, spec, baseline, simulate) -> str:
    computed = impact.compute_impact(
        title=title, spec=spec, baseline=baseline, simulate=simulate
    )
    assert computed is not None, f"no impact computed for {title!r}"
    return computed


def legs(line: str) -> dict[int, tuple[float, float, float]]:
    """Parse 'Week N headroom: before +delta -> after' back into numbers."""
    found = {}
    pattern = re.compile(
        r"Week (\d+) headroom: (-?[\d,]+\.\d) ([+-][\d,]+\.\d) -> ([+-][\d,]+\.\d)"
    )
    for match in pattern.finditer(line):
        found[int(match.group(1))] = tuple(
            float(match.group(index).replace(",", "")) for index in (2, 3, 4)
        )
    return found


# ---------------------------------------------------------------------------
# QC-004 — a deferral must cost the week it moves into
# ---------------------------------------------------------------------------


def test_deferral_lowers_week_six_headroom(baseline, simulate):
    line = line_for(
        "Defer deferrable Week 5 payable",
        "Move AP-015 from Week 5 to Week 6 within agreed terms.",
        baseline,
        simulate,
    )
    parsed = legs(line)

    assert parsed[5] == (-1002.5, 3000.0, 1997.5)
    assert parsed[6] == (1012.5, -3000.0, -1987.5)


def test_deferral_states_both_weeks(baseline, simulate):
    """The trade-off is the point: relief alone is what QC-004 reported."""
    line = line_for(
        "Rephase deferrable Week 5 payables",
        "Move AP-015 PT Kemasan Prima from Week 5 to Week 6.",
        baseline,
        simulate,
    )
    assert set(legs(line)) == {5, 6}


def test_acceleration_costs_the_week_it_pulls_from(baseline, simulate):
    """Pulling AR-012 forward out of Week 7 has to show Week 7 giving it up."""
    line = line_for(
        "Accelerate PT Anugerah Prima collection",
        "Target AR-012 for expedited payment before Week 5 close.",
        baseline,
        simulate,
    )
    parsed = legs(line)

    assert parsed[5] == (-1002.5, 8000.0, 6997.5)
    assert parsed[7] == (13112.5, -8000.0, 5112.5)


# ---------------------------------------------------------------------------
# QC-005 — one metric, one unit, arithmetic that closes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "spec"),
    [
        ("Defer deferrable Week 5 payable", "Move AP-015 into Week 6."),
        ("Accelerate PT Anugerah Prima collection", "Pull AR-012 forward."),
        ("Pre-arrange contingent liquidity", "Secure standby revolving credit."),
        ("Reschedule deferrable Week 5 vendor payment", "Move AP-015."),
    ],
)
def test_every_leg_closes_arithmetically(title, spec, baseline, simulate):
    line = line_for(title, spec, baseline, simulate)
    for week_number, (before, delta, after) in legs(line).items():
        assert before + delta == pytest.approx(after), (
            f"Week {week_number} does not close: {before} {delta:+} != {after}"
        )


@pytest.mark.parametrize(
    ("title", "spec"),
    [
        ("Defer deferrable Week 5 payable", "Move AP-015 into Week 6."),
        ("Accelerate PT Anugerah Prima collection", "Pull AR-012 forward."),
    ],
)
def test_a_leg_labelled_headroom_carries_headroom(title, spec, baseline, simulate):
    """QC-005: a line labelled headroom must not close on closing cash.

    Note the trap this dataset sets. AR-012 is 8,000 and the minimum buffer is
    8,000, so accelerating it moves Week 5 headroom from -1,002.5 to +6,997.5 —
    and 6,997.5 is also Week 5 closing cash. "Delta equals the buffer" cannot
    tell the two apart here. The figures are checked against the simulator
    instead, which is the only thing that settles it.
    """
    request = impact.build_request(title, spec, baseline)
    assert request is not None
    result = simulate(request)

    simulated_headroom = {
        5: result.week5_headroom_idr_mn,
        6: result.week6_headroom_idr_mn,
        7: result.week7_headroom_idr_mn,
    }
    simulated_cash = {
        5: result.week5_cash_idr_mn,
        6: result.week6_cash_idr_mn,
        7: result.week7_cash_idr_mn,
    }

    for week_number, (before, _, after) in legs(line_for(
        title, spec, baseline, simulate
    )).items():
        assert before == pytest.approx(
            CLOSING_CASH[week_number] - MINIMUM_BUFFER
        ), f"Week {week_number} opens on something other than baseline headroom"
        assert after == pytest.approx(simulated_headroom[week_number])
        assert after != pytest.approx(simulated_cash[week_number]), (
            f"Week {week_number} closes on closing cash, not headroom"
        )


def test_line_names_its_unit_and_instrument(baseline, simulate):
    line = line_for(
        "Defer deferrable Week 5 payable", "Move AP-015.", baseline, simulate
    )
    assert "(IDR mn" in line
    assert "AP-015" in line


# ---------------------------------------------------------------------------
# Lever detection — the only thing still read from model-written wording
# ---------------------------------------------------------------------------


def test_title_wins_over_spec_when_both_name_a_lever(baseline):
    """A spec listing alternatives must not override an unambiguous title."""
    levers = impact.detect_levers(
        "Defer Week 5 vendor payment",
        "Accelerate AR-012 or arrange a standby credit line.",
    )
    assert set(levers) == {impact.DEFER}


def test_alternatives_in_a_spec_collapse_to_the_first(baseline):
    """'A or B' is one choice; charging the forecast for both invents cash."""
    levers = impact.detect_levers(
        "Bridge Week 5 funding gap",
        "Accelerate collection of AR-012 or arrange a standby credit line.",
    )
    assert set(levers) == {impact.ACCELERATE}


def test_advice_without_a_cash_lever_computes_nothing(baseline, simulate):
    """Better no number than an invented one — the other half of QC-005."""
    assert (
        impact.compute_impact(
            title="Stage collections and payables by confirmed receipt timing",
            spec="Release payments only after customer remittance confirmation.",
            baseline=baseline,
            simulate=simulate,
        )
        is None
    )


def test_stored_wording_is_kept_when_nothing_can_be_computed(baseline, simulate):
    items = [
        {
            "agent": "finance.treasury",
            "action": "Stage collections by confirmed receipt timing",
            "spec": "Release payments after remittance confirmation.",
            "impact": "volatility: Week5-7 reduced",
        }
    ]
    impact.apply_computed_impact(items, baseline=baseline, simulate=simulate)

    assert items[0]["impact"] == "volatility: Week5-7 reduced"
    assert items[0]["impact_source"] == "stored"


def test_other_agents_are_left_alone(baseline, simulate):
    items = [
        {
            "agent": "finance.finance",
            "action": "Defer Week 5 payable",
            "spec": "Move AP-015.",
            "impact": "EBITDA%: 9.2% +2pts -> 11.2%",
        }
    ]
    impact.apply_computed_impact(items, baseline=baseline, simulate=simulate)

    assert items[0]["impact"] == "EBITDA%: 9.2% +2pts -> 11.2%"
    assert "impact_source" not in items[0]


def test_replacement_keeps_the_original_for_review(baseline, simulate):
    items = [
        {
            "agent": "finance.treasury",
            "action": "Defer deferrable Week 5 payable",
            "spec": "Move AP-015 into Week 6.",
            "impact": "week6 headroom: 1012.5 +3000 -> 4012.5",
        }
    ]
    impact.apply_computed_impact(items, baseline=baseline, simulate=simulate)

    assert items[0]["impact_stored"] == "week6 headroom: 1012.5 +3000 -> 4012.5"
    assert items[0]["impact_source"] == "computed"
    assert "-1,987.5" in items[0]["impact"]
