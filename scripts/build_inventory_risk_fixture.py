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
counts flags and sums columns. No threshold (`DoS > 15`, `growth < 1.0`,
`Position < 0.6 x ROP`) is allowed to exist in JavaScript, because a second
copy of a rule is a rule that will silently drift from the workbook.

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


def build_items(
    engine: list[dict[str, Any]],
    sku_master: dict[str, dict[str, Any]],
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
                # The three KPI predicates, resolved here so no threshold ever
                # reaches JavaScript. Sources: A2 spec sections 2 and 3.
                "is_stockout_risk": row["position"] < row["rop"],
                "is_overstock": dos > 15,
                "is_slow_mover": growth < 1.0 and dos > 10,
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

    items = build_items(tables["engine"], sku_master)
    store_rows = build_store_rows(tables["engine_store"], stores)

    failures = reconcile(items, reference, label_of)
    if failures:
        print(f"FAIL  {len(failures)} KPI(s) disagree with the A2 sheet:")
        for line in failures:
            print(f"      {line}")
        return 1

    checked = len(label_of) * 6
    print(f"  ok  reconciled {checked} KPI values across {len(label_of)} verticals")

    # Filter options carry their parent so the UI can reset a child selection
    # that the new parent makes invalid, without a second request.
    categories = {}
    for row in items:
        categories.setdefault(
            row["category_id"],
            {
                "value": row["category_id"],
                "label": row["category_name"],
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
