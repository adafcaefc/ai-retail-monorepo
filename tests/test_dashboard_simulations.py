"""Unit checks for dashboard finance / leakage math."""

from src.llm.dashboard_payload import (
    simulate_finance_scenario,
    simulate_leakage_scenario,
)


def test_finance_base_margin_matches_mockup():
    result = simulate_finance_scenario()
    # Mockup displays one decimal (9.2%); exact model is 9.25%.
    assert round(result["stats"]["scenario_margin_pct"], 1) == 9.2
    assert result["stats"]["ebitda_idr_mn"] == 4300.0
    assert result["baseline"]["rev"] == 46510.0


def test_finance_price_up_improves_margin():
    base = simulate_finance_scenario()
    up = simulate_finance_scenario(price=4, scope="fx")
    assert up["stats"]["scenario_margin_pct"] > base["stats"]["scenario_margin_pct"]
    assert up["stats"]["ebitda_idr_mn"] > base["stats"]["ebitda_idr_mn"]


def test_leakage_hold_math():
    result = simulate_leakage_scenario(
        hold=3800,
        dup_rec=95,
        ov_rec=90,
        duplicates_amount=3050,
        overbill_amount=400,
        other_blocked=500,
        at_risk=7845,
    )
    assert result["blocked"] == 4300
    assert result["recovered"] == 3050 * 0.95 + 400 * 0.9
    assert result["total_protected"] == result["blocked"] + result["recovered"]
