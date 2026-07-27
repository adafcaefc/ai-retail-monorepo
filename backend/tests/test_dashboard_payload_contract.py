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
from src.llm.agents.finance.leakage.dashboard import _leakage_dashboard
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
            "high_risk_provision_idr_mn": 5000,
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
        "risk_tiers": [
            {"risk_tier": "High", "exposure_idr_mn": 5000},
            {"risk_tier": "Medium", "exposure_idr_mn": 19500},
            {"risk_tier": "Low", "exposure_idr_mn": 13435},
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
    return {
        "summary": [{"total_at_risk_idr_mn": 7845}],
        "category_breakdowns": [
            {"category_name": "Bank-change fraud", "amount_idr_mn": 3800},
            {"category_name": "Duplicate pay", "amount_idr_mn": 3050},
            {"category_name": "Overbilling", "amount_idr_mn": 900},
            {"category_name": "Lost discount", "amount_idr_mn": 95},
        ],
        "anomalies": [],
        "action_worklist": [
            {
                "vendor_name": "Osaka Precision KK",
                "anomaly_type": "Bank-change fraud",
                "amount_idr_mn": 3800,
                "risk_score": 94,
            },
            {
                "vendor_name": "Osaka Precision KK",
                "anomaly_type": "Overbilling",
                "amount_idr_mn": 500,
                "risk_score": 88,
            },
            {
                "vendor_name": "Shenzhen Micro Ltd",
                "anomaly_type": "Duplicate pay",
                "amount_idr_mn": 1850,
                "risk_score": 70,
            },
            {
                "vendor_name": "PT Bahan Baku Lokal",
                "anomaly_type": "Duplicate pay",
                "amount_idr_mn": 1200,
                "risk_score": 64,
            },
            {
                "vendor_name": "Taipei Semicon Co",
                "anomaly_type": "Overbilling",
                "amount_idr_mn": 400,
                "risk_score": 51,
            },
        ],
    }


def finance_snapshot() -> dict:
    return {
        "kpis": [],
        "variance_drivers": [],
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
