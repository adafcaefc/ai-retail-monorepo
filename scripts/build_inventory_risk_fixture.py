"""Build the Inventory Risk (Agent 2) dashboard fixture from the workbook data.

Run it yourself:

    python scripts/build_inventory_risk_fixture.py

Input:  resources/dbtemp/schema_with_data.json  (produced by extract_workbook_schema.py)
Output: frontend/src/agents/retail/inventory_risk/data/fixture.json

WHY A FIXTURE AND NOT A MOCK ENGINE
The Demand Forecasting dashboard had to invent its numbers, because forecast
data does not exist anywhere yet. Inventory Risk is the opposite case: every
figure the A2 spec asks for is already computed and stored in the workbook, and
this script has verified it reconciles. So the frontend reads numbers here, it
never re-derives them.

In particular the state classification (Stockout / Low / Expiry / Overstock /
Slow-mover / Healthy) and the three KPI predicates are resolved HERE, into
`state` plus the `is_*` booleans on every item row. The React side only ever
counts flags and sums columns.

WHERE THE RULES LIVE
Nowhere in this file. `DoS > 15`, `DoS > 10` and `growth < 1.0` used to be
typed out below, which made this script a second definition of rules the
workbook already owns -- and a second definition is one that will eventually
disagree with the first. They are gone. Every `is_*` flag is now either a
comparison the workbook's own KPI formula makes (`Position < ROP`, straight
from `A2 Inventory Risk!B`) or a reading of the state the workbook already
resolved.

The one place the thresholds live is `resources/dbtemp/formula.json`,
`f07-inventory-state`. `verify_engine_chain` re-derives all 800 rows from it
and six sibling formulas before anything is written, so the link between that
file and this fixture is asserted rather than assumed.

RECONCILIATION
Before writing anything, the six KPIs are recomputed per vertical from the
item rows and compared against the workbook's own `A2 Inventory Risk` sheet.
A mismatch aborts the build. That check is the whole reason this file can be
trusted; do not weaken it into a warning.

DATA HONESTY
The numbers are internally consistent but they are demonstration data, not a
live ERP position. Per A2 spec section 10 note 5, on-hand in the source
workbook is pseudo-random in the SKU id (`stockFactor = 0.4 + ((id*37)%100)/58`).
The payload therefore carries `is_mock: true` and a note, and the UI is
expected to label it rather than present it as measured stock.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))  # `scripts/` is not a package

import workbook_guard  # noqa: E402
from retail_demand_model import (  # noqa: E402
    DOW_PROFILE,
    check_profile,
    seasonality_payload,
)
from src.formulas import repository  # noqa: E402
from src.formulas.expression import evaluate, parse  # noqa: E402

SOURCE = REPO / "resources" / "dbtemp" / "schema_with_data.json"
TARGET = (
    REPO
    / "frontend"
    / "src"
    / "agents"
    / "retail"
    / "inventory_risk"
    / "data"
    / "fixture.json"
)

SCHEMA_VERSION = 1
AGENT_ID = "retail.inventory_risk"

# A2 spec section 5c: severity ordering for the risk register, and the agent a
# row hands off to. Stockout/Low are a replenishment problem; everything else
# is a markdown/assortment problem.
STATE_ORDER = ("Stockout", "Low", "Expiry", "Overstock", "Slow-mover", "Healthy")
REPLENISH_STATES = frozenset({"Stockout", "Low"})

# Every formula this fixture needs, all of them from the catalogue.
#
# f20 to f22 are ENGINE columns I, L and N. They were briefly transcribed here
# instead, because the workbook's `Formulas` sheet lists nineteen rows and does
# not include them -- but they are real workbook formulas with real cells, so
# the right home was always `resources/formula.md`, with five cell-cited worked
# examples apiece like every other entry. That is where they now live.
#
# Nothing in this file states a rule any more.
CATALOGUE_FORMULAS = (
    "f01-ads-per-store",
    "f03-open-po-per-store",
    "f04-position",
    "f05-rop",
    "f06-maximum-inventory",
    "f07-inventory-state",
    "f12-at-risk-value",
    "f20-days-of-supply",
    "f21-inventory-value",
    "f22-expiry-units",
)


def read_source() -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = [dict(zip(names, row)) for row in table["rows"]]
    return tables


def resolve_vertical_labels(
    verticals: list[dict[str, Any]],
    reference: list[dict[str, Any]],
) -> dict[str, str]:
    """Map vertical_id -> the label the A2 sheet uses for the same vertical.

    The workbook is not consistent about this: `Verticals` carries `vertical`,
    `short`, and the A-sheet `dashboard_label`, and the A2 sheet keys on
    whichever of those its author typed. Try each, and fail loudly rather than
    silently dropping a vertical out of the reconciliation.
    """
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
                f"FAIL  no A2 reference row for vertical {vertical['vertical_id']}"
                f" (tried {vertical['dashboard_label']!r},"
                f" {vertical['short']!r}, {vertical['vertical']!r})"
            )
    return resolved


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
    """Total store-size index per vertical.

    `f01-ads-per-store` reads a single store's size index. A chain-net row is
    that same formula summed over every store in the vertical, and because
    `base_ads` and `seasonality` are SKU attributes rather than store ones,
    the sum factorises: pass the vertical's total size index as `store_size`
    and f01 returns the chain-net ADS unchanged.

    Do not substitute `sku_master.sum_vert_size` here. It carries the same
    quantity rounded to four decimals (Grocery: 20.8447 against a true
    20.8445), which is close enough to look right and far enough to make the
    verification below fail.
    """
    totals: dict[str, float] = {}
    for store in stores:
        totals[store["vertical_id"]] = (
            totals.get(store["vertical_id"], 0.0) + store["size"]
        )
    return totals


def verify_engine_chain(
    engine: list[dict[str, Any]],
    sku_master: dict[str, dict[str, Any]],
    store_size: dict[str, float],
) -> dict[str, str]:
    """Rebuild every chain-net row from `formula.json` and insist it matches.

    This script reads its figures straight out of the workbook rather than
    computing them, which is the right way round. But the What-If panel
    downstream *does* recompute them, from these same expressions, the moment a
    lever leaves zero. If the expressions and this fixture ever describe
    different rules, the board would change its mind about a SKU as soon as a
    slider moved, with nothing on screen to explain why.

    So the whole chain is re-derived here at zero levers -- ADS, open PO, ROP,
    Max, state -- and compared against the 800 rows about to be written. Zero
    levers is the setting the workbook itself was calculated at (`Constants`
    B16-B21), so agreement here means the engine and the workbook start from
    the same place.

    `backend/tests/test_formula_conformance.py` makes the same argument against
    the 16,000-row per-store grid. This one costs a second and keeps the
    guarantee attached to the artefact it protects: a fixture that cannot prove
    this is not written at all.
    """
    formulas = {formula["id"]: formula for formula in repository.load()}
    wanted = CATALOGUE_FORMULAS
    missing = [key for key in wanted if key not in formulas]
    if missing:
        raise SystemExit(
            f"FAIL  formula.json is missing {', '.join(missing)}; the rules"
            " this fixture depends on have no home"
        )

    expressions = {key: formulas[key]["expression"] for key in wanted}
    asts = {key: parse(expression) for key, expression in expressions.items()}
    failures: list[str] = []

    def agrees(computed: Any, stored: Any) -> bool:
        if isinstance(stored, str):
            return computed == stored
        return abs(float(computed) - float(stored)) <= 1e-6

    for row in engine:
        sku = sku_master[row["sku_id"]]
        size = store_size[row["vertical_id"]]

        checks: list[tuple[str, Any, Any]] = [
            (
                "ads",
                evaluate(
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
                ),
                row["ads"],
            ),
            (
                "open_po",
                evaluate(
                    asts["f03-open-po-per-store"],
                    {
                        # Ratio of one: a chain-net row already covers every
                        # store, so there is no allocation left to do.
                        "open_po_total": row["open_po"],
                        "store_size": size,
                        "total_store_size": size,
                        "inbound_lever": 0,
                    },
                ),
                row["open_po"],
            ),
        ]

        reorder = {
            "ads": row["ads"],
            "lead_time_days": sku["lead_d"],
            "lead_time_adjust": 0,
            "safety_days": sku["safety_d"],
            "safety_adjust": 0,
        }
        checks.append(("rop", evaluate(asts["f05-rop"], reorder), row["rop"]))
        checks.append(
            ("max", evaluate(asts["f06-maximum-inventory"], reorder), row["max"])
        )
        checks.append(
            (
                "state",
                evaluate(
                    asts["f07-inventory-state"],
                    {
                        "position": row["position"],
                        "rop": row["rop"],
                        "perishable": row["perish"],
                        "days_of_supply": row["dos"],
                        "shelf_life_days": sku["expiry_d"],
                        "velocity": sku["growth"],
                    },
                ),
                row["state"],
            )
        )
        checks.append(
            (
                "at_risk",
                evaluate(
                    asts["f12-at-risk-value"],
                    {
                        "state": row["state"],
                        "position": row["position"],
                        "price": row["price"],
                    },
                ),
                row["at_risk"],
            )
        )
        # Definitional at zero levers, since this fixture derives on-hand as
        # Position - Open PO. Checked anyway so the expression cannot ship
        # unexercised: What-If runs it with a scaled Open PO, where it is not.
        checks.append(
            (
                "position",
                evaluate(
                    asts["f04-position"],
                    {
                        "on_hand": row["position"] - row["open_po"],
                        "open_po": row["open_po"],
                    },
                ),
                row["position"],
            )
        )

        # ENGINE columns I, L and N -- catalogue entries 20 to 22.
        checks.append(
            (
                "dos",
                evaluate(
                    asts["f20-days-of-supply"],
                    {"ads": row["ads"], "position": row["position"]},
                ),
                row["dos"],
            )
        )
        checks.append(
            (
                "inv_value",
                evaluate(
                    asts["f21-inventory-value"],
                    {"position": row["position"], "price": row["price"]},
                ),
                row["inv_value"],
            )
        )
        checks.append(
            (
                "expiry_units",
                evaluate(
                    asts["f22-expiry-units"],
                    {
                        "perishable": row["perish"],
                        "position": row["position"],
                        "ads": row["ads"],
                        "shelf_life_days": sku["expiry_d"],
                    },
                ),
                row["expiry_u"],
            )
        )

        for name, computed, stored in checks:
            if not agrees(computed, stored):
                failures.append(
                    f"{row['sku_id']} / {name}: formula {computed!r},"
                    f" workbook {stored!r}"
                )

    if failures:
        print(
            f"FAIL  formula.json disagrees with ENGINE on {len(failures)}"
            f" value(s) across {len(engine)} rows:"
        )
        for line in failures[:5]:
            print(f"      {line}")
        raise SystemExit(1)

    print(
        f"  ok  {len(expressions)} catalogue formulas rebuild {len(engine)}"
        " chain-net rows at zero levers"
    )
    # Returned so the fixture can carry the exact expressions that were just
    # verified. Shipping them together is what stops the browser evaluating a
    # formula.json that nobody checked against this data.
    return expressions


def verify_store_derivation(
    engine_store: list[dict[str, Any]],
    engine: list[dict[str, Any]],
    sku_master: dict[str, dict[str, Any]],
    stores: dict[str, dict[str, Any]],
    store_size: dict[str, float],
) -> None:
    """Prove one store's position is derivable, before promising it downstream.

    The store filter used to be disabled with the note "needs the per-store
    dataset, not yet available". That was true of the dataset and false of the
    arithmetic: `ENGINE_STORE` is not an independent measurement, it is the SKU
    attributes crossed with the store attributes. Three products reproduce it.

        ads      = base_ads * seasonality * store.size
        on_hand  = base_ads * onhand_days * stock_factor
                   * store.health * store.size
        open_po  = open_po_chain * (store.size / total_size_in_vertical)

    So the board can scope to a store by carrying two extra numbers per SKU and
    two per store -- about 960 values -- instead of the 16,000-row grid those
    same values generate.

    That is a strong claim, so it is checked rather than asserted, over every
    row, every time this fixture is built. `open_po` gets a 1e-3 tolerance
    because the workbook stores it rounded; the other two must be exact.

    If this ever fails, the store filter is lying and must go back to disabled
    -- do not widen the tolerance to make it pass.
    """
    chain = {row["sku_id"]: row for row in engine}
    failures: list[str] = []

    for row in engine_store:
        sku = sku_master[row["sku_id"]]
        store = stores[row["store_id"]]
        ratio = store["size"] / store_size[store["vertical_id"]]

        checks = (
            ("ads", sku["base_ads"] * sku["seasonality"] * store["size"], row["ads"], 1e-9),
            (
                "on_hand",
                sku["base_ads"]
                * sku["onhand_days"]
                * sku["stockf"]
                * store["health"]
                * store["size"],
                row["on_hand"],
                1e-9,
            ),
            (
                "open_po",
                chain[row["sku_id"]]["open_po"] * ratio,
                row["open_po"],
                1e-3,
            ),
        )
        for name, computed, stored, tolerance in checks:
            if abs(computed - stored) > tolerance:
                failures.append(
                    f"{row['sku_id']}@{row['store_id']} / {name}:"
                    f" derived {computed!r}, workbook {stored!r}"
                )

    if failures:
        print(
            f"FAIL  the per-store derivation disagrees with ENGINE_STORE on"
            f" {len(failures)} value(s) across {len(engine_store)} rows:"
        )
        for line in failures[:5]:
            print(f"      {line}")
        raise SystemExit(1)

    print(
        f"  ok  per-store derivation reproduces {len(engine_store)}"
        " ENGINE_STORE rows from SKU x store attributes"
    )


def build_items(
    engine: list[dict[str, Any]],
    sku_master: dict[str, dict[str, Any]],
    store_size: dict[str, float],
) -> list[dict[str, Any]]:
    """One row per SKU at chain-net level, with every predicate pre-resolved."""
    items = []
    for row in engine:
        sku = sku_master[row["sku_id"]]
        dos = row["dos"]
        growth = sku["growth"]
        state = row["state"]

        items.append(
            {
                "sku_id": row["sku_id"],
                "name": sku["item"],
                "vertical_id": row["vertical_id"],
                "category_id": row["cat_id"],
                "category_name": sku["category"],
                "brand": row["brand"],
                "vendor": row["vendor"],
                "state": state,
                "severity_rank": STATE_ORDER.index(state),
                # A2 spec 5c: Position = On-Hand + Open PO, so on-hand is the
                # difference. The workbook stores Position and Open PO, not
                # on-hand, so it is derived here once instead of in the UI.
                "on_hand": row["position"] - row["open_po"],
                "open_po": row["open_po"],
                "position": row["position"],
                "rop": row["rop"],
                "max": row["max"],
                "dos": dos,
                "ads": row["ads"],
                "price": row["price"],
                "inv_value": row["inv_value"],
                "at_risk_value": row["at_risk"],
                "expiry_units": row["expiry_u"],
                "shelf_life_days": sku["expiry_d"],
                "is_perishable": str(row["perish"]).strip().upper() == "Y",
                "growth": growth,
                # The three KPI predicates, each written the way the workbook's
                # own A2 sheet writes it -- so none of them restates a rule.
                #
                #   #1 Stockout-risk  A2!B = SUMPRODUCT((ENGINE!F < ENGINE!G))
                #   #2 Overstock      A2!C = COUNTIFS(ENGINE!J, "Overstock")
                #   #4 Slow-moving           ENGINE!J = "Slow-mover"
                #
                # Two of these used to be predicates over DoS instead, copied
                # from the A2 spec's "Formula (card fx)" column. That column and
                # the "Data di workbook" column beside it do not agree, and the
                # spec presents them as if they did:
                #
                #   dos > 15                -> 40   state == "Overstock"  -> 40
                #   growth < 1 and dos > 10 -> 62   state == "Slow-mover" -> 51
                #
                # Overstock agreed only by luck of this dataset (no perishable
                # SKU sits above 15 days without being Expiry first). Slow-mover
                # never agreed: 11 SKUs satisfy the raw predicate but were
                # already claimed by a higher-severity state, so the card read
                # 62 while the state chart and the register below it showed 51.
                # The board contradicted itself.
                "is_stockout_risk": row["position"] < row["rop"],
                "is_overstock": state == "Overstock",
                "is_slow_mover": state == "Slow-mover",
                # -- What-If inputs -------------------------------------
                # Everything below exists so the browser can re-evaluate
                # f01/f03/f05/f06/f07 when a lever moves. They are formula
                # *parameters*, never answers: nothing reads them to decide
                # anything, and `verify_engine_chain` has already proved that
                # feeding them back through the expressions at zero levers
                # returns the columns above unchanged.
                "base_ads": sku["base_ads"],
                "seasonality": sku["seasonality"],
                # The vertical's total size index, not one store's. See
                # `chain_store_size` for why f01 still applies.
                "store_size": store_size[row["vertical_id"]],
                # -- Per-store derivation inputs ------------------------
                # These two, with a store's own `size_index` and
                # `health_index`, reproduce that store's on-hand exactly:
                #
                #   on_hand = base_ads * onhand_days * stock_factor
                #             * store.health * store.size
                #
                # `verify_store_derivation` proves it over all 16,000
                # ENGINE_STORE rows before this file is written. Carrying two
                # numbers per SKU rather than the grid itself is what lets the
                # store filter work without ~163 KB of extra payload.
                "onhand_days": sku["onhand_days"],
                "stock_factor": sku["stockf"],
                "promo_eligible": sku["promo"],
                "promo_depth": sku["cannib_pct"],
                "lead_days": sku["lead_d"],
                "safety_days": sku["safety_d"],
                "perishable": row["perish"],
                "next_agent": (
                    "3 Replenish" if state in REPLENISH_STATES else "5 Markdown"
                ),
            }
        )
    return items


def build_store_rows(
    engine_store: list[dict[str, Any]],
    stores: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-store aggregates.

    The raw per-store grid is 16,000 rows / ~4.2 MB, and every A2 visual that
    uses it (stockout-risk by store, at-risk by cluster) only ever renders an
    aggregate. Collapsing here turns 4.2 MB into ~5 KB with no loss of what is
    actually drawn. Cluster totals are grouped from these rows in the UI, so
    there is no separate cluster table.

    Note these are GROSS per-store figures. A2 spec section 6 and section 10
    note 1: they sum local pockets of risk and will exceed the chain-net
    headline, which nets surplus against shortage across stores. That
    difference is intentional and must be labelled, not reconciled away.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for row in engine_store:
        store_id = row["store_id"]
        bucket = grouped.get(store_id)
        if bucket is None:
            store = stores[store_id]
            bucket = grouped[store_id] = {
                "store_id": store_id,
                "name": store["store_name"],
                "vertical_id": store["vertical_id"],
                "cluster": store["cluster"],
                "channel": store["channel"],
                # The two store attributes the per-store derivation needs.
                # `size_index` also drives f01 and the f03 allocation ratio,
                # so a store-scoped board reads them rather than a stored grid.
                "size_index": store["size"],
                "health_index": store["health"],
                "sku_count": 0,
                # Broken out per state so the store chart can stack segments
                # that add up to sku_count. Rendering a partial breakdown as if
                # it covered the whole store is how the earlier version of that
                # chart came to leave SKUs out of every bar.
                "stockout_count": 0,
                "low_count": 0,
                "other_at_risk_count": 0,
                "healthy_count": 0,
                "stockout_risk_count": 0,
                "at_risk_count": 0,
                "at_risk_value": 0.0,
                "inv_value": 0.0,
            }
        bucket["sku_count"] += 1

        state = row["state"]
        if state == "Stockout":
            bucket["stockout_count"] += 1
        elif state == "Low":
            bucket["low_count"] += 1
        elif state == "Healthy":
            bucket["healthy_count"] += 1
        else:
            bucket["other_at_risk_count"] += 1

        # Verified across all 16,000 rows: `position < rop` holds for exactly
        # the Stockout and Low rows, so the reorder-zone count is the sum of
        # those two segments rather than an independent measure.
        if row["position"] < row["rop"]:
            bucket["stockout_risk_count"] += 1
        if state != "Healthy":
            bucket["at_risk_count"] += 1
        bucket["at_risk_value"] += row["at_risk"]
        bucket["inv_value"] += row["inv_value"]

    for bucket in grouped.values():
        segments = (
            bucket["stockout_count"]
            + bucket["low_count"]
            + bucket["other_at_risk_count"]
            + bucket["healthy_count"]
        )
        if segments != bucket["sku_count"]:
            raise SystemExit(
                f"FAIL  {bucket['store_id']}: state segments sum to {segments}"
                f" but the store stocks {bucket['sku_count']} SKUs"
            )
        if bucket["stockout_count"] + bucket["low_count"] != bucket["stockout_risk_count"]:
            raise SystemExit(
                f"FAIL  {bucket['store_id']}: Stockout+Low disagrees with the"
                " position-below-ROP count"
            )

    return sorted(grouped.values(), key=lambda row: row["store_id"])


def kpis_for(items: list[dict[str, Any]]) -> dict[str, Any]:
    """The six A2 KPIs plus slow-mover, from pre-resolved flags only.

    `overstock_excess_value` and `expiry_value` are the money figures the A2
    cards show underneath their counts. Note `overstock_excess_value` counts
    only the position above Max, not the full position value — the workbook
    keeps two different senses of "overstock" side by side (A2 spec section 10
    note 3), and this is the narrower one.
    """
    count = len(items)
    return {
        "stockout_risk_skus": sum(1 for row in items if row["is_stockout_risk"]),
        "overstock_skus": sum(1 for row in items if row["is_overstock"]),
        "overstock_excess_value": sum(
            (row["position"] - row["max"]) * row["price"]
            for row in items
            if row["is_overstock"] and row["position"] > row["max"]
        ),
        "expiry_units": sum(row["expiry_units"] for row in items),
        "expiry_value": sum(row["expiry_units"] * row["price"] for row in items),
        "slow_mover_skus": sum(1 for row in items if row["is_slow_mover"]),
        "avg_dos": (sum(row["dos"] for row in items) / count) if count else 0.0,
        "inventory_value": sum(row["inv_value"] for row in items),
        "at_risk_value": sum(row["at_risk_value"] for row in items),
    }


def reconcile(
    items: list[dict[str, Any]],
    reference: list[dict[str, Any]],
    label_of: dict[str, str],
) -> list[str]:
    """Recompute each vertical's KPIs and diff against the A2 sheet."""
    by_label = {row["vertical_label"]: row for row in reference}
    failures: list[str] = []

    for vertical_id, label in sorted(label_of.items()):
        scoped = [row for row in items if row["vertical_id"] == vertical_id]
        mine = kpis_for(scoped)
        book = by_label[label]

        checks = (
            ("stockout_risk_skus", mine["stockout_risk_skus"], book["stockout_risk_skus"]),
            ("overstock_skus", mine["overstock_skus"], book["overstock_skus"]),
            ("expiry_units", mine["expiry_units"], book["expiry_units"]),
            ("inventory_value", mine["inventory_value"], book["inventory_value"]),
            ("at_risk_value", mine["at_risk_value"], book["at_risk_value"]),
            # avg_dos is stored rounded to one decimal on the sheet.
            ("avg_dos", round(mine["avg_dos"], 1), round(book["avg_dos"], 1)),
        )
        for name, computed, stored in checks:
            if isinstance(computed, float) or isinstance(stored, float):
                agrees = abs(float(computed) - float(stored)) <= 1e-6
            else:
                agrees = computed == stored
            if not agrees:
                failures.append(
                    f"{label} / {name}: computed {computed}, workbook {stored}"
                )

    return failures


def main() -> int:
    # A fixture built from the wrong workbook is committed to the repo
    # and read by every board in standalone mode, so it needs the same
    # check the seeders make before they touch the warehouse.
    workbook_guard.check(SOURCE)

    if not SOURCE.exists():
        print(f"FAIL  source not found: {SOURCE}")
        print("      run scripts/extract_workbook_schema.py first")
        return 1

    tables = read_source()
    required = (
        "engine",
        "engine_store",
        "sku_master",
        "stores",
        "verticals",
        "a2_inventory_risk",
        "constants",
        "what_if_per_agent",
        # The projection burns a shaped daily curve rather than a flat ADS, so
        # this board needs the same two inputs Demand Forecasting reads: the
        # monthly GMV profile behind the seasonal indices, and A1's typed
        # `Trend %`. Neither changes a single stock figure below; both change
        # how that stock is spent over the horizon.
        "time_series_24mo",
        "a1_demand_forecasting",
    )
    missing = [name for name in required if name not in tables]
    if missing:
        print(f"FAIL  source is missing tables: {', '.join(missing)}")
        return 1

    verticals = tables["verticals"]
    reference = tables["a2_inventory_risk"]
    label_of = resolve_vertical_labels(verticals, reference)

    sku_master = {row["sku_id"]: row for row in tables["sku_master"]}
    stores = {row["store_id"]: row for row in tables["stores"]}
    store_size = chain_store_size(tables["stores"])

    constants = constants_from_cells(
        tables["constants"], {"dow_sum": "B7", "month_index": "B6"}
    )
    check_profile(constants["dow_sum"])
    month_index = int(constants["month_index"])
    seasonality = seasonality_payload(tables["time_series_24mo"], month_index)
    # A1's typed `Trend %`, keyed the way this file already keys A2's totals.
    trend_by_label = {
        row["vertical_label"]: row["trend_pct"]
        for row in tables["a1_demand_forecasting"]
    }

    expressions = verify_engine_chain(tables["engine"], sku_master, store_size)
    verify_store_derivation(
        tables["engine_store"], tables["engine"], sku_master, stores, store_size
    )

    items = build_items(tables["engine"], sku_master, store_size)
    store_rows = build_store_rows(tables["engine_store"], stores)

    failures = reconcile(items, reference, label_of)
    if failures:
        print(f"FAIL  {len(failures)} KPI(s) disagree with the A2 sheet:")
        for line in failures:
            print(f"      {line}")
        return 1

    checked = len(label_of) * 6
    print(f"  ok  reconciled {checked} KPI values across {len(label_of)} verticals")

    entity_of = {label: vertical_id for vertical_id, label in label_of.items()}

    # Filter options carry their parent so the UI can reset a child selection
    # that the new parent makes invalid, without a second request.
    categories = {}
    for row in items:
        categories.setdefault(
            row["category_id"],
            {
                "value": row["category_id"],
                # id first: category_name is not unique across verticals
                # (e.g. DGT-C01 and OMN-C01 are both "Electronics"), so the
                # bare name alone cannot tell two dropdown entries apart.
                "label": f"{row['category_id']} · {row['category_name']}",
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
            "Workbook demonstration data, not a live ERP position. On-hand in "
            "the source workbook is pseudo-random in the SKU id, so treat "
            "stock levels as illustrative."
        ),
        "state_order": list(STATE_ORDER),
        # Model parameters the browser needs but must not retype. Keyed off the
        # `Constants` cell rather than its label, because a label is prose and
        # gets reworded; B6 and B7 are addresses and do not.
        "constants": {
            **constants,
            # Seven factors summing to `dow_sum`, checked above. A modelled
            # allocation of a measured week: the total is the workbook's, the
            # shape inside it is ours, and `derivation` says so.
            "dow_profile": list(DOW_PROFILE),
        },
        # The expressions the What-If engine runs, copied from formula.json
        # after `verify_engine_chain` proved they rebuild the rows below. The
        # browser evaluates these rather than importing formula.json directly,
        # so the rules and the data it was verified against cannot arrive out
        # of step with each other.
        "formulas": expressions,
        # The workbook's own +20% demand scenario, carried so the What-If
        # engine has something to be checked against. Every other figure in
        # this file sits at zero levers, which cannot test a lever at all.
        "what_if_reference": {
            "levers": {"demand": 20, "promo": 15},
            "note": next(
                (row["note"] for row in tables["what_if_per_agent"]), ""
            ),
            "by_legal_entity": [
                {
                    "legal_entity_id": entity_of[row["vertical_label"]],
                    "vertical_label": row["vertical_label"],
                    "forecast_delta": row["forecast_delta"],
                    "at_risk_delta": row["at_risk_delta"],
                    "order_delta": row["order_delta"],
                }
                for row in tables["what_if_per_agent"]
                if row["vertical_label"] in entity_of
            ],
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
            "states": list(STATE_ORDER),
        },
        "items": items,
        "stores": store_rows,
        # Twelve seasonal indices per vertical and the month the workbook says
        # it is (`Constants` B6) -- byte-for-byte what the Demand Forecasting
        # fixture ships, from the same function, so the projection here and the
        # outlook curve there cannot disagree about next month.
        "seasonality": seasonality,
        # The workbook's own per-vertical totals. Kept so a test can assert the
        # UI still agrees with the sheet after any refactor, and so the chain-net
        # headline has something to be checked against.
        "reference_by_vertical": [
            {
                "legal_entity_id": vertical_id,
                "vertical_label": label,
                **{
                    key: by_label[label][key]
                    for key in (
                        "stockout_risk_skus",
                        "overstock_skus",
                        "expiry_units",
                        "inventory_value",
                        "at_risk_value",
                        "avg_dos",
                    )
                },
                # Not an A2 figure: A1's typed annual trend, carried because
                # the projection compounds it over the horizon. Typed, not
                # measured -- `derivation` on the demand board says as much and
                # the note below repeats it.
                "trend_pct": trend_by_label.get(label, 0.0),
            }
            for vertical_id, label in sorted(label_of.items())
            for by_label in [{row["vertical_label"]: row for row in reference}]
        ],
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temp = TARGET.with_suffix(".json.tmp")
    # Compact, not indented. Pretty-printing costs ~200 KB of bundle for an
    # identical gzip size, and neither form gives a reviewable diff at 800
    # rows — this script, not the output, is the review surface.
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
