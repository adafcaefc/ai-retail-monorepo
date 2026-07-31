"""QC-035 and QC-043: the period stamp and the filter declaration.

Both are payload-shaping helpers, so they are tested on hand-built payloads
rather than through the database — the point is the shape, not the figures.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.llm.agents.common.dashboard_blocks import (
    _enriched,
    _filters,
    _options_of,
    _stamp_period,
)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def bar(*labels_and_keys):
    return {
        "chart_type": "bar",
        "title": "A chart",
        "data": [
            {"label": label, "value": index + 1, **({"key": key} if key else {})}
            for index, (label, key) in enumerate(labels_and_keys)
        ],
    }


def table(*rows):
    return {
        "title": "A table",
        "table": {"headers": ["Name", "Amount"], "rows": list(rows)},
    }


# ---------------------------------------------------------------------------
# QC-035
# ---------------------------------------------------------------------------


def test_period_reaches_every_chart_and_table():
    payload = {
        "period": "August 2026",
        "kpis": [],
        "views": {"a": bar(("X", None)), "b": table(["Row", 1])},
        "side": {"top": bar(("Y", None))},
    }
    _stamp_period(payload)

    assert payload["views"]["a"]["period"] == "August 2026"
    assert payload["views"]["b"]["period"] == "August 2026"
    assert payload["side"]["top"]["period"] == "August 2026"


def test_a_chart_keeps_a_period_it_already_states():
    payload = {
        "period": "August 2026",
        "kpis": [],
        "views": {"a": {**bar(("X", None)), "period": "Q3 2026"}},
        "side": {},
    }
    _stamp_period(payload)

    assert payload["views"]["a"]["period"] == "Q3 2026"


def test_missing_period_stamps_nothing_rather_than_an_empty_label():
    payload = {"kpis": [], "views": {"a": bar(("X", None))}, "side": {}}
    _stamp_period(payload)

    assert "period" not in payload["views"]["a"]


def test_enriched_stamps_and_enriches_together():
    payload = {
        "period": "August 2026",
        "kpis": [{"id": "k", "label": "K", "value": "1", "delta": ""}],
        "views": {"a": bar(("X", None))},
        "side": {},
    }
    out = _enriched(payload)

    assert out["views"]["a"]["period"] == "August 2026"
    assert out["kpis"][0]["id"] == "k"


# ---------------------------------------------------------------------------
# QC-043
# ---------------------------------------------------------------------------


def test_options_come_from_the_chart_that_is_plotted():
    assert _options_of(bar(("A", None), ("B", None))) == ["A", "B"]


def test_an_abbreviated_label_offers_its_full_key():
    """The GM-by-product bar reads 'Ind'; the filter must offer 'Industrial'."""
    assert _options_of(bar(("Ind", "Industrial"), ("Pre", "Precision"))) == [
        "Industrial",
        "Precision",
    ]


def test_table_options_come_from_the_named_column():
    element = table(["Osaka", 10], ["Taipei", 5], ["Osaka", 2])
    assert _options_of(element, 0) == ["Osaka", "Taipei"]


def test_a_dimension_with_one_value_is_not_offered():
    """A filter that cannot narrow anything is noise, not a control."""
    views = {"only": bar(("Solo", None))}
    built = _filters(views, {}, (("x", "X", "view:only", ("view:only",), 0),))

    assert built == []


def test_a_filter_targeting_a_missing_element_drops_that_target():
    views = {"src": bar(("A", None), ("B", None))}
    built = _filters(
        views, {}, (("x", "X", "view:src", ("view:src", "view:gone"), 0),)
    )

    assert built[0]["applies_to"] == ["view:src"]


def test_every_offered_option_exists_in_every_element_it_targets():
    """The QC-043 trap: an option no target contains empties the board."""
    views = {
        "full": bar(("Industrial", None), ("Precision", None)),
        "short": bar(("Ind", "Industrial"), ("Pre", "Precision")),
    }
    built = _filters(
        views, {}, (("p", "Product", "view:full", ("view:full", "view:short"), 0),)
    )

    offered = set(built[0]["options"])
    for key in built[0]["applies_to"]:
        assert offered & set(_options_of(views[key.split(":", 1)[1]]))


def test_side_panels_can_be_both_source_and_target():
    side = {"top": bar(("A", None), ("B", None))}
    built = _filters({}, side, (("s", "S", "side:top", ("side:top",), 0),))

    assert built[0]["options"] == ["A", "B"]
    assert built[0]["applies_to"] == ["side:top"]


# ---------------------------------------------------------------------------
# QC-058 — the toggle is only as good as the wording behind it
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dictionary() -> set[str]:
    source = (FRONTEND / "i18n.js").read_text(encoding="utf-8")
    quoted = set(re.findall(r'"([^"\\]+)":\s*"[^"\\]+"', source))
    bare = set(re.findall(r'^\s{2}(\w+):\s*"[^"\\]+",', source, re.M))
    return quoted | bare


@pytest.mark.parametrize(
    "phrase",
    [
        "What-if simulator",
        "Reset to baseline",
        "Presets",
        "No rows match the current filter.",
    ],
)
def test_chrome_wording_is_translated(dictionary, phrase):
    assert phrase in dictionary


def test_the_toggle_offers_exactly_two_languages():
    source = (FRONTEND / "i18n.js").read_text(encoding="utf-8")
    block = source.split("export const LANGUAGES = [", 1)[1].split("];", 1)[0]

    assert set(re.findall(r'id:\s*"(\w+)"', block)) == {"en", "id"}


# ---------------------------------------------------------------------------
# Presets come from the workbook, not from a constant someone typed
# ---------------------------------------------------------------------------


def test_finance_presets_quote_the_stored_levers():
    from src.llm.agents.finance.finance.dashboard import _finance_presets

    presets = _finance_presets(
        [
            {
                "selling_price_change_percentage": 0.04,
                "material_cost_change_percentage": 0.0,
                "usd_idr_change_percentage": 0.03,
            }
        ]
    )
    combined = next(p for p in presets if p["id"] == "combined")

    assert combined["values"] == {"price": 4.0, "cost": 0.0, "fx": 3.0}


def test_no_preset_claims_to_be_a_recommendation():
    """A button labelled "recommendation" asks to be trusted; one labelled
    with its own levers can be checked against the sliders it moves."""
    from src.llm.agents.finance.finance.dashboard import _finance_presets

    presets = _finance_presets(
        [{"selling_price_change_percentage": 0.04,
          "usd_idr_change_percentage": 0.03}]
    )

    assert not any(
        "recommendation" in p["label"].lower() for p in presets
    )


def test_finance_presets_accept_points_as_well_as_fractions():
    """Some batches store 4, others 0.04. Both mean four percent."""
    from src.llm.agents.finance.finance.dashboard import _finance_presets

    as_points = _finance_presets([{"selling_price_change_percentage": 4}])
    as_fraction = _finance_presets([{"selling_price_change_percentage": 0.04}])

    assert as_points[0]["values"]["price"] == as_fraction[0]["values"]["price"]


def test_no_stored_scenario_offers_no_preset():
    """Better an empty row than an invented number — that is the whole point."""
    from src.llm.agents.finance.finance.dashboard import _finance_presets

    assert _finance_presets([]) == []
    assert _finance_presets([{"selling_price_change_percentage": 0}]) == []
