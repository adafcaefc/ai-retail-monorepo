"""Build the Demand Forecasting (Agent 1) dashboard fixture from the workbook.

Run it yourself:

    python scripts/build_demand_forecasting_fixture.py

Input:  resources/dbtemp/schema_with_data.json  (produced by extract_workbook_schema.py)
        resources/dbtemp/formula.json           (the formula catalogue)
Output: frontend/src/agents/retail/demand_forecasting/data/fixture.json

WHAT THIS REPLACES
`mockDataset.js` invented four legal entities (two of which -- HBA, HME -- do
not exist), twelve categories, sixteen stores and four hundred SKUs from a hash
of the row index. This script reads the real eight verticals, 160 categories,
160 stores and 800 SKUs instead, so a code like `GRC-001` means the same
product on this board as it does on Inventory Risk. Dimension values are join
keys; two boards that disagree about them cannot be connected later.

WHAT THE WORKBOOK ACTUALLY COMPUTES FOR A1
Almost nothing. The `A1 Demand Forecasting` sheet holds six columns, and only
the first is a formula:

    Forecast 7d      =SUMIFS(ENGINE_STORE!U, vertical)     <- computed
    Accuracy %       92.4                                  <- typed
    Trend %          5.6, 8.7, 6.9, ...                    <- typed
    Stockout-risk    46, 31, 39, ...                       <- typed
    Trending SKUs    47, 39, 44, ...                       <- typed
    Seasonality idx  114, 100, 98, ...                     <- typed

So five of the six KPIs are constants somebody keyed in. This script keeps
them, because they are the workbook's own numbers and the board reconciles
against them -- but it never presents them as calculations, and
`derivation` in the payload records which is which.

Stockout-risk is the exception worth naming: A1 types 46 where A2 computes the
same 46 from `Position < ROP`. This script computes it, so the two boards
cannot drift apart on a KPI they both display.

TIME SERIES: WHAT `time_series_24mo` REALLY IS
Not history. Its second year is byte-identical to its first in all eight
verticals, so year-on-year growth is exactly zero by construction. It is one
seasonal profile written twice.

That makes it useless as actuals and perfect as a seasonal index, which is how
it is used here: monthly GMV divided by the series mean gives twelve classical
seasonal indices per vertical. No actuals line is emitted at all, because there
are no actuals -- see `docs/RETAIL_FORMULA_SOURCES.md` for the full ledger of what
is measured, what is modelled and what is a placeholder.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.formulas import repository  # noqa: E402
from src.formulas.expression import evaluate, parse  # noqa: E402

SOURCE = REPO / "resources" / "dbtemp" / "schema_with_data.json"
TARGET = (
    REPO
    / "frontend"
    / "src"
    / "agents"
    / "retail"
    / "demand_forecasting"
    / "data"
    / "fixture.json"
)

SCHEMA_VERSION = 1
AGENT_ID = "retail.demand_forecasting"

# The chain the What-If levers run through. Identical to Inventory Risk's set
# minus the value formulas it does not need, because both boards must answer
# "how many SKUs are below ROP" the same way under the same levers.
CATALOGUE_FORMULAS = (
    "f01-ads-per-store",
    "f03-open-po-per-store",
    "f04-position",
    "f05-rop",
    "f06-maximum-inventory",
    "f07-inventory-state",
    "f08-forecast-7-days",
    "f20-days-of-supply",
)

# Day-of-week demand profile, Monday first.
#
# Not in the workbook as seven numbers -- but `Constants` B7 stores their sum,
# 7.45, and f08 multiplies ADS by it to get a week. These seven allocate that
# total across the week and sum to exactly 7.45, so any daily view rolls back
# up to the weekly figure the workbook publishes.
#
# The shape is the ordinary Indonesian retail week: flat Monday to Thursday,
# lifting into the weekend, peaking Saturday. It is a modelled allocation of a
# measured total, and the payload says so.
DOW_PROFILE = (0.85, 0.90, 0.95, 1.00, 1.15, 1.35, 1.25)

# z for a two-sided 90% prediction interval.
#
# This is what puts a number on the A1 spec's "band ±12%". Forecast error grows
# with the square root of the horizon (variance accumulates linearly under a
# random walk), so the band at horizon h is
#
#     yhat +/- z * (1 - accuracy/100) * sqrt(h)
#
# At h = 1 with the workbook's 92.4% accuracy that is 1.645 * 0.076 = 12.5%,
# which is where the spec's flat ±12% comes from. Stating it this way makes the
# band widen with horizon, as a prediction interval must.
INTERVAL_Z = 1.645

MONTH_LABELS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _designated_lead_times(tables: dict) -> dict:
    """Lead time per item, from the DESIGNATED trade agreement row.

    NOT `sku_master.lead_d`. The workbook's ROP reads
    `SUMIFS('Trade Agreement'!H, item, designated="Y")`, and the two disagree --
    GRC-005 is 2 days in the master and 6 in the agreement. Feeding f05 the
    master column reproduces neither ROP nor Max. Exactly one row per item
    carries `designated = "Y"`.
    """
    return {
        row["item"]: row["lead_time_d"]
        for row in tables["trade_agreements"]
        if str(row["designated"]).strip().upper() == "Y"
    }


def read_source() -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = [dict(zip(names, row)) for row in table["rows"]]
    return tables


def constants_from_cells(
    constants: list[dict[str, Any]],
    wanted: dict[str, str],
) -> dict[str, Any]:
    """Pull named model parameters out of `Constants` by cell address."""
    by_cell = {row["source_cell"]: row for row in constants}
    resolved = {}
    for name, cell in wanted.items():
        if cell not in by_cell:
            raise SystemExit(f"FAIL  Constants!{cell} ({name}) is not in the extract")
        resolved[name] = by_cell[cell]["value"]
    return resolved


def chain_store_size(stores: list[dict[str, Any]]) -> dict[str, float]:
    """Total store-size index per vertical, so f01 applies at chain-net grain."""
    totals: dict[str, float] = {}
    for store in stores:
        totals[store["vertical_id"]] = (
            totals.get(store["vertical_id"], 0.0) + store["size"]
        )
    return totals


def seasonal_indices(
    series: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """Twelve classical seasonal indices per vertical, from monthly GMV.

    Textbook decomposition: each calendar month's average divided by the
    series average. The workbook's series repeats one year twice, so the two
    observations per month are the same number -- which makes the average
    exact rather than noisy, and means no de-trending step is needed. There is
    no trend to remove.

    These are NOT the `Seasonality idx` KPI. That column is typed into the A1
    sheet and does not agree with this calculation (Grocery: 114 typed against
    108.3 derived). Both are kept, and the payload labels which is which.
    """
    months: dict[str, list[str]] = {}
    values: dict[str, dict[str, float]] = {}

    for row in series:
        vertical = row["vertical_id"]
        values.setdefault(vertical, {})[row["month"]] = row["gmv"]
        order = months.setdefault(vertical, [])
        if row["month"] not in order:
            order.append(row["month"])

    indices: dict[str, list[float]] = {}
    for vertical, order in months.items():
        observations = [values[vertical][month] for month in order]
        if len(observations) % 12:
            raise SystemExit(
                f"FAIL  {vertical} has {len(observations)} months, not a whole"
                " number of years"
            )
        mean = sum(observations) / len(observations)
        years = len(observations) // 12
        indices[vertical] = [
            sum(observations[month + 12 * year] for year in range(years))
            / years
            / mean
            for month in range(12)
        ]

    return indices


def verify_engine_chain(
    engine: list[dict[str, Any]],
    sku_master: dict[str, dict[str, Any]],
    store_size: dict[str, float],
    week_factor: float,
    lead_times: dict[str, float],
) -> dict[str, str]:
    """Rebuild every chain-net row from the catalogue and insist it matches.

    Same contract as the Inventory Risk builder: the What-If panel recomputes
    these expressions when a lever moves, so the fixture is only written if the
    expressions reproduce it at rest.
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
                "store_size": size,
                "demand_lever": 0,
                "promo_eligible": sku["promo"],
                "promo_lever": 0,
                "promo_depth": sku["cannib_pct"],
            },
        )
        rop = evaluate(
            asts["f05-rop"],
            {
                "ads": row["ads"],
                "lead_time_days": lead_times.get(
                    row["sku_id"], sku["lead_d"]
                ),
                "lead_time_adjust": 0,
                "safety_days": sku["safety_d"],
                "safety_adjust": 0,
            },
        )
        forecast = evaluate(
            asts["f08-forecast-7-days"],
            {"ads": row["ads"], "week_factor": week_factor},
        )

        for name, computed, stored in (
            ("ads", ads, row["ads"]),
            ("rop", rop, row["rop"]),
            # ENGINE has no forecast column; ENGINE_STORE!U sums to the A1
            # sheet, and this is the same product at chain-net grain.
            ("forecast_7d", forecast, row["ads"] * week_factor),
        ):
            if abs(float(computed) - float(stored)) > 1e-6:
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
        " chain-net rows at zero levers"
    )
    return expressions


def build_items(
    engine: list[dict[str, Any]],
    sku_master: dict[str, dict[str, Any]],
    store_size: dict[str, float],
    week_factor: float,
) -> list[dict[str, Any]]:
    """One row per SKU at chain-net level."""
    items = []
    for row in engine:
        sku = sku_master[row["sku_id"]]
        signals = []
        if sku["viral"] == "Y":
            signals.append("viral")
        if sku["promo"] == "Y":
            signals.append("promo")
        # The complement of f07's `velocity < 1` test, so "growth" here and
        # "Slow-mover" on the Inventory Risk board cannot both be true.
        if sku["growth"] >= 1.0:
            signals.append("growth")

        items.append(
            {
                "sku_id": row["sku_id"],
                "name": sku["item"],
                "vertical_id": row["vertical_id"],
                "category_id": row["cat_id"],
                "category_label": sku["category"],
                "ads": row["ads"],
                "forecast_7d": row["ads"] * week_factor,
                "price": row["price"],
                "growth": sku["growth"],
                "state": row["state"],
                "is_stockout_risk": row["position"] < row["rop"],
                "is_trending": is_trending(sku),
                "signals": signals,
                # What-If parameters, identical in meaning to the Inventory
                # Risk fixture's so both boards move the same way.
                "base_ads": sku["base_ads"],
                "seasonality": sku["seasonality"],
                "store_size": store_size[row["vertical_id"]],
                "promo_eligible": sku["promo"],
                "promo_depth": sku["cannib_pct"],
                "lead_days": sku["lead_d"],
                "safety_days": sku["safety_d"],
                "perishable": row["perish"],
                "shelf_life_days": sku["expiry_d"],
                "on_hand": row["position"] - row["open_po"],
                "open_po": row["open_po"],
                "position": row["position"],
                "rop": row["rop"],
            }
        )
    return items


def is_trending(sku: dict[str, Any]) -> bool:
    """The A1 spec's own test: `count(viral OR growth>1.25)`.

    A per-SKU predicate, not a rank+quota allocation against the sheet's
    vertical-wide `Trending SKUs` count -- it composes correctly under any
    later UI-level scoping (category, store) because it never depends on how
    many other SKUs are in the group. It still reconciles exactly to the
    workbook's typed count at vertical grain -- see `reconcile()` -- it is no
    longer *forced* to.
    """
    return sku["viral"] == "Y" or sku["growth"] > 1.25


def build_stores(
    engine_store: list[dict[str, Any]],
    stores: dict[str, dict[str, Any]],
    week_factor: float,
) -> list[dict[str, Any]]:
    """Per-store forecast, collapsed from the 16,000-row grid."""
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
                "forecast_7d": 0.0,
            }
        bucket["sku_count"] += 1
        bucket["forecast_7d"] += row["ads"] * week_factor

    return sorted(grouped.values(), key=lambda row: row["store_id"])


def resolve_vertical_labels(
    verticals: list[dict[str, Any]],
    reference: list[dict[str, Any]],
) -> dict[str, str]:
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
                f"FAIL  no A1 reference row for vertical {vertical['vertical_id']}"
            )
    return resolved


def reconcile(
    items: list[dict[str, Any]],
    reference: dict[str, dict[str, Any]],
    label_of: dict[str, str],
    a2_reference: dict[str, dict[str, Any]],
) -> list[str]:
    """Diff the computable KPIs against the workbook, per vertical.

    Forecast 7d comes from A1, whose own column is a live SUMIFS. The
    stockout-risk count comes from A2, because A1 holds that one as a pasted
    value and froze at the pre-fix number.

    Only two of the six can be checked, because only two are calculated
    anywhere: Forecast 7d (the sheet's own SUMIFS) and Stockout-risk SKUs
    (which the A2 sheet computes and A1 types). The other four are constants
    and are copied through, not verified -- there is nothing to verify them
    against.
    """
    failures: list[str] = []

    for vertical_id, label in sorted(label_of.items()):
        scoped = [row for row in items if row["vertical_id"] == vertical_id]
        book = reference[label]

        forecast = sum(row["forecast_7d"] for row in scoped)
        if abs(forecast - book["forecast_7d"]) > 1e-3:
            failures.append(
                f"{label} / forecast_7d: computed {forecast}, workbook"
                f" {book['forecast_7d']}"
            )

        # Checked against `A2 Inventory Risk`, not this board's own `A1`.
        # A1 carries this metric as a pasted value -- only its `Forecast 7d`
        # column is a formula -- so it still reads the pre-fix 302 across its
        # verticals. A2 computes the same metric and recomputed to 438, which
        # is `position < rop` over ENGINE row for row.
        at_risk = sum(1 for row in scoped if row["is_stockout_risk"])
        expected_at_risk = a2_reference[label]["stockout_risk_skus"]
        if at_risk != expected_at_risk:
            failures.append(
                f"{label} / stockout_risk_skus: computed {at_risk},"
                f" A2 {expected_at_risk}"
            )

        trending = sum(1 for row in scoped if row["is_trending"])
        if trending != book["trending_skus"]:
            failures.append(
                f"{label} / trending_skus: allocated {trending}, workbook"
                f" {book['trending_skus']}"
            )

    return failures


def main() -> int:
    if not SOURCE.exists():
        print(f"FAIL  source not found: {SOURCE}")
        return 1

    tables = read_source()
    required = (
        "engine",
        "engine_store",
        "sku_master",
        "stores",
        "categories",
        "verticals",
        "a1_demand_forecasting",
        "time_series_24mo",
        "constants",
    )
    missing = [name for name in required if name not in tables]
    if missing:
        print(f"FAIL  source is missing tables: {', '.join(missing)}")
        return 1

    verticals = tables["verticals"]
    reference_rows = tables["a1_demand_forecasting"]
    label_of = resolve_vertical_labels(verticals, reference_rows)
    reference = {row["vertical_label"]: row for row in reference_rows}

    sku_master = {row["sku_id"]: row for row in tables["sku_master"]}
    stores = {row["store_id"]: row for row in tables["stores"]}
    store_size = chain_store_size(tables["stores"])
    constants = constants_from_cells(
        tables["constants"], {"dow_sum": "B7", "month_index": "B6"}
    )

    expressions = verify_engine_chain(
        tables["engine"],
        sku_master,
        store_size,
        constants["dow_sum"],
        _designated_lead_times(tables),
    )

    items = build_items(
        tables["engine"],
        sku_master,
        store_size,
        constants["dow_sum"],
    )
    store_rows = build_stores(
        tables["engine_store"], stores, constants["dow_sum"]
    )

    # A2 supplies the stockout-risk count: A1 carries it as a pasted value
    # and still reads the pre-ROP-fix number.
    a2_reference = {
        row["vertical_label"]: row for row in tables["a2_inventory_risk"]
    }
    failures = reconcile(items, reference, label_of, a2_reference)
    if failures:
        print(f"FAIL  {len(failures)} figure(s) disagree with the A1 sheet:")
        for line in failures:
            print(f"      {line}")
        return 1
    print(f"  ok  reconciled 3 measures across {len(label_of)} verticals")

    indices = seasonal_indices(tables["time_series_24mo"])
    month_index = int(constants["month_index"])

    categories = {}
    for row in items:
        categories.setdefault(
            row["category_id"],
            {
                "value": row["category_id"],
                "label": row["category_label"],
                "legal_entity_id": row["vertical_id"],
            },
        )

    fixture = {
        "schema_version": SCHEMA_VERSION,
        "agent": AGENT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_workbook": "Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx",
        "is_mock": True,
        "note": (
            "Workbook demonstration data. Forecast 7d and the reorder position "
            "are calculated; accuracy, trend and the seasonality index are "
            "constants typed into the A1 sheet, and no sales history exists at "
            "any grain."
        ),
        "constants": {
            **constants,
            "dow_profile": list(DOW_PROFILE),
            "interval_z": INTERVAL_Z,
        },
        "formulas": expressions,
        # Which figures are measured, which are modelled, which are typed. The
        # UI reads this to label them; nothing else decides it.
        "derivation": {
            "forecast_next_7d": "measured",
            "stockout_risk_skus": "measured",
            "predicted_to_trend": "measured-formula",
            "forecast_accuracy": "typed-constant",
            "demand_trend": "typed-constant",
            "seasonality_index": "typed-constant",
            "seasonality_curve": "derived-from-gmv-profile",
            "history": "unavailable",
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
        },
        "items": items,
        "stores": store_rows,
        # Twelve seasonal indices per vertical, and the month the workbook says
        # it is (`Constants` B6). Used for the seasonality chart and to shape
        # the forecast curve.
        "seasonality": {
            "month_labels": list(MONTH_LABELS),
            "current_month_index": month_index,
            "by_legal_entity": {
                vertical_id: [round(value * 100, 4) for value in indices[vertical_id]]
                for vertical_id in indices
            },
        },
        "reference_by_vertical": [
            {
                "legal_entity_id": vertical_id,
                "vertical_label": label,
                **{
                    key: reference[label][key]
                    for key in (
                        "forecast_7d",
                        "accuracy_pct",
                        "trend_pct",
                        "stockout_risk_skus",
                        "trending_skus",
                        "seasonality_idx",
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
    print(f"  ok  {len(items)} items, {len(store_rows)} stores")
    print(f"  ok  wrote {TARGET.relative_to(REPO)} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
