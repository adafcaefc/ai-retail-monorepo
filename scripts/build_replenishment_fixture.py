"""Build the Replenishment (Agent 3) dashboard fixture from the workbook.

Run it yourself:

    python scripts/build_replenishment_fixture.py

Input:  resources/dbtemp/schema_with_data.json
        resources/dbtemp/formula.json
        resources/demand_store_sku_32w_poc_v1.csv
Output: frontend/src/agents/retail/replenishment/data/fixture.json

WHY THIS ONE IS THE LEAST BLOCKED
Of the three Retail boards, A3 has the richest source and no D365 dependency at
all: 800 requisition lines in `Replenishment Detail`, 2,400 price tiers in
`Trade Agreement`, vendor scorecards, and `A3 Replenishment` to reconcile
against. Five of its six KPIs are calculated in the workbook, not typed -- the
opposite of A1.

TWO ORDER VALUES, AND WHY BOTH ARE KEPT
The workbook states order value twice, and they differ by about a fifth:

    A3 Replenishment / ENGINE!P      order units x SELLING price   (retail)
    Replenishment Detail!amount      buy units x TRADE price       (cost)

Grocery: Rp 4.46 bn against Rp 3.60 bn. Neither is wrong. A buyer approving a
PO needs the cost; a merchandiser sizing the commitment needs the retail value.
Reporting one as "order value" and hiding the other is how a board gets used to
argue for the wrong decision, so both ship, both named.

WHAT `vendor_scorecard` IS NOT USED FOR
The vendor rows used to carry a `risk` field read as
`scorecard[name].get("risk", "")`. `Vendor Scorecard` has no `risk` column --
it has `score`, `otif_pct`, `fill_pct`, `defect_pct`, `at_risk_value` -- so
that lookup returned an empty string on all eight vendors, every build, and the
whole table was loaded to produce it. The field is gone and the table is no
longer read. Surfacing the real scorecard columns is worth doing, but it needs
a `retail.vendor_scorecard` table so the API can answer with the same figures;
half of it in the fixture only would put the two paths out of step.

THE QUOTES BEHIND `saving_vs_designated`
The board reported a recoverable saving per line without ever carrying the
prices it is a difference between: `Trade Agreement` was seeded into Postgres,
indexed, and queried by nobody. A buyer asked to move a line to another vendor
could not see what that vendor charges, what its minimum break is, or by how
much it undercuts the incumbent.

`build_quotes` carries all 2,400. `verify_quotes` then rebuilds three figures
the workbook states independently and refuses to write the fixture unless all
800 lines agree exactly:

    best_price            = min(unit_price) across the SKU's three quotes
    unit_price_trade      = the quote of the vendor marked Designated
    saving_vs_designated  = (designated - best) x order_qty_buy x pack_factor

The last one is worth spelling out because it is not the shortfall. The
workbook prices the saving on the whole packs a purchase order actually buys,
so it reconciles against `amount` and not against `order_qty_sales`. Getting
that wrong is a quiet twelvefold error on some SKUs.

ONE THING THE PANEL MUST NOT DO
`best_price` is the lowest LIST price. The workbook ignores `discount_pct` when
it picks the winner, and applying the discount would change which vendor is
cheapest on 159 of 800 SKUs. Both columns ship; the discount is shown and the
saving stays on the workbook's own basis. Publishing a rival saving computed a
different way would put two numbers on one board with nothing to say which is
the answer.

ROUTES COME FROM LEAD TIME, NOT FROM A CATEGORY LIST
A3 spec section 2 classifies routes as `fresh -> Direct`, `catId in {BEV, HOU}
-> Flow-Through`, else `Cross-Dock`. `BEV` and `HOU` do not exist in this
dataset -- the mockup carried its own category codes.

The workbook does carry the thing those codes stood for. `SKU_Master.lead_d`
takes exactly three values, and they line up with the spec's own lead-time
story one for one:

    lead 2d   75 SKUs   all perishable   -> Direct Store Delivery  (+2d)
    lead 4d  625 SKUs                    -> Flow-Through           (+4d)
    lead 7d  100 SKUs                    -> Cross-Docking          (+5d and up)

`perishable == "Y"` and `lead_d == 2` select the same 75 rows with no
exceptions, so the fresh rule and the lead-time rule agree where they overlap.
Routing on lead time is therefore the spec's intent expressed in a column this
dataset actually has.

THE 32-WEEK DEMAND CURVE
The requirement chart's backbone comes from `synthetic.demand_store_sku_32w`,
which holds no workbook sheet at all -- its export is
`resources/demand_store_sku_32w_poc_v1.csv` (16,000 store x SKU rows, 16 actual
weeks then 16 forecast, provenance in the manifest beside it). Each line gets
`demand_weekly`, the per-SKU chain curve, summed over the SKU's 20 stores in
`Decimal` so the fixture's floats are the same numbers the API's SQL decimal
sums produce -- the parity test compares field for field.

The curve is calibrated against this very board, and `verify_demand_calibration`
refuses to build if that ever drifts: each SKU's first forecast week must
reproduce the line's own ADS x `Constants!B7` (the day-of-week sum). Without
that check a regenerated CSV could quietly state a different demand level than
the ADS every other figure on the board reconciles against.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))  # `scripts/` is not a package

import workbook_guard  # noqa: E402
from retail_demand_model import DOW_PROFILE, check_profile  # noqa: E402
from src.formulas import repository  # noqa: E402
from src.formulas.expression import evaluate, parse  # noqa: E402

SOURCE = REPO / "resources" / "dbtemp" / "schema_with_data.json"
DEMAND_CSV = REPO / "resources" / "demand_store_sku_32w_poc_v1.csv"
TARGET = (
    REPO
    / "frontend"
    / "src"
    / "agents"
    / "retail"
    / "replenishment"
    / "data"
    / "fixture.json"
)

SCHEMA_VERSION = 1
AGENT_ID = "retail.replenishment"

CATALOGUE_FORMULAS = (
    "f01-ads-per-store",
    "f03-open-po-per-store",
    "f04-position",
    "f05-rop",
    "f06-maximum-inventory",
    "f09-order-quantity-sales-units",
    "f10-order-quantity-purchase-units",
    "f11-order-value",
    "f20-days-of-supply",
)

# A3 spec section 7. `days` is the added lead the route costs, straight from
# the spec's own tab labels; `lead_days` is the SKU attribute that selects it.
ROUTES = (
    {
        "id": "direct",
        "label": "Direct Store Delivery",
        "lead_days": 2,
        "added_days": 2,
        "note": "Fresh, store-direct. Shortest lead, no consolidation.",
    },
    {
        "id": "flow",
        "label": "Flow-Through",
        "lead_days": 4,
        "added_days": 4,
        "note": "DC pick and pass. No put-away step.",
    },
    {
        "id": "cross",
        "label": "Cross-Docking",
        "lead_days": 7,
        "added_days": 5,
        "note": "DC consolidation across vendors.",
    },
)


def read_source() -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = [dict(zip(names, row)) for row in table["rows"]]
    return tables


def constants_from_cells(constants, wanted):
    by_cell = {row["source_cell"]: row for row in constants}
    resolved = {}
    for name, cell in wanted.items():
        if cell not in by_cell:
            raise SystemExit(f"FAIL  Constants!{cell} ({name}) is not in the extract")
        resolved[name] = by_cell[cell]["value"]
    return resolved


def chain_store_size(stores):
    totals: dict[str, float] = {}
    for store in stores:
        totals[store["vertical_id"]] = (
            totals.get(store["vertical_id"], 0.0) + store["size"]
        )
    return totals


def route_for(lead_days: int) -> str:
    """Pick a route from the SKU's lead time. See the module docstring."""
    for route in ROUTES:
        if lead_days <= route["lead_days"]:
            return route["id"]
    return ROUTES[-1]["id"]


def verify_order_chain(engine, sku_master, store_size, hz_cov) -> dict[str, str]:
    """Rebuild the order chain from the catalogue before writing anything.

    Every formula this board turns into a purchase order is checked against the
    workbook column it is supposed to reproduce -- all 800 rows, or the fixture
    is not written.

    It used to start at f09, taking the workbook's own `position`, `rop` and
    `max` as given. That left the whole demand half of the chain unchecked, and
    it is exactly where v8.5 changed: f01 gained an archetype/horizon factor
    and f06 took its horizon term as a parameter. The catalogue moved, this
    builder did not, and nothing here failed -- the fixture kept its pre-v8.5
    expressions and the board carried on until the first What-If lever drag
    raised on the operand that was never supplied. Checking f01 through f06 as
    well is what makes that a build failure rather than a runtime one.

    Each formula is evaluated against the workbook's own stored inputs rather
    than against the previous formula's output. Chaining would report one
    failure as six; this way the name that fails is the rule that is wrong.
    """
    formulas = {formula["id"]: formula for formula in repository.load()}
    missing = [key for key in CATALOGUE_FORMULAS if key not in formulas]
    if missing:
        raise SystemExit(f"FAIL  formula.json is missing {', '.join(missing)}")

    expressions = {key: formulas[key]["expression"] for key in CATALOGUE_FORMULAS}
    asts = {key: parse(expression) for key, expression in expressions.items()}
    failures: list[str] = []

    for row in engine:
        sku = sku_master[row["sku_id"]]
        size = store_size[row["vertical_id"]]

        ads = evaluate(
            asts["f01-ads-per-store"],
            {
                "base_ads": sku["base_ads"],
                "seasonality": sku["seasonality"],
                "arch_horizon_factor": sku["arch_horizon_factor"],
                "store_size": size,
                "demand_lever": 0,
                "promo_eligible": sku["promo"],
                "promo_lever": 0,
                "promo_depth": sku["cannib_pct"],
            },
        )
        open_po = evaluate(
            asts["f03-open-po-per-store"],
            {
                # Ratio of one: a chain-net row already covers every store, so
                # there is no allocation left to do.
                "open_po_total": row["open_po"],
                "store_size": size,
                "total_store_size": size,
                "inbound_lever": 0,
            },
        )
        position = evaluate(
            asts["f04-position"],
            # The workbook publishes position and open PO but not on-hand, so
            # on-hand is the difference -- which is how `build_lines` below
            # states it too. The check is therefore that f04 is consistent with
            # that reading, not an independent measurement of it.
            {"on_hand": row["position"] - row["open_po"], "open_po": row["open_po"]},
        )

        reorder = {
            "ads": row["ads"],
            "lead_time_days": sku["lead_d"],
            "lead_time_adjust": 0,
            "safety_days": sku["safety_d"],
            "safety_adjust": 0,
        }
        rop = evaluate(asts["f05-rop"], reorder)
        max_qty = evaluate(
            asts["f06-maximum-inventory"], {**reorder, "horizon_coverage": hz_cov}
        )

        order_sales = evaluate(
            asts["f09-order-quantity-sales-units"],
            {
                "position": row["position"],
                "rop": row["rop"],
                "max_inventory": row["max"],
            },
        )
        order_buy = evaluate(
            asts["f10-order-quantity-purchase-units"],
            {
                "order_sales_units": order_sales,
                "pack_factor": sku["pack_factor"],
            },
        )
        dos = evaluate(
            asts["f20-days-of-supply"],
            {"ads": row["ads"], "position": row["position"]},
        )

        # f11 is deliberately NOT compared against `ENGINE!P` here.
        #
        # They answer different questions and differ by the pack rounding
        # between them. f11 prices what the purchase order actually buys --
        # `CEILING(need / pack) x pack x price`, whole cases. `ENGINE!P` prices
        # the requirement, `ROUND(need x price)`, before any case is rounded
        # up.
        #
        # GRC-001: 43,545,600 against 43,507,800, a gap of exactly two units at
        # Rp 18,900. That gap is real inventory the PO will bring in, so both
        # numbers are right and neither should be quietly replaced by the
        # other. f11 is verified against the per-store grid, where whole cases
        # are what gets ordered, by `backend/tests/test_formula_conformance.py`.
        for name, computed, stored, tolerance in (
            # f01 carries four rounded workbook inputs into one product, so it
            # reconciles to four decimals rather than to the exact float the
            # tighter checks below use.
            ("ads", ads, row["ads"], 1e-4),
            ("open_po", open_po, row["open_po"], 1e-6),
            ("position", position, row["position"], 1e-6),
            ("rop", rop, row["rop"], 1e-6),
            ("max", max_qty, row["max"], 1e-6),
            ("dos", dos, row["dos"], 1e-4),
            ("order_units", order_sales, row["order_units"], 1e-6),
            (
                "order_buy_units",
                order_buy,
                # ceil without importing math: the same integer f10 produces.
                -(-row["order_units"] // sku["pack_factor"]),
                1e-6,
            ),
        ):
            if abs(float(computed) - float(stored)) > tolerance:
                failures.append(
                    f"{row['sku_id']} / {name}: formula {computed!r},"
                    f" workbook {stored!r}"
                )

    if failures:
        print(f"FAIL  the catalogue disagrees with ENGINE on {len(failures)} value(s):")
        for line in failures[:5]:
            print(f"      {line}")
        raise SystemExit(1)

    print(
        f"  ok  {len(expressions)} catalogue formulas rebuild {len(engine)}"
        " order lines at zero levers"
    )
    return expressions


def build_lines(engine, sku_master, detail, store_size, hz_cov):
    """One requisition line per SKU, at chain-net level."""
    by_sku = {row["item"]: row for row in detail}
    lines = []

    for row in engine:
        sku = sku_master[row["sku_id"]]
        requisition = by_sku[row["sku_id"]]
        lead = sku["lead_d"]

        lines.append(
            {
                "sku_id": row["sku_id"],
                "name": sku["item"],
                "vertical_id": row["vertical_id"],
                "category_id": row["cat_id"],
                "category_label": sku["category"],
                "route": route_for(lead),
                "lead_days": lead,
                "safety_days": sku["safety_d"],
                "perishable": row["perish"],
                # Position chain, so the reader can check the arithmetic that
                # produced the order quantity without leaving the row.
                "on_hand": row["position"] - row["open_po"],
                "open_po": row["open_po"],
                "position": row["position"],
                "rop": row["rop"],
                "max": row["max"],
                "dos": row["dos"],
                "ads": row["ads"],
                # `reorder` is the workbook's own YES/NO; `Position < ROP` is
                # the rule behind it. They agree on all 800 rows, and the
                # reconciliation below would fail if they ever stopped.
                "is_reorder": requisition["reorder"] == "YES",
                "order_qty_sales": requisition["order_qty_sales"],
                "order_qty_buy": requisition["order_qty_buy"],
                "buy_uom": requisition["buy_uom"],
                "pack_factor": sku["pack_factor"],
                # Two values, deliberately. See the module docstring.
                "order_value_retail": row["order_value"],
                "order_value_cost": requisition["amount"],
                "unit_price_retail": row["price"],
                "unit_price_trade": requisition["unit_price_ta"],
                # Sourcing. `saving_vs_designated` is what switching vendor
                # would recover on this line — the only figure on the board
                # that suggests an action rather than describing a state.
                "designated_vendor": requisition["designated_vendor"],
                "best_price_vendor": requisition["best_price_vendor"],
                "best_price": requisition["best_price"],
                "saving_vs_designated": requisition["saving_vs_designated"],
                "store_size": store_size[row["vertical_id"]],
                "base_ads": sku["base_ads"],
                "seasonality": sku["seasonality"],
                # The two v8.5 parameters. `engine.js` reads both off the line
                # -- f01 multiplies by the first, f06 adds the second -- so a
                # row without them cannot be simulated at all: the evaluator
                # raises on the missing operand rather than quietly assuming
                # one, which is what this board did until now.
                "arch_horizon_factor": sku["arch_horizon_factor"],
                "horizon_coverage": hz_cov,
                "promo_eligible": sku["promo"],
                "promo_depth": sku["cannib_pct"],
            }
        )
    return lines


def build_stores(engine_store, stores, sku_master):
    """Per-store order value, collapsed from the 16,000-row grid."""
    grouped: dict[str, dict[str, Any]] = {}
    for row in engine_store:
        bucket = grouped.get(row["store_id"])
        if bucket is None:
            store = stores[row["store_id"]]
            bucket = grouped[row["store_id"]] = {
                "store_id": row["store_id"],
                "name": store["store_name"],
                "vertical_id": store["vertical_id"],
                "cluster": store["cluster"],
                "channel": store["channel"],
                "sku_count": 0,
                "reorder_count": 0,
                "order_units": 0.0,
                "order_value_retail": 0.0,
                "open_po": 0.0,
            }
        bucket["sku_count"] += 1
        if row["position"] < row["rop"]:
            bucket["reorder_count"] += 1
        bucket["order_units"] += row["order_sales"]
        bucket["order_value_retail"] += row["order_value"]
        bucket["open_po"] += row["open_po"]

    return sorted(grouped.values(), key=lambda row: row["store_id"])


def resolve_vertical_labels(verticals, reference):
    known = {row["vertical_label"] for row in reference}
    resolved: dict[str, str] = {}
    for vertical in verticals:
        for candidate in (
            vertical["dashboard_label"],
            vertical["short"],
            vertical["vertical"],
        ):
            if candidate in known:
                resolved[vertical["vertical_id"]] = candidate
                break
        else:
            raise SystemExit(
                f"FAIL  no A3 reference row for vertical {vertical['vertical_id']}"
            )
    return resolved


def reconcile(lines, reference, label_of) -> list[str]:
    """Five of the six A3 KPIs, per vertical, against the workbook's own sheet.

    Order value is checked at RETAIL, because that is the basis the A3 sheet
    uses. The cost figure has no per-vertical total to check against; it is
    summed from the same rows and carried alongside.
    """
    failures: list[str] = []

    for vertical_id, label in sorted(label_of.items()):
        scoped = [row for row in lines if row["vertical_id"] == vertical_id]
        book = reference[label]
        need = [row for row in scoped if row["is_reorder"]]

        checks = (
            ("skus_to_reorder", len(need), book["skus_to_reorder"]),
            (
                "order_units",
                sum(row["order_qty_sales"] for row in scoped),
                book["order_units"],
            ),
            (
                "order_value",
                sum(row["order_value_retail"] for row in scoped),
                book["order_value"],
            ),
            (
                "fill_rate_pct",
                round((len(scoped) - len(need)) / len(scoped) * 100, 1),
                round(book["fill_rate_pct"], 1),
            ),
            (
                "avg_cover_d",
                round(sum(row["dos"] for row in scoped) / len(scoped), 1),
                round(book["avg_cover_d"], 1),
            ),
        )
        for name, computed, stored in checks:
            if abs(float(computed) - float(stored)) > 1e-6:
                failures.append(
                    f"{label} / {name}: computed {computed}, workbook {stored}"
                )

        # The workbook's YES/NO and the rule behind it must select the same
        # rows. If they part company, one of them has been edited.
        by_rule = [row for row in scoped if row["position"] < row["rop"]]
        if len(by_rule) != len(need):
            failures.append(
                f"{label} / reorder flag: {len(need)} marked YES but"
                f" {len(by_rule)} sit below ROP"
            )

    return failures


# Columns `Trade Agreement` holds identical across all 2,400 rows. Carried
# once instead of repeated 2,400 times -- but checked on every build, because
# "it was constant when I looked" is how a fixture starts lying. When the Azure
# source makes any of them vary, the build stops and says which one.
CONSTANT_QUOTE_TERMS = ("currency", "lead_time_d", "valid_from", "valid_to")


def quote_terms(rows: list[dict[str, Any]]) -> dict[str, Any]:
    terms: dict[str, Any] = {}
    for column in CONSTANT_QUOTE_TERMS:
        seen = {row[column] for row in rows}
        if len(seen) != 1:
            raise SystemExit(
                f"FAIL  Trade Agreement.{column} is no longer one value "
                f"({len(seen)} distinct). Move it onto the quote rows here and "
                "in backend/src/llm/agents/retail/replenishment/dashboard.py, "
                "or the two paths will disagree."
            )
        terms[column] = seen.pop()
    return {
        "currency": terms["currency"],
        "lead_time_days": terms["lead_time_d"],
        "valid_from": terms["valid_from"],
        "valid_to": terms["valid_to"],
    }


def build_quotes(trade_agreements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every vendor quote on file, one row per (SKU, vendor).

    Sorted cheapest first within a SKU so the panel does not have to, and so
    the fixture and the API -- which sorts in SQL -- can be compared row for
    row. `vendor` is the short name because that is what an order line names
    in `designated_vendor`; the account travels with it for the eventual join
    against D365.
    """
    return [
        {
            "sku_id": row["item"],
            "vendor": row["vendor"],
            "vendor_account": row["vendor_account"],
            "unit_price": row["unit_price"],
            "min_qty_break": row["min_qty_break"],
            "discount_pct": row["discount_pct"],
            "is_designated": row["designated"] == "Y",
        }
        for row in sorted(
            trade_agreements,
            key=lambda row: (row["item"], row["unit_price"], row["vendor_account"]),
        )
    ]


def verify_quotes(
    quotes: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    sku_master: dict[str, dict[str, Any]],
) -> list[str]:
    """Rebuild the three sourcing figures from the quotes, or refuse to build.

    The order line states `best_price`, `unit_price_trade` and
    `saving_vs_designated` as finished numbers. If the quotes now shipping
    beside them cannot reproduce those three, one of the two is wrong and the
    board would show a saving next to prices that do not add up to it.
    """
    by_sku: dict[str, list[dict[str, Any]]] = {}
    for quote in quotes:
        by_sku.setdefault(quote["sku_id"], []).append(quote)

    failures: list[str] = []
    for line in lines:
        sku = line["sku_id"]
        offers = by_sku.get(sku)
        if not offers:
            failures.append(f"{sku}: no trade agreement on file")
            continue

        designated = [offer for offer in offers if offer["is_designated"]]
        if len(designated) != 1:
            failures.append(f"{sku}: {len(designated)} designated vendors, expected 1")
            continue

        best = min(offer["unit_price"] for offer in offers)
        incumbent = designated[0]["unit_price"]
        # Whole packs, not the shortfall -- see THE QUOTES BEHIND above.
        units = line["order_qty_buy"] * sku_master[sku]["pack_factor"]

        if abs(line["best_price"] - best) > 1e-6:
            failures.append(f"{sku}: best_price {line['best_price']} != {best}")
        if abs(line["unit_price_trade"] - incumbent) > 1e-6:
            failures.append(
                f"{sku}: unit_price_trade {line['unit_price_trade']} != "
                f"designated quote {incumbent}"
            )
        expected = (incumbent - best) * units
        if abs(line["saving_vs_designated"] - expected) > 0.5:
            failures.append(
                f"{sku}: saving {line['saving_vs_designated']} != {expected}"
            )
    return failures


# The CSV's week columns in timeline order: actuals oldest first (w16 is 16
# weeks back), forecasts nearest first (w1 is next week). Same order the API's
# `demand_weekly_32w` emits, so the two never disagree about what index means.
DEMAND_ACTUAL_COLUMNS = tuple(f"actual_w{week}" for week in range(16, 0, -1))
DEMAND_FORECAST_COLUMNS = tuple(f"forecast_w{week}" for week in range(1, 17))


def load_demand_curves(source: Path = DEMAND_CSV) -> dict[str, dict[str, list[float]]]:
    """Per-SKU chain demand curves from the synthetic table's CSV export.

    Sums the SKU's store rows in `Decimal` and converts once at the end. The
    API sums the same values as SQL `DECIMAL(20,6)` and converts once in
    Python; two exact decimal sums of the same rows give the same float, which
    is what lets the parity test compare field for field rather than "close
    enough".
    """
    totals: dict[str, dict[str, list[Decimal]]] = {}
    with source.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            buckets = totals.setdefault(
                row["sku_id"],
                {
                    "actual": [Decimal(0)] * len(DEMAND_ACTUAL_COLUMNS),
                    "forecast": [Decimal(0)] * len(DEMAND_FORECAST_COLUMNS),
                },
            )
            for kind, columns in (
                ("actual", DEMAND_ACTUAL_COLUMNS),
                ("forecast", DEMAND_FORECAST_COLUMNS),
            ):
                for position, column in enumerate(columns):
                    buckets[kind][position] += Decimal(row[column])

    return {
        sku: {kind: [float(value) for value in curve] for kind, curve in by_kind.items()}
        for sku, by_kind in totals.items()
    }


def verify_demand_calibration(
    lines: list[dict[str, Any]],
    curves: dict[str, dict[str, list[float]]],
    dow_sum: float,
) -> list[str]:
    """The curve's first forecast week must equal the line's own ADS x dow_sum.

    The synthetic table was generated against this board: each SKU's forecast
    week one reproduces `ads x Constants!B7`, the day-of-week sum, to six
    decimals -- verified against all 800 SKUs on the live table. Holding the
    CSV to the same identity is what keeps a regenerated export from stating a
    different demand level than the ADS every other figure here reconciles
    against.
    """
    failures = []
    for line in lines:
        curve = curves.get(line["sku_id"])
        if curve is None:
            failures.append(f"{line['sku_id']}: no demand curve in the CSV")
            continue
        expected = line["ads"] * dow_sum
        if abs(curve["forecast"][0] - expected) > max(1.0, expected * 1e-6):
            failures.append(
                f"{line['sku_id']}: forecast W+1 {curve['forecast'][0]:,.2f} "
                f"!= ADS x dow_sum {expected:,.2f}"
            )
    return failures


def main() -> int:
    # A fixture built from the wrong workbook is committed to the repo
    # and read by every board in standalone mode, so it needs the same
    # check the seeders make before they touch the warehouse.
    workbook_guard.check(SOURCE)

    if not SOURCE.exists():
        print(f"FAIL  source not found: {SOURCE}")
        return 1
    if not DEMAND_CSV.exists():
        print(f"FAIL  demand-curve source not found: {DEMAND_CSV}")
        return 1

    tables = read_source()
    required = (
        "engine",
        "engine_store",
        "sku_master",
        "stores",
        "verticals",
        "replenishment_detail",
        "a3_replenishment",
        "vendors",
        "trade_agreements",
        "constants",
    )
    missing = [name for name in required if name not in tables]
    if missing:
        print(f"FAIL  source is missing tables: {', '.join(missing)}")
        return 1

    verticals = tables["verticals"]
    reference_rows = tables["a3_replenishment"]
    label_of = resolve_vertical_labels(verticals, reference_rows)
    reference = {row["vertical_label"]: row for row in reference_rows}

    sku_master = {row["sku_id"]: row for row in tables["sku_master"]}
    # v8.5's f01-ads-per-store gained an archetype/horizon factor. It isn't a
    # SKU_Master column -- it's precomputed onto ENGINE_STORE as `archhz`,
    # constant across every store for a given SKU -- so it's read off any one
    # ENGINE_STORE row per SKU and carried on sku_master like every other
    # per-SKU f01 input. Without it this board rebuilt a pre-v8.5 ADS and the
    # browser's engine threw on the first lever drag.
    for row in tables["engine_store"]:
        sku_master[row["sku_id"]]["arch_horizon_factor"] = row["archhz"]
    stores = {row["store_id"]: row for row in tables["stores"]}
    store_size = chain_store_size(tables["stores"])
    constants = {
        **constants_from_cells(
            tables["constants"],
            # `hz_cov` joins the shared pair now that this board evaluates f06:
            # the browser must use the same horizon term the rows were built
            # with or a lever drag would move Max on its own.
            {"dow_sum": "B7", "month_index": "B6", "hz_cov": "B24"},
        ),
        # Carried by every board, because `warehouse.constants()` serves one
        # block to all of them and the API path must equal this file. This
        # board does not spend a shaped day yet -- when it does, the shape is
        # already here rather than copied in for a third time.
        "dow_profile": list(DOW_PROFILE),
    }
    check_profile(constants["dow_sum"])

    expressions = verify_order_chain(
        tables["engine"], sku_master, store_size, constants["hz_cov"]
    )

    lines = build_lines(
        tables["engine"],
        sku_master,
        tables["replenishment_detail"],
        store_size,
        constants["hz_cov"],
    )
    store_rows = build_stores(tables["engine_store"], stores, sku_master)

    failures = reconcile(lines, reference, label_of)
    if failures:
        print(f"FAIL  {len(failures)} figure(s) disagree with the A3 sheet:")
        for line in failures:
            print(f"      {line}")
        return 1
    print(f"  ok  reconciled 5 KPIs across {len(label_of)} verticals")

    # The 32-week demand curve, checked against the board's own ADS before a
    # single line ships with it -- see THE 32-WEEK DEMAND CURVE above.
    curves = load_demand_curves()
    demand_failures = verify_demand_calibration(lines, curves, constants["dow_sum"])
    if demand_failures:
        print(
            f"FAIL  {len(demand_failures)} line(s) disagree with the demand CSV:"
        )
        for failure in demand_failures[:10]:
            print(f"      {failure}")
        return 1
    for line in lines:
        line["demand_weekly"] = curves[line["sku_id"]]
    print(
        f"  ok  32-week demand curve calibrated on all {len(lines)} lines "
        f"(W+1 = ADS x {constants['dow_sum']})"
    )

    categories = {}
    for row in lines:
        categories.setdefault(
            row["category_id"],
            {
                "value": row["category_id"],
                # id first: category_label is not unique across verticals
                # (e.g. DGT-C01 and OMN-C01 are both "Electronics"), so the
                # bare name alone cannot tell two dropdown entries apart.
                "label": f"{row['category_id']} · {row['category_label']}",
                "legal_entity_id": row["vertical_id"],
            },
        )

    vendors = {row["vendor"]: row for row in tables["vendors"]}

    quotes = build_quotes(tables["trade_agreements"])
    terms = quote_terms(tables["trade_agreements"])
    quote_failures = verify_quotes(quotes, lines, sku_master)
    if quote_failures:
        print(f"FAIL  {len(quote_failures)} line(s) disagree with their quotes:")
        for failure in quote_failures[:10]:
            print(f"      {failure}")
        return 1
    print(f"  ok  {len(quotes)} quotes reconcile to all {len(lines)} order lines")

    fixture = {
        "schema_version": SCHEMA_VERSION,
        "agent": AGENT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_workbook": "AI_360_Retail_Suite_v8.5_General_9Agents 20260819.xlsx",
        "is_mock": True,
        "note": (
            "Workbook demonstration data, not a live ERP position. Order value "
            "is reported twice — at selling price, which is what the A3 sheet "
            "totals, and at trade-agreement price, which is what the purchase "
            "order would actually cost."
        ),
        "constants": constants,
        "formulas": expressions,
        "routes": list(ROUTES),
        "derivation": {
            "skus_to_reorder": "measured",
            "order_units": "measured",
            "order_value_retail": "measured",
            "order_value_cost": "measured",
            "inbound_open_po": "measured",
            "fill_rate_pct": "measured",
            "avg_cover_days": "measured",
            "route": "modelled-from-lead-time",
            # Same two keys `replenishment/dashboard.py` adds when the
            # synthetic table answers: the demand curve is read, the cover
            # curve is modelled in the browser (no arrival dates exist), and
            # the derivation block is where the two are told apart.
            "requirement_curve": "measured-32w",
            "cover_curve": "modelled-lagged-demand",
        },
        "filter_options": {
            "legal_entities": [
                {
                    "value": row["vertical_id"],
                    "label": f"{row['vertical_id']} · {row['vertical']}",
                    "dashboard_label": row["dashboard_label"],
                }
                for row in verticals
            ],
            "categories": sorted(categories.values(), key=lambda row: row["value"]),
            "stores": [
                {
                    "value": row["store_id"],
                    "label": f"{row['store_id']} · {row['name']}",
                    "legal_entity_id": row["vertical_id"],
                    "cluster": row["cluster"],
                }
                for row in store_rows
            ],
            "routes": [
                {"value": route["id"], "label": route["label"]} for route in ROUTES
            ],
        },
        "lines": lines,
        "stores": store_rows,
        "quote_terms": terms,
        "quotes": quotes,
        "vendors": [
            {
                "vendor": name,
                "vendor_account": row["vendor_account"],
                "vendor_name": row["vendor_name"],
                "lead_time_days": row["lead_time_d"],
                "moq_units": row["moq_units"],
                "otif_pct": row["otif_pct"],
                "fill_pct": row["fill_pct"],
                "defect_pct": row["defect_pct"],
                "lead_adherence_pct": row["lead_adherence_pct"],
                "payment_terms": row["payment_terms"],
            }
            for name, row in sorted(vendors.items())
        ],
        "reference_by_vertical": [
            {
                "legal_entity_id": vertical_id,
                "vertical_label": label,
                **{
                    key: reference[label][key]
                    for key in (
                        "skus_to_reorder",
                        "order_units",
                        "order_value",
                        "fill_rate_pct",
                        "avg_cover_d",
                    )
                },
            }
            for vertical_id, label in sorted(label_of.items())
        ],
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temp = TARGET.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(fixture, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temp.replace(TARGET)

    size_kb = TARGET.stat().st_size / 1024
    reorder = sum(1 for row in lines if row["is_reorder"])
    saving = sum(row["saving_vs_designated"] for row in lines)
    print(f"  ok  {len(lines)} lines ({reorder} to reorder), {len(store_rows)} stores")
    print(f"  ok  Rp {saving:,.0f} recoverable by switching to best price")
    print(f"  ok  wrote {TARGET.relative_to(REPO)} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
