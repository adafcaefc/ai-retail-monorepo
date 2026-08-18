"""`formula.json` against the workbook it was transcribed from.

`test_formulas.py` proves the stored expressions parse and evaluate.
`test_worked_example_cells.py` proves the cited cells hold the documented
inputs. Neither asks the question this file asks: **do these expressions
reproduce the workbook's own answers, at scale?**

That question matters because of how `formula.json` came to exist. It was not
extracted by a script. It arrived by hand in `791aa14`, transcribed from the
workbook's `Formulas` sheet -- nineteen rows of prose like

    State | Stockout<0.6ROP; Low<ROP; Expiry(perishable,DoS>shelf);
            Overstock(non-perish,DoS>15); Slow(growth<1,DoS>10)

into executable expressions. The transcription also introduced constants the
prose never mentions (1.3, 0.15, 2.2, 0.85, 0.55). A human read a sentence and
wrote a formula, and nothing until now checked the result.

It is checked here against `schema_with_data.json`, which *was* extracted
mechanically and carries `source_sheet`/`source_row` on every row:

* f01-f16 against all sixteen computed columns of `ENGINE_STORE`, 16,000 rows;
* f17-f19 against `Workforce`, 159 stores;
* the **lever paths** against `What-If . Per Agent`.

That last one is not decoration. Every other check here sits at the workbook's
stored state, where `Constants` B16-B21 are all zero -- so it exercises the
lever parameters only at the one value that makes them vanish. A sign error in
`(1 + demand_lever / 100)` would pass every row of the first two checks.
`What-If . Per Agent` is the only non-zero reference the workbook contains, and
reproducing it is the sole evidence that What-If will be right.

The formulas are user-editable through the Formula Manager. That is the other
reason this file exists: an edit that looks harmless in the UI can silently
stop matching the workbook, and only a test at this scale would notice.
"""

from __future__ import annotations

import json
import math

from typing import Any

import pytest

from src.common.constants import AppPaths
from src.formulas import repository
from src.formulas.expression import evaluate, parse

SCHEMA_PATH = AppPaths.REPO_ROOT / "resources" / "dbtemp" / "schema_with_data.json"

# The workbook's stored state. Every one of `Constants` B16-B21 is zero, which
# is why the ENGINE_STORE comparison is a fair test at all: the sheet was
# calculated with no lever applied.
NO_LEVERS = {
    "demand_lever": 0,
    "promo_lever": 0,
    # B18. Absent from this dict until f14 started reading it -- the catalogue
    # had no term for the markdown slider to move, which is why the lever did
    # nothing in the What-If panel.
    "markdown_lever": 0,
    "inbound_lever": 0,
    "lead_time_adjust": 0,
    "safety_adjust": 0,
}

# The one scenario the workbook publishes a result for, on `What-If . Per
# Agent`. Its note reads "demand +20% -> forecast & PO rise"; the promo lever
# rides along at 15, which is also where the mockup parks its promo slider.
PUBLISHED_SCENARIO = {**NO_LEVERS, "demand_lever": 20, "promo_lever": 15}

# ENGINE_STORE column -> the formula that should reproduce it.
#
# `expiry_u` has no entry: f22 computes it, but only the chain-net ENGINE sheet
# stores the result, so `build_inventory_risk_fixture.py` is where that one is
# checked, over its 800 rows.
COLUMN_FORMULAS = {
    "ads": "f01-ads-per-store",
    "on_hand": "f02-on-hand",
    "open_po": "f03-open-po-per-store",
    "position": "f04-position",
    "rop": "f05-rop",
    "max": "f06-maximum-inventory",
    "state": "f07-inventory-state",
    "forecast_7d": "f08-forecast-7-days",
    "order_sales": "f09-order-quantity-sales-units",
    "order_buy": "f10-order-quantity-purchase-units",
    "order_value": "f11-order-value",
    "at_risk": "f12-at-risk-value",
    "promo_incr_margin": "f13-incremental-promotion-margin",
    # AA and AF. AA was headed "At-risk value" while computing markdown
    # recovery; renaming it split the two apart.
    "markdown_recoverable": "f14-recoverable-at-risk-value",
    "markdown_at_risk_value": "f23-markdown-at-risk-gross",
    "contribution_day": "f15-contribution-per-day",
    "labour_fte": "f16-labour-fte",
    "dos": "f20-days-of-supply",
    "inv_value": "f21-inventory-value",
}

WORKFORCE_FORMULAS = {
    "required": "f17-required-workforce",
    "scheduled": "f18-scheduled-workforce",
    "gap": "f19-coverage-gap",
}


# -- loading -----------------------------------------------------------


@pytest.fixture(scope="module")
def tables() -> dict[str, list[dict[str, Any]]]:
    """Every workbook table as row dicts.

    Rows are stored as positional arrays beside a `columns` list, which keeps
    the 6 MB file small but is unreadable to assert against. Zipping once here
    costs a second and makes every test below say what it means.
    """
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    return {
        table["name"]: [
            dict(zip([column["name"] for column in table["columns"]], row))
            for row in table["rows"]
        ]
        for table in payload["tables"]
    }


@pytest.fixture(scope="module")
def asts() -> dict[str, tuple]:
    """Each stored expression parsed once.

    `evaluate_expression` re-parses on every call. At 16,000 rows x 16
    formulas that is a quarter of a million parses, and the test stops being
    something anyone waits for.
    """
    return {
        formula["id"]: parse(formula["expression"])
        for formula in repository.load()
    }


@pytest.fixture(scope="module")
def week_factor(tables) -> float:
    """`Constants` B7 -- read, not typed in, so the two cannot drift apart."""
    for row in tables["constants"]:
        if row["source_cell"] == "B7":
            return row["value"]
    raise AssertionError("Constants!B7 (DOW sum) is missing from the extract.")


def _run(asts: dict[str, tuple], formula_id: str, **values: Any) -> Any:
    return evaluate(asts[formula_id], values)


# -- the engine grid ---------------------------------------------------


def _engine_row(
    asts: dict[str, tuple],
    sku: dict[str, Any],
    store: dict[str, Any],
    vertical: dict[str, Any],
    week: float,
    levers: dict[str, Any],
) -> dict[str, Any]:
    """One ENGINE_STORE row, rebuilt from the formulas alone.

    The order matters: each formula consumes the output of the ones above it,
    so this function is the dependency graph written out longhand. Nothing here
    decides anything -- every threshold, every constant lives in the
    expressions.
    """
    ads = _run(
        asts,
        "f01-ads-per-store",
        base_ads=sku["base_ads"],
        seasonality=sku["seasonality"],
        store_size=store["size"],
        demand_lever=levers["demand_lever"],
        promo_eligible=sku["promo"],
        promo_lever=levers["promo_lever"],
        promo_depth=sku["cannib_pct"],
    )
    on_hand = _run(
        asts,
        "f02-on-hand",
        base_ads=sku["base_ads"],
        on_hand_days=sku["onhand_days"],
        stock_factor=sku["stockf"],
        store_health=store["health"],
        store_size=store["size"],
    )
    open_po = _run(
        asts,
        "f03-open-po-per-store",
        open_po_total=sku["open_po"],
        store_size=store["size"],
        total_store_size=sku["sum_vert_size"],
        inbound_lever=levers["inbound_lever"],
    )
    position = _run(asts, "f04-position", on_hand=on_hand, open_po=open_po)

    reorder_days = {
        "ads": ads,
        # The designated vendor's lead time, not `sku_master.lead_d`.
        # The two disagree -- GRC-005 is 2 days against 6 -- and ROP
        # follows the Trade Agreement, which is the contract actually
        # being ordered against.
        "lead_time_days": sku["designated_lead_d"],
        "lead_time_adjust": levers["lead_time_adjust"],
        "safety_days": sku["safety_d"],
        "safety_adjust": levers["safety_adjust"],
    }
    rop = _run(asts, "f05-rop", **reorder_days)
    maximum = _run(asts, "f06-maximum-inventory", **reorder_days)

    days_of_supply = _run(
        asts, "f20-days-of-supply", ads=ads, position=position
    )
    state = _run(
        asts,
        "f07-inventory-state",
        position=position,
        rop=rop,
        perishable=sku["perishable"],
        days_of_supply=days_of_supply,
        shelf_life_days=sku["expiry_d"],
        velocity=sku["growth"],
    )

    gross_markdown = _run(
        asts,
        "f23-markdown-at-risk-gross",
        state=state,
        position=position,
        ads=ads,
        shelf_life_days=sku["expiry_d"],
        price=sku["price"],
        max_inventory=maximum,
    )

    order_sales = _run(
        asts,
        "f09-order-quantity-sales-units",
        position=position,
        rop=rop,
        max_inventory=maximum,
    )
    order_buy = _run(
        asts,
        "f10-order-quantity-purchase-units",
        order_sales_units=order_sales,
        pack_factor=sku["pack_factor"],
    )

    return {
        "ads": ads,
        "on_hand": on_hand,
        "open_po": open_po,
        "position": position,
        "rop": rop,
        "max": maximum,
        "state": state,
        "forecast_7d": _run(
            asts, "f08-forecast-7-days", ads=ads, week_factor=week
        ),
        "dos": days_of_supply,
        "order_sales": order_sales,
        "order_buy": order_buy,
        "order_value": _run(
            asts,
            "f11-order-value",
            order_buy_units=order_buy,
            pack_factor=sku["pack_factor"],
            # The contract price the PO is raised at, not the shelf price.
            vendor_price=sku["designated_unit_price"],
        ),
        "inv_value": _run(
            asts,
            "f21-inventory-value",
            position=position,
            price=sku["price"],
        ),
        "at_risk": _run(
            asts,
            "f12-at-risk-value",
            state=state,
            position=position,
            price=sku["price"],
        ),
        "promo_incr_margin": _run(
            asts,
            "f13-incremental-promotion-margin",
            promo_eligible=sku["promo"],
            ads=ads,
            price=sku["price"],
            cannibalization=sku["cannib_pct"],
            margin_pct=sku["margin_pct"],
            promo_funding=sku["fund_pct"],
        ),
        # Gross exposure (ENGINE_STORE!AF), then the net recovery it feeds
        # (AA). f14 held the gross expression under the net's name until the
        # workbook's rename split them apart.
        "markdown_at_risk_value": gross_markdown,
        "markdown_recoverable": _run(
            asts,
            "f14-recoverable-at-risk-value",
            gross=gross_markdown,
            state=state,
            elasticity=sku["elasticity"],
            markdown_lever=levers["markdown_lever"],
        ),
        "contribution_day": _run(
            asts,
            "f15-contribution-per-day",
            ads=ads,
            price=sku["price"],
            margin_pct=sku["margin_pct"],
        ),
        "labour_fte": _run(
            asts,
            "f16-labour-fte",
            ads=ads,
            price=sku["price"],
            sales_per_fte=vertical["sales_per_fte"],
        ),
    }


def _sku_index(tables) -> dict[str, dict]:
    """`sku_master` rows keyed by id, each carrying its designated lead time.

    `sku_master.lead_d` is a static field that disagrees with the Trade
    Agreement the item is actually ordered against -- GRC-005 says 2 days
    there and 6 in the agreement. ROP follows the agreement, so the check has
    to as well, or every ROP-derived column reports a mismatch that is really
    the test reading the wrong column.

    Exactly one row per item carries `designated = "Y"`; verified 800/800.
    """
    designated = {
        row["item"]: row
        for row in tables["trade_agreements"]
        if str(row["designated"]).strip().upper() == "Y"
    }
    index = {}
    for row in tables["sku_master"]:
        agreement = designated.get(row["sku_id"])
        enriched = dict(row)
        enriched["designated_lead_d"] = (
            agreement["lead_time_d"] if agreement else row["lead_d"]
        )
        # Falls back to cost rather than price: guessing the retail price here
        # would reintroduce the very error this replaced.
        enriched["designated_unit_price"] = (
            agreement["unit_price"] if agreement else row["cost"]
        )
        index[row["sku_id"]] = enriched
    return index


@pytest.fixture(scope="module")
def engine_grid(asts, tables, week_factor) -> list[tuple[dict, dict]]:
    """All 16,000 rows recomputed, paired with what the workbook stored."""
    sku_by_id = _sku_index(tables)
    store_by_id = {row["store_id"]: row for row in tables["stores"]}
    vertical_by_id = {row["vertical_id"]: row for row in tables["verticals"]}

    return [
        (
            stored,
            _engine_row(
                asts,
                sku_by_id[stored["sku_id"]],
                store_by_id[stored["store_id"]],
                vertical_by_id[stored["vertical_id"]],
                week_factor,
                NO_LEVERS,
            ),
        )
        for stored in tables["engine_store"]
    ]


def _agrees(computed: Any, stored: Any) -> bool:
    if isinstance(stored, str) or isinstance(computed, str):
        return str(computed) == str(stored)
    # Absolute tolerance carries the money columns, where a relative
    # comparison against billions would wave through whole rupiah.
    if math.isclose(computed, stored, rel_tol=1e-9, abs_tol=1e-6):
        return True

    # A formula ending in ROUND can land on the far side of the .5 boundary
    # from Excel purely on the last bit of a double. FSH-062/S054 computes
    # 5427889.499999999 here, 9.3e-10 short, so Excel rounds up and Python
    # rounds down. Seventeen of 16,000 rows do this. One unit is allowed on
    # integral results only, and only when the two agree to a part in a
    # million -- f11 reading the retail price instead of the contract price
    # was out by 32% and still failed this.
    # No relative gate: ROUND's output granularity IS one unit, so one unit is
    # the smallest disagreement the formula can express. A real error does not
    # land inside that across 16,000 rows -- f11 reading the retail price
    # instead of the contract price was out by 1.2 million per row.
    if float(computed).is_integer() and float(stored).is_integer():
        return abs(computed - stored) <= 1
    return False


@pytest.mark.parametrize("column", sorted(COLUMN_FORMULAS))
def test_formulas_reproduce_engine_store(engine_grid, column: str) -> None:
    """Every computed ENGINE_STORE column, every row."""
    mismatches = [
        (stored["sku_id"], stored["store_id"], computed[column], stored[column])
        for stored, computed in engine_grid
        if not _agrees(computed[column], stored[column])
    ]

    assert not mismatches, (
        f"{COLUMN_FORMULAS[column]} disagrees with ENGINE_STORE.{column} on "
        f"{len(mismatches)} of {len(engine_grid)} rows. First three: "
        + "; ".join(
            f"{sku}/{store} formula={got!r} workbook={want!r}"
            for sku, store, got, want in mismatches[:3]
        )
    )


def test_the_grid_is_the_whole_chain(engine_grid) -> None:
    """A guard on the guard: a truncated extract would make the above vacuous."""
    assert len(engine_grid) == 16_000


# -- workforce ---------------------------------------------------------


@pytest.mark.parametrize("column", sorted(WORKFORCE_FORMULAS))
def test_formulas_reproduce_workforce(asts, tables, column: str) -> None:
    """f17-f19 against the Workforce sheet, chain TOTAL row excluded."""
    stores = [row for row in tables["workforce"] if not row["is_total"]]
    assert stores, "the Workforce extract carries no per-store rows"

    mismatches = []
    for store in stores:
        roster = {
            "store_size": store["size"],
            "wf_base": store["wf_base"],
        }
        required = _run(
            asts,
            "f17-required-workforce",
            **roster,
            peak_factor=store["peak"],
            event_lift=store["event_lift"],
            footfall_index=store["footfall_idx"],
        )
        scheduled = _run(
            asts, "f18-scheduled-workforce", **roster, store_health=store["health"]
        )
        computed = {
            "required": required,
            "scheduled": scheduled,
            "gap": _run(
                asts,
                "f19-coverage-gap",
                required=required,
                scheduled=scheduled,
            ),
        }

        if not _agrees(computed[column], store[column]):
            mismatches.append(
                (store["store_id"], computed[column], store[column])
            )

    assert not mismatches, (
        f"{WORKFORCE_FORMULAS[column]} disagrees with Workforce.{column} on "
        f"{len(mismatches)} of {len(stores)} stores. First three: "
        + "; ".join(
            f"{store} formula={got!r} workbook={want!r}"
            for store, got, want in mismatches[:3]
        )
    )


# -- the lever paths ---------------------------------------------------


def test_levers_reproduce_the_published_scenario(
    asts, tables, week_factor
) -> None:
    """demand +20% against `What-If . Per Agent`.

    This is the only assertion in the file that moves a lever off zero, and so
    the only one that can catch a wrong sign, a misplaced /100, or a promo
    branch that never fires. Without it the What-If panel would rest on
    expressions nobody had ever run in anger.
    """
    sku_by_id = _sku_index(tables)
    store_by_id = {row["store_id"]: row for row in tables["stores"]}
    vertical_by_id = {row["vertical_id"]: row for row in tables["verticals"]}
    label_of = {
        row["vertical_id"]: row["dashboard_label"] for row in tables["verticals"]
    }

    forecast: dict[str, list[float]] = {}
    for stored in tables["engine_store"]:
        sku = sku_by_id[stored["sku_id"]]
        store = store_by_id[stored["store_id"]]
        vertical = vertical_by_id[stored["vertical_id"]]
        label = label_of[stored["vertical_id"]]

        totals = forecast.setdefault(label, [0.0, 0.0])
        for index, levers in enumerate((NO_LEVERS, PUBLISHED_SCENARIO)):
            row = _engine_row(asts, sku, store, vertical, week_factor, levers)
            totals[index] += row["forecast_7d"]

    published = {
        row["vertical_label"]: row["forecast_delta"]
        for row in tables["what_if_per_agent"]
    }
    assert set(published) == set(forecast), (
        "What-If . Per Agent and ENGINE_STORE disagree on the vertical list"
    )

    drifted = []
    for label, expected in published.items():
        baseline, scenario = forecast[label]
        # The sheet stores the delta rounded to whole units, so a couple of
        # units of disagreement is the rounding, not the formula.
        if abs((scenario - baseline) - expected) > 2:
            drifted.append((label, scenario - baseline, expected))

    assert not drifted, (
        "the lever path no longer reproduces the workbook's own +20% demand "
        "scenario: "
        + "; ".join(
            f"{label} formula={got:,.1f} workbook={want:,}"
            for label, got, want in drifted
        )
    )


def test_inbound_lead_and_safety_have_no_workbook_reference(tables) -> None:
    """Three of the six levers cannot be checked against the workbook at all.

    `What-If . Per Agent` publishes one scenario, and it moves only demand and
    promo. `What-If Simulator` looks like a second reference but is not: it was
    saved with every lever at zero, so its "live levers" column differs from
    baseline only by float noise -- Grocery's forecast delta is -3.74 on a
    442,054 base.

    So `inbound`, `lead` and `safety` are exercised below by property rather
    than by reference. That is weaker, and saying so here is the point: if a
    scenario for them ever lands in the workbook, replace those tests with a
    comparison and delete this one.
    """
    # Relative, because the noise is absolute: Grocery drifts 3.74 units on a
    # 442,054 base (0.0008%), while the published +20% scenario moves 25%.
    # Anything past a tenth of a percent is a lever, not arithmetic.
    noise = [
        row
        for row in tables["what_if_simulator"]
        if row["metric"] == "Forecast 7d"
        and abs(row["delta"]) > abs(row["baseline"]) * 0.001
    ]
    assert not noise, (
        "What-If Simulator now carries a real scenario -- it can be used as a "
        f"reference for the remaining levers: {noise[:2]}"
    )


@pytest.mark.parametrize(
    ("lever", "formula_id", "reads"),
    [
        ("demand_lever", "f01-ads-per-store", "ads"),
        ("inbound_lever", "f03-open-po-per-store", "open_po"),
        ("lead_time_adjust", "f05-rop", "rop"),
        ("safety_adjust", "f05-rop", "rop"),
    ],
)
def test_raising_a_lever_never_lowers_what_it_drives(
    asts, tables, week_factor, lever: str, formula_id: str, reads: str
) -> None:
    """Direction only -- but direction is where sign errors live.

    A flipped sign or a `* 100` where `/ 100` belongs survives every reference
    check above, because those all sit at zero. This does not prove the
    magnitude is right; it proves the lever pushes the way its label promises.
    """
    sku_by_id = _sku_index(tables)
    store_by_id = {row["store_id"]: row for row in tables["stores"]}
    vertical_by_id = {row["vertical_id"]: row for row in tables["verticals"]}

    # One store per vertical is enough for a monotonicity claim, and keeps the
    # test at 8 x 100 rows rather than 16,000 x 3.
    sample = [row for row in tables["engine_store"] if row["store_id"].endswith("01")]
    assert sample, "no sample rows selected"

    wrong = []
    for stored in sample:
        rows = [
            _engine_row(
                asts,
                sku_by_id[stored["sku_id"]],
                store_by_id[stored["store_id"]],
                vertical_by_id[stored["vertical_id"]],
                week_factor,
                {**NO_LEVERS, lever: step},
            )[reads]
            for step in (-2, 0, 2)
        ]
        if not (rows[0] <= rows[1] <= rows[2]):
            wrong.append((stored["sku_id"], stored["store_id"], rows))

    assert not wrong, (
        f"{formula_id}: raising {lever} does not raise {reads}. "
        f"{len(wrong)} of {len(sample)} rows, first three: {wrong[:3]}"
    )


def test_the_reorder_floors_engage_under_a_negative_lever(
    asts, tables, week_factor
) -> None:
    """`MAX(1, lead + adj)` and `MAX(0, safety + adj)` -- dead at rest, live in What-If.

    No SKU ships with a lead below 2 or a safety below 1, so neither floor ever
    binds in the stored workbook: replacing `MAX(1, ...)` with `MAX(2, ...)`
    passes every other test in this file. Pull the lead lever to its minimum
    and 75 of 800 SKUs cross the floor, which is precisely the branch a What-If
    user reaches first.

    The expectation is restated here by hand on purpose. Everywhere else this
    repository refuses to write a rule twice; a test that independently says
    what the answer should be is the exception that makes drift visible.
    """
    sku_by_id = _sku_index(tables)
    store_by_id = {row["store_id"]: row for row in tables["stores"]}
    vertical_by_id = {row["vertical_id"]: row for row in tables["verticals"]}

    levers = {**NO_LEVERS, "lead_time_adjust": -2, "safety_adjust": -2}
    floored = 0
    wrong = []

    for stored in tables["engine_store"]:
        sku = sku_by_id[stored["sku_id"]]
        if sku["lead_d"] - 2 >= 1 and sku["safety_d"] - 2 >= 0:
            continue

        floored += 1
        row = _engine_row(
            asts,
            sku,
            store_by_id[stored["store_id"]],
            vertical_by_id[stored["vertical_id"]],
            week_factor,
            levers,
        )
        # The designated agreement's lead time, matching f05. Against the
        # static `lead_d` this expectation drifts the moment ROP stops
        # reading that column.
        days = max(1, sku["designated_lead_d"] - 2) + max(0, sku["safety_d"] - 2)
        expected = math.floor(abs(row["ads"] * days) + 0.5)

        if row["rop"] != expected:
            wrong.append((stored["sku_id"], row["rop"], expected))

    assert floored, (
        "no SKU crosses either floor at the minimum lever -- this test no "
        "longer exercises the branch it was written for"
    )
    assert not wrong, (
        f"the reorder floors are not holding on {len(wrong)} of {floored} "
        f"rows. First three: {wrong[:3]}"
    )


def test_zero_levers_are_the_workbooks_stored_state(tables) -> None:
    """Why NO_LEVERS is the right baseline, asserted rather than assumed.

    If a future workbook ships with a lever already applied, every comparison
    above becomes a comparison against a scenario -- and would still pass while
    meaning something else entirely.
    """
    levers = {
        row["parameter"]: row["value"]
        for row in tables["constants"]
        if row["block"] == "what_if_lever"
    }

    assert levers, "Constants carries no what_if_lever block"
    assert set(levers.values()) == {0}, (
        f"the workbook was calculated with a lever applied: {levers}"
    )
