"""Contract checks between dashboard payloads and the frontend info registry.

The frontend opens an explanation card for every clickable board element,
keyed by `tile:<kpi.id>`, `view:<viewKey>`, `side:top|bottom`. Those keys live
in frontend/src/infoRegistry.js. If a payload gains or renames an element and
the registry is not updated, the card silently stops appearing.

These tests build every payload from fixtures (no DB) and assert the two sides
still agree, plus the arithmetic of the charts rebuilt from the v9.4 mockup.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.llm.agents.finance.collection.dashboard import _collections_dashboard
from src.llm.agents.finance.finance.dashboard import _finance_dashboard
from src.llm.agents.finance.leakage.dashboard import (
    _leakage_dashboard,
    simulate_leakage_scenario,
)
from src.llm.agents.finance.treasury.dashboard import _treasury_dashboard

REGISTRY = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "infoRegistry.js"
)


# ---------------------------------------------------------------------------
# Fixtures — shaped like the real snapshots, small enough to reason about
# ---------------------------------------------------------------------------


def collections_snapshot() -> dict:
    return {
        "summary": {
            "total_ar_idr_mn": 110000,
            "overdue_ar_idr_mn": 37935,
            "overdue_percentage": 34.5,
            "current_dso_days": 57.4,
            "target_dso_days": 47,
            "cash_freed_at_target_idr_mn": 19863,
            # The provision is what we set aside; the High tier's exposure
            # (5,000 below) is what is actually at risk. Different numbers.
            "high_risk_provision_idr_mn": 2500,
            "current_ar_idr_mn": 72065,
            "daily_credit_sales_idr_mn": 1918,
        },
        "customers": [
            {
                "current_idr_mn": 72065,
                "overdue_1_30_idr_mn": 12000,
                "overdue_31_60_idr_mn": 13500,
                "overdue_61_90_idr_mn": 9500,
                "overdue_90_plus_idr_mn": 2935,
            }
        ],
        # Tiers partition the whole AR book, not just the overdue slice.
        "risk_tiers": [
            {"risk_tier": "Low", "exposure_idr_mn": 65500},
            {"risk_tier": "Medium", "exposure_idr_mn": 39500},
            {"risk_tier": "High", "exposure_idr_mn": 5000},
        ],
        "worklist": [
            {
                "customer_name": "PT Anugerah Prima (A)",
                "overdue_idr_mn": 10000,
                "oldest_aging_bucket": "31-60",
                "risk_tier": "Medium",
                "expected_recovery_idr_mn": 8500,
            },
            {
                "customer_name": "PT Sumber Makmur",
                "overdue_idr_mn": 6500,
                "oldest_aging_bucket": "61-90",
                "risk_tier": "Medium",
                "expected_recovery_idr_mn": 5525,
            },
            {
                "customer_name": "CV Berkah Jaya",
                "overdue_idr_mn": 3500,
                "oldest_aging_bucket": "90+",
                "risk_tier": "High",
                "expected_recovery_idr_mn": 1400,
            },
            {
                "customer_name": "PT Karya Abadi",
                "overdue_idr_mn": 3500,
                "oldest_aging_bucket": "31-60",
                "risk_tier": "Low",
                "expected_recovery_idr_mn": 3325,
            },
            {
                "customer_name": "CV Toko Sejahtera",
                "overdue_idr_mn": 3000,
                "oldest_aging_bucket": "61-90",
                "risk_tier": "Medium",
                "expected_recovery_idr_mn": 2550,
            },
            {
                "customer_name": "PT Enam",
                "overdue_idr_mn": 1500,
                "oldest_aging_bucket": "1-30",
                "risk_tier": "Low",
                "expected_recovery_idr_mn": 1425,
            },
        ],
    }


def treasury_baseline() -> dict:
    return {
        "minimum_buffer_idr_mn": 8000,
        "net_usd_exposure": 3_300_000,
        "recommended_hedge_usd": 2_000_000,
        "spot_rate_idr_per_usd": 17950,
        "adverse_rate_idr_per_usd": 18488.5,  # +3%
        "weekly_positions": [
            {
                "week_number": w,
                "closing_cash_idr_mn": v,
                "headroom_idr_mn": v - 8000,
            }
            for w, v in enumerate(
                [12000, 10800, 9600, 8200, 6698, 7400, 8900], start=1
            )
        ],
        "customer_delay_driver": {
            "counterparty_name": "PT Anugerah Prima",
            "amount_idr_mn": 8000,
            "expected_week": 5,
        },
        "deferrable_payment_driver": {
            "counterparty_name": "Osaka Precision KK",
            "amount_idr_mn": 3000,
            "payment_week": 5,
        },
    }


def leakage_snapshot() -> dict:
    """Mirrors payment_leakage.* column names exactly.

    An earlier version of this fixture invented `amount_idr_mn` /
    `total_at_risk_idr_mn`. The dashboard probed those same invented names, so
    the tests passed while every live chart resolved to zero. Keep these keys
    in sync with database-structure.md.
    """
    return {
        "summary": [
            {
                "invoices_scanned": 1850,
                "items_flagged": 10,
                "total_amount_at_risk_idr_mn": 7845,
                "blocked_before_payment_idr_mn": 4300,
                "recoverable_already_paid_idr_mn": 3450,
                "expected_recovered_idr_mn": 3257.5,
                "lost_this_cycle_idr_mn": 95,
                "total_cash_protected_idr_mn": 7557.5,
            }
        ],
        "category_breakdowns": [
            {
                "category_name": "Bank-change fraud",
                "amount_at_risk_idr_mn": 3800,
                "is_direct_loss": True,
            },
            {
                "category_name": "Duplicate payment",
                "amount_at_risk_idr_mn": 3050,
                "is_direct_loss": True,
            },
            {
                "category_name": "Overbilling (3-way)",
                "amount_at_risk_idr_mn": 900,
                "is_direct_loss": True,
            },
            {
                "category_name": "Lost discount",
                "amount_at_risk_idr_mn": 95,
                "is_direct_loss": True,
            },
            {
                "category_name": "Split / threshold",
                "amount_at_risk_idr_mn": 1950,
                "is_direct_loss": False,
            },
        ],
        "anomalies": [],
        "action_worklist": [
            {
                "vendor_name": "Osaka Precision KK",
                "anomaly_type": "Bank-change fraud",
                "amount_at_risk_idr_mn": 3800,
            },
            {
                "vendor_name": "Osaka Precision KK",
                "anomaly_type": "Overbilling (3-way)",
                "amount_at_risk_idr_mn": 500,
            },
            {
                "vendor_name": "Shenzhen Micro Ltd",
                "anomaly_type": "Duplicate payment",
                "amount_at_risk_idr_mn": 1850,
            },
            {
                "vendor_name": "PT Bahan Baku Lokal",
                "anomaly_type": "Duplicate payment",
                "amount_at_risk_idr_mn": 1200,
            },
            {
                "vendor_name": "Taipei Semicon Co",
                "anomaly_type": "Overbilling (3-way)",
                "amount_at_risk_idr_mn": 400,
            },
        ],
    }


def finance_snapshot() -> dict:
    """`kpis` and `variance_drivers` mirror financial_performance.* exactly.

    The opex rows deliberately use the looser `line_item` / `actual_idr_mn`
    shape: the live profit_summary carries no opex line items, so that path
    only ever runs for a batch that does, and it still needs covering.
    """
    return {
        "kpis": [
            {
                "metric_name": "Revenue (IDR mn)",
                "budget_value": 46000,
                "actual_value": 46510,
                "unit": "IDR million",
            },
            # Must not be mistaken for revenue.
            {
                "metric_name": "Revenue growth vs budget",
                "budget_value": 0,
                "actual_value": 0.01108696,
                "unit": "percentage",
            },
            {
                "metric_name": "Gross margin %",
                "budget_value": 0.30869565,
                "actual_value": 0.25327886,
                "unit": "percentage",
            },
            {
                "metric_name": "EBITDA (IDR mn)",
                "budget_value": 7200,
                "actual_value": 4300,
                "unit": "IDR million",
            },
            {
                "metric_name": "EBITDA %",
                "budget_value": 0.15652174,
                "actual_value": 0.09245324,
                "unit": "percentage",
            },
            # Also contains "revenue" — must not overwrite the revenue slot.
            {
                "metric_name": "Opex to revenue %",
                "budget_value": 0.15217391,
                "actual_value": 0.16082563,
                "unit": "percentage",
            },
        ],
        "variance_drivers": [
            {"driver_name": "Volume", "impact_idr_mn": 1341.11111111},
            {"driver_name": "Mix", "impact_idr_mn": -1491.11111111},
            {"driver_name": "Price", "impact_idr_mn": -390},
            {"driver_name": "Cost (input)", "impact_idr_mn": -1880},
            {"driver_name": "Operating cost", "impact_idr_mn": -480},
        ],
        "simulator_levers": [],
        "profit_summary": [
            {"line_item": "Payroll", "actual_idr_mn": 3300, "budget_idr_mn": 3200},
            {
                "line_item": "Logistics & freight",
                "actual_idr_mn": 1650,
                "budget_idr_mn": 1400,
            },
            {
                "line_item": "Rent & utilities",
                "actual_idr_mn": 920,
                "budget_idr_mn": 900,
            },
            {
                "line_item": "Marketing & selling",
                "actual_idr_mn": 850,
                "budget_idr_mn": 800,
            },
            {"line_item": "Other opex", "actual_idr_mn": 760, "budget_idr_mn": 700},
            # Must be filtered out — not an opex line.
            {"line_item": "Revenue", "actual_idr_mn": 46510, "budget_idr_mn": 46000},
        ],
    }


# Keyed by canonical `folder.agent` id — the same ids the frontend registry,
# the dashboard route and the alerts API use.
PAYLOADS = {
    "finance.collection": lambda: _collections_dashboard(collections_snapshot()),
    "finance.treasury": lambda: _treasury_dashboard(treasury_baseline()),
    "finance.finance": lambda: _finance_dashboard(finance_snapshot()),
    "finance.leakage": lambda: _leakage_dashboard(leakage_snapshot()),
}


# ---------------------------------------------------------------------------
# Registry parsing
# ---------------------------------------------------------------------------


def registry_keys() -> dict[str, set[str]]:
    """Pull the info keys per agent out of infoRegistry.js.

    Parsed rather than imported so the test needs no JS runtime. Only the
    top-level agent blocks and their quoted/bare keys are read.
    """

    source = REGISTRY.read_text(encoding="utf-8")
    body = source.split("export const INFO_REGISTRY = ", 1)[1]

    keys: dict[str, set[str]] = {}
    for agent in PAYLOADS:
        match = re.search(
            rf'\n  "{re.escape(agent)}": \{{(.*?)\n  \}},?\n', body, re.S
        )
        assert match, f"agent block {agent!r} not found in infoRegistry.js"
        block = match.group(1)
        found = set(re.findall(r'"([a-z]+:[^"]+)":', block))
        found |= {
            bare
            for bare in re.findall(r"^\s{4}(gauge|simchart):", block, re.M)
        }
        keys[agent] = found
    return keys


def expected_keys(payload: dict) -> set[str]:
    out = {f"tile:{k['id']}" for k in payload["kpis"]}
    out |= {f"view:{v}" for v in payload["views"]}
    for slot in payload.get("side") or {}:
        out.add(f"side:{slot}")
    return out


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent", sorted(PAYLOADS))
def test_every_board_element_has_an_info_entry(agent: str) -> None:
    payload = PAYLOADS[agent]()
    registered = registry_keys()[agent]
    missing = expected_keys(payload) - registered
    assert not missing, f"{agent}: board elements with no info card: {sorted(missing)}"


@pytest.mark.parametrize("agent", sorted(PAYLOADS))
def test_no_orphan_info_entries(agent: str) -> None:
    """Registry entries for elements that no longer exist would never show."""

    payload = PAYLOADS[agent]()
    registered = registry_keys()[agent]
    # Simulator stat / gauge / simchart keys are frontend-side, not in payload.
    structural = {
        k
        for k in registered
        if k.startswith(("tile:", "view:", "side:"))
    }
    orphans = structural - expected_keys(payload)
    assert not orphans, f"{agent}: info entries with no board element: {sorted(orphans)}"


@pytest.mark.parametrize("agent", sorted(PAYLOADS))
def test_default_view_exists(agent: str) -> None:
    payload = PAYLOADS[agent]()
    assert payload["default_view"] in payload["views"]


@pytest.mark.parametrize("agent", sorted(PAYLOADS))
def test_kpi_views_resolve(agent: str) -> None:
    """Clicking a KPI switches the focus panel — the target must exist."""

    payload = PAYLOADS[agent]()
    for kpi in payload["kpis"]:
        assert kpi["view"] in payload["views"], (
            f"{agent}: KPI {kpi['id']!r} points at missing view {kpi['view']!r}"
        )


# ---------------------------------------------------------------------------
# Charts rebuilt from the mockup — no two views may restate each other
# ---------------------------------------------------------------------------


def chart_points(view: dict) -> list[dict]:
    """Flatten a chart's data rows; line charts nest theirs under `values`."""

    data = view.get("data") or []
    if data and isinstance(data[0], dict) and "values" in data[0]:
        return [p for series in data for p in series.get("values") or []]
    return data


def charts(payload: dict) -> list[tuple[str, list[dict]]]:
    out: list[tuple[str, list[dict]]] = []
    for key, view in (payload.get("views") or {}).items():
        if view.get("table"):
            continue
        out.append((f"view:{key}", chart_points(view)))
    for slot, view in (payload.get("side") or {}).items():
        if not view or view.get("table"):
            continue
        out.append((f"side:{slot}", chart_points(view)))
    return out


def card(payload: dict, kpi_id: str) -> float:
    """The number a KPI card actually prints, parsed back out."""

    kpi = next(k for k in payload["kpis"] if k["id"] == kpi_id)
    return float(str(kpi["value"]).replace(",", "").rstrip("%d"))


@pytest.mark.parametrize("agent", sorted(PAYLOADS))
def test_no_chart_is_entirely_zero(agent: str) -> None:
    """A chart of nothing but zeros renders as an empty frame.

    This is what a column-name miss looks like from the outside: the labels
    and the legend are there, every bar is flat, and no error is raised.
    """

    payload = PAYLOADS[agent]()
    for key, points in charts(payload):
        assert points, f"{agent}: {key} has no data rows"
        assert any(float(p.get("value") or 0) for p in points), (
            f"{agent}: every value in {key} is zero — check the column names "
            f"against the snapshot: {points}"
        )


def test_leakage_charts_agree_with_the_kpi_cards() -> None:
    """Cards and charts must not state two different numbers for one quantity."""

    payload = _leakage_dashboard(leakage_snapshot())
    at_risk = card(payload, "flagged")
    protected = card(payload, "protected")
    blocked = card(payload, "blocked")

    def total(points: list[dict]) -> float:
        return sum(p["value"] for p in points)

    # The category breakdown and the mix donut both partition "at risk".
    assert total(payload["views"]["categories"]["data"]) == pytest.approx(
        at_risk, abs=0.5
    )
    assert total(payload["side"]["top"]["data"]) == pytest.approx(at_risk, abs=0.5)

    bottom = {p["label"]: p["value"] for p in payload["side"]["bottom"]["data"]}
    assert bottom["At risk"] == pytest.approx(at_risk, abs=0.5)
    assert bottom["Protected"] == pytest.approx(protected, abs=0.5)

    blockvs = {p["label"]: p["value"] for p in payload["views"]["blockvs"]["data"]}
    assert blockvs["Blocked"] == pytest.approx(blocked, abs=0.5)

    # The recovery sensitivity's current point is the "Total protected" card.
    assert payload["views"]["recovery"]["data"][-1]["value"] == pytest.approx(
        protected, abs=0.5
    )


def test_leakage_keeps_control_weaknesses_out_of_the_at_risk_total() -> None:
    """Split/threshold is flagged but not lost cash, so it cannot be a bar.

    Including it would push the category chart to 9,795 against a 7,845 card.
    """

    payload = _leakage_dashboard(leakage_snapshot())
    labels = [p["label"] for p in payload["views"]["categories"]["data"]]

    assert "Split / threshold" not in labels
    assert "Split / threshold" in payload["views"]["categories"]["note"]
    assert "1,950" in payload["views"]["categories"]["note"]


def test_leakage_says_so_when_category_amounts_do_not_resolve() -> None:
    """The fallback must announce itself, or the next rename hides again."""

    snapshot = leakage_snapshot()
    for row in snapshot["category_breakdowns"]:
        row["renamed_column_idr_mn"] = row.pop("amount_at_risk_idr_mn")

    view = _leakage_dashboard(snapshot)["views"]["categories"]
    assert "Illustrative" in view["note"]


def test_leakage_flag_count_comes_from_the_summary() -> None:
    """`items_flagged` is the stated count; row counts are query-limited."""

    payload = _leakage_dashboard(leakage_snapshot())
    flagged = next(k for k in payload["kpis"] if k["id"] == "flagged")
    assert flagged["delta"] == "10 flags"


def test_leakage_baseline_simulation_reproduces_the_cards() -> None:
    """A zero-delta simulator run must land on the numbers already on screen."""

    payload = _leakage_dashboard(leakage_snapshot())
    baseline = payload["simulator"]["baseline"]
    result = simulate_leakage_scenario(
        hold=baseline["fraud"],
        dup_rec=95,
        ov_rec=90,
        duplicates_amount=baseline["duplicates_amount"],
        overbill_amount=baseline["overbill_amount"],
        other_blocked=baseline["other_blocked"],
        at_risk=baseline["at_risk"],
    )

    assert result["blocked"] == pytest.approx(card(payload, "blocked"), abs=0.5)
    assert result["total_protected"] == pytest.approx(
        card(payload, "protected"), abs=0.5
    )


def test_leakage_vendors_is_a_rollup_not_the_worklist() -> None:
    views = _leakage_dashboard(leakage_snapshot())["views"]
    worklist = views["worklist"]["table"]
    vendors = views["vendors"]["table"]

    assert vendors["headers"] != worklist["headers"]
    assert vendors["rows"] != worklist["rows"]

    # Osaka has two flags (3,800 + 500) and must collapse into one row.
    names = [r[0] for r in vendors["rows"]]
    assert names.count("Osaka Precision KK") == 1
    osaka = next(r for r in vendors["rows"] if r[0] == "Osaka Precision KK")
    assert osaka[1] == 2, "flag count"
    assert osaka[3] == "4,300", "summed at-risk"
    # Ranked by exposure.
    assert names[0] == "Osaka Precision KK"


def test_leakage_recovery_is_a_sensitivity_not_side_bottom() -> None:
    payload = _leakage_dashboard(leakage_snapshot())
    recovery = payload["views"]["recovery"]
    bottom = payload["side"]["bottom"]

    assert recovery["title"] != bottom["title"]
    assert recovery["data"] != bottom["data"]
    assert len(recovery["data"]) == 3
    # Protection must rise with the assumed claw-back rate.
    values = [d["value"] for d in recovery["data"]]
    assert values == sorted(values), values


def test_leakage_blockvs_accounts_for_everything_at_risk() -> None:
    data = _leakage_dashboard(leakage_snapshot())["views"]["blockvs"]["data"]
    assert [d["label"] for d in data] == ["Blocked", "Recoverable", "Lost"]
    assert sum(d["value"] for d in data) == pytest.approx(7845)


def test_finance_reads_headline_metrics_from_the_stored_rows() -> None:
    """`metric_name` is the real column; substring matching mixed slots up."""

    payload = _finance_dashboard(finance_snapshot())

    assert card(payload, "revenue") == pytest.approx(46510)
    assert card(payload, "ebitda") == pytest.approx(4300)
    assert card(payload, "margin") == pytest.approx(9.2, abs=0.05)
    assert card(payload, "gm") == pytest.approx(25.3, abs=0.05)
    # "Opex to revenue %" and "Revenue growth vs budget" both contain
    # "revenue"; neither may land in the revenue slot.
    assert card(payload, "opex") == pytest.approx(16.1, abs=0.05)


def test_finance_waterfall_closes_on_the_ebitda_card() -> None:
    """A budget-to-actual waterfall that does not land on the actual is wrong."""

    payload = _finance_dashboard(finance_snapshot())
    data = payload["views"]["drivers"]["data"]

    assert data[0]["type"] == "total", "must open on budget"
    assert data[-1]["type"] == "total", "must close on actual"
    # Live driver names, not the mockup's abbreviations.
    assert [p["label"] for p in data[1:-1]] == [
        "Volume",
        "Mix",
        "Price",
        "Cost (input)",
        "Operating cost",
    ]

    running = data[0]["value"]
    for point in data[1:-1]:
        running += point["value"]
    assert running == pytest.approx(data[-1]["value"], abs=0.5)
    assert data[-1]["value"] == pytest.approx(card(payload, "ebitda"), abs=0.5)


def test_collections_high_risk_card_matches_its_tier_bar() -> None:
    """The card opens the by-tier chart, so it must state the tier's exposure."""

    payload = _collections_dashboard(collections_snapshot())
    tiers = {p["label"]: p["value"] for p in payload["views"]["tiers"]["data"]}
    kpi = next(k for k in payload["kpis"] if k["id"] == "high_risk")

    assert card(payload, "high_risk") == pytest.approx(tiers["High"], abs=0.5)
    # The provision is a different, smaller number — kept, but as the caption.
    assert "provision" in kpi["delta"]


def test_collections_aging_and_tiers_both_partition_the_ar_card() -> None:
    payload = _collections_dashboard(collections_snapshot())
    total_ar = card(payload, "ar")

    for key in ("aging", "tiers"):
        total = sum(p["value"] for p in payload["views"][key]["data"])
        assert total == pytest.approx(total_ar, abs=0.5), key
    assert sum(
        p["value"] for p in payload["side"]["top"]["data"]
    ) == pytest.approx(total_ar, abs=0.5)


def test_finance_opex_uses_live_lines_and_ranks_by_variance() -> None:
    view = _finance_dashboard(finance_snapshot())["views"]["opex"]
    rows = view["table"]["rows"]

    assert view["table"]["headers"] == ["Line", "Actual", "Budget", "Variance"]
    assert "Illustrative" not in view["note"]
    # Revenue row must be filtered out of an opex breakdown.
    assert all(r[0] != "Revenue" for r in rows)
    # Worst variance first, total last.
    assert rows[0][0] == "Logistics & freight"
    assert rows[0][3] == "+250"
    assert rows[-1] == ["Total operating expenses", "7,480", "7,000", "+480"]


def test_finance_opex_falls_back_when_columns_absent() -> None:
    view = _finance_dashboard({"profit_summary": []})["views"]["opex"]
    assert "Illustrative" in view["note"]
    assert view["table"]["rows"][-1][0] == "Total operating expenses"


def test_treasury_options_is_the_decision_table() -> None:
    view = _treasury_dashboard(treasury_baseline())["views"]["options"]
    rows = view["table"]["rows"]

    assert view["table"]["headers"] == [
        "Option",
        "Avoided",
        "Premium",
        "Liquidity impact",
    ]
    assert [r[0][0] for r in rows] == ["A", "B", "C", "D"]

    # A avoids nothing; B and C avoid the same FX loss but C pays cash today.
    assert rows[0][1] == "0", "doing nothing avoids nothing"
    assert rows[1][1] == rows[2][1] != "0", "B and C remove the same FX risk"
    assert rows[2][2] == "0", "spot purchase has no forward premium"
    assert "Cash out" in rows[2][3], "but C pays cash today"
    assert "No cash out" in rows[1][3], "while B does not"
    # D covers half of B.
    b_avoided = float(rows[1][1].replace(",", ""))
    d_avoided = float(rows[3][1].replace(",", ""))
    assert d_avoided == pytest.approx(b_avoided / 2, rel=0.01)


def test_collections_options_reach_levels_are_monotonic() -> None:
    view = _collections_dashboard(collections_snapshot())["views"]["options"]
    values = [d["value"] for d in view["data"]]

    assert len(values) == 3
    assert values == sorted(values), f"wider reach freed less: {values}"
    # Top-5 recovery from the fixture: 8500+5525+1400+3325+2550.
    assert values[1] == pytest.approx(21300)
    # Labels carry the DSO each option buys.
    assert all(d["label"].endswith("d") for d in view["data"])


def test_collections_options_monotonic_without_a_worklist() -> None:
    snapshot = collections_snapshot()
    snapshot["worklist"] = []
    view = _collections_dashboard(snapshot)["views"]["options"]
    values = [d["value"] for d in view["data"]]
    assert values == sorted(values), values


def test_registry_is_valid_and_covers_four_agents() -> None:
    keys = registry_keys()
    assert set(keys) == set(PAYLOADS)
    for agent, found in keys.items():
        assert "gauge" in found, agent
        assert "simchart" in found, agent
