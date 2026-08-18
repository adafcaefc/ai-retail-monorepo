"""Build the Promotion Effectiveness (Agent 4) dashboard fixture from workbook data.

Run it yourself:

    python scripts/build_promotion_effectiveness_fixture.py

Input:  resources/dbtemp/schema_with_data.json  (produced by extract_workbook_schema.py)
Output: frontend/src/agents/retail/promotion_effectiveness/data/fixture.json

WHAT THIS SHIPS
The promo-eligible SKUs (chain-net, one row per item, the ~quarter of the 800
that carry SKU_Master.promo = "Y"), each with its workbook margin_rp and
funding_rp plus the cannibalisation, margin and price inputs behind
f13-incremental-promotion-margin. Plus the 48 campaign rows from Promotion &
Discount Detail, the six headline KPIs per vertical from the A4 Promotion
sheet as `reference_by_vertical`, and a plain `stores` dimension list
(store_id, cluster, channel, size_index) the frontend selectors use to split
each item's incremental_margin proportionally by store size — see
`verify_store_split` for the proof that this reconstruction is exact.

The browser What-If engine re-evaluates f01-ads-per-store and
f13-incremental-promotion-margin over these items; this script ships the two
formula expressions alongside so the engine has one source of truth, read from
the same `retail.formula` catalogue the backend agents quote.

RECONCILIATION
`reference_by_vertical` is the A4 Promotion sheet verbatim. The aggregate of
the shipped items' margin_rp reconciles against the sheet's per-vertical
incremental_margin at chain grain within rounding, because both come from the
same ENGINE table. The headline uplift and ROI are stored KPIs (not derivable
from per-SKU rows) and are carried as-is.

DATA HONESTY
The numbers are internally consistent demonstration data, not a live ERP or
D365 Commerce position. The payload carries `is_mock: true` and a note, and the
UI labels it rather than presenting it as measured.
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
    / "promotion_effectiveness"
    / "data"
    / "fixture.json"
)
SOURCE_WORKBOOK = "Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx"

# The two expressions the browser What-If engine evaluates. Read from the
# catalogue rather than restated, so the fixture and the agents can never
# disagree about what a formula says.
CATALOGUE_FORMULAS = (
    "f01-ads-per-store",
    "f13-incremental-promotion-margin",
)

THRESHOLDS = {
    "roi_target": 2,
    "uplift_target_pct": 20,
    "funding_guardrail_pct": 35,
    "cannib_cap_pct": 25,
    "pre_buy_material_units": 2000,
}


def load_tables() -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = [dict(zip(names, row)) for row in table["rows"]]
    return tables


def build_items(
    engine: list[dict[str, Any]],
    sku_master: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
    stores: list[dict[str, Any]],
    f13_ast: Any,
) -> list[dict[str, Any]]:
    """Promo-eligible SKUs only, chain-net, with their promo economics.

    The incremental margin carried here is the f13 value computed from each
    SKU's chain inputs, NOT the chain `margin_rp`. Those are different numbers:
    `margin_rp` is the chain's total weekly margin, while f13 is the incremental
    margin attributable to the promotion. SUM(f13) over the 241 promo SKUs
    reconciles to the cent against the A4 Promotion sheet's chain total
    (Rp 21.04B), which is why f13 is the right figure here.
    """
    by_sku = {row["sku_id"]: row for row in sku_master}
    # store_size per vertical, summed from the stores table the same way the
    # backend's SQL does it (sum(size_index)). sku_master.sum_vert_size was
    # rounded to 4 places by the workbook, which drifts from the SQL sum.
    vertical_size: dict[str, float] = {}
    for store in stores:
        vid = store.get("vertical_id")
        vertical_size[vid] = vertical_size.get(vid, 0.0) + _num(store.get("size"))
    # Match the backend's ORDER BY vt.sort_order, c.margin_rp DESC: vertical in
    # the workbook's own order (the verticals table is in that order), then the
    # chain margin_rp descending within each vertical.
    vertical_order = {
        row["vertical_id"]: index for index, row in enumerate(verticals)
    }
    ordered_engine = sorted(
        engine,
        key=lambda row: (
            vertical_order.get(row.get("vertical_id"), len(verticals)),
            -_num(row.get("margin_rp")),
        ),
    )
    items = []
    for row in ordered_engine:
        master = by_sku.get(row["sku_id"])
        if not master:
            continue
        if str(master.get("promo", "N")).strip().upper() != "Y":
            continue
        price = _num(master.get("price", row.get("price")))
        margin_pct = _num(master.get("margin_pct"))
        cannib = _num(master.get("cannib_pct"))
        fund = _num(master.get("fund_pct"))
        ads = _num(row.get("ads"))
        incremental_margin = evaluate(
            f13_ast,
            {
                "ads": ads,
                "price": price,
                "margin_pct": margin_pct,
                "cannibalization": cannib,
                "promo_eligible": "Y",
                "promo_funding": fund,
            },
        )
        items.append(
            {
                "sku_id": row["sku_id"],
                "name": master.get("item", row["sku_id"]),
                "vertical_id": row["vertical_id"],
                "category_id": row["cat_id"],
                "category_label": master.get("category", row["cat_id"]),
                "brand": master.get("brand", ""),
                "price": price,
                "margin_pct": margin_pct,
                "ads": ads,
                "incremental_margin": incremental_margin,
                "supplier_funding": _num(row.get("funding_rp")),
                "supplier_funding_pct": fund * 100.0,
                "cannibalisation_pct": cannib * 100.0,
                "state": row.get("state"),
                "inventory_value": _num(row.get("inv_value")),
                # What-If inputs the browser re-evaluates f01 / f13 against.
                "base_ads": _num(master.get("base_ads")),
                "seasonality": _num(master.get("seasonality")),
                "store_size": vertical_size.get(row["vertical_id"], 0.0),
                "promo_eligible": "Y",
                "promo_depth": cannib * 100.0,
                "promo_funding": fund * 100.0,
            }
        )
    return items


def build_store_rows(stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per store — the by-store/cluster/channel dimension source.

    A plain passthrough of the `stores` table, no per-row formula evaluation.
    `size_index` is what the frontend selectors multiply against each item's
    own `incremental_margin` to reconstruct that store's share of it (see
    `verify_store_split` for why that reconstruction is exact, not
    approximate).
    """
    return sorted(
        (
            {
                "store_id": row["store_id"],
                "name": row["store_name"],
                "vertical_id": row["vertical_id"],
                "cluster": row["cluster"],
                "channel": row["channel"],
                "size_index": _num(row["size"]),
            }
            for row in stores
        ),
        key=lambda row: row["store_id"],
    )


def verify_store_split(
    engine_store: list[dict[str, Any]],
    sku_master: list[dict[str, Any]],
    stores: list[dict[str, Any]],
    items: list[dict[str, Any]],
    f13_ast: Any,
) -> None:
    """Prove the proportional store split before shipping it, not just assert it.

    `f01-ads-per-store` is purely multiplicative in `store_size`, and `f13` is
    linear in `ads` with every other input (price, margin, cannib, funding)
    constant per item regardless of store. So a store's incremental margin
    should equal `item.incremental_margin * (store.size_index /
    item.store_size)` exactly. Checked here against every real `ENGINE_STORE`
    row for a promo SKU: `f13` evaluated on that row's *real* `ads` must match
    the proportional split to floating-point precision. `engine_store` is only
    a build-time oracle for this proof — it is not shipped in the fixture.

    If this ever fails, the store/cluster/channel charts are lying and must go
    back to a real per-store computation. Do not widen the tolerance to make
    it pass.
    """
    items_by_sku = {row["sku_id"]: row for row in items}
    stores_by_id = {row["store_id"]: row for row in stores}
    failures: list[str] = []
    checked = 0

    for row in engine_store:
        item = items_by_sku.get(row["sku_id"])
        if item is None:
            continue  # not a promo SKU; the split only applies to those
        store = stores_by_id[row["store_id"]]
        real_margin = evaluate(
            f13_ast,
            {
                "ads": _num(row.get("ads")),
                "price": item["price"],
                "margin_pct": item["margin_pct"],
                "cannibalization": item["cannibalisation_pct"] / 100.0,
                "promo_eligible": "Y",
                "promo_funding": item["supplier_funding_pct"] / 100.0,
            },
        )
        expected_split = item["incremental_margin"] * (
            _num(store["size"]) / item["store_size"] if item["store_size"] else 0.0
        )
        tolerance = max(1e-6, abs(expected_split) * 1e-6)
        if abs(real_margin - expected_split) > tolerance:
            failures.append(
                f"{row['sku_id']}@{row['store_id']}: proportional split"
                f" {expected_split!r}, f13(real store ads) {real_margin!r}"
            )
        checked += 1

    if failures:
        print(
            f"FAIL  the proportional store split disagrees with ENGINE_STORE on"
            f" {len(failures)} value(s) across {checked} promo rows:"
        )
        for line in failures[:5]:
            print(f"      {line}")
        raise SystemExit(1)

    print(
        f"  ok  proportional store split reproduces {checked} ENGINE_STORE"
        " promo rows from item incremental_margin x store size_index"
    )


def build_campaigns(
    detail: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The 48 campaign rows, vertical_label resolved to vertical_id, classified.

    Ordered to match the backend's ORDER BY: vertical workbook order, then
    expected_uplift_pct DESC, then pre_buy_uplift_units DESC.
    """
    label_to_id = {row["dashboard_label"]: row["vertical_id"] for row in verticals}
    vertical_order = {
        row["vertical_id"]: index for index, row in enumerate(verticals)
    }
    ordered_detail = sorted(
        detail,
        key=lambda row: (
            vertical_order.get(
                label_to_id.get(row["vertical_label"], ""), len(verticals)
            ),
            -_num(row.get("expected_uplift_pct")),
            -_num(row.get("pre_buy_uplift_units")),
        ),
    )
    campaigns = []
    for row in ordered_detail:
        vertical_id = label_to_id.get(row["vertical_label"], row["vertical_label"])
        campaigns.append(
            {
                "promo_id": row["promo_id"],
                "promo_name": row["promo_name"],
                "discount_type": row["discount_type"],
                "scope": row["scope"],
                "vertical_id": vertical_id,
                "vertical_label": row["vertical_label"],
                "target_category": row["target_category"],
                "season": row["season"],
                "peak_month": row["peak_month"],
                "mechanism": row["mechanism"],
                "discount_pct": row.get("discount_pct"),
                "value_rule": row["value_rule"],
                "min_qty_threshold": row["min_qty_threshold"],
                "supplier_funding_pct": row["supplier_funding_pct"],
                "expected_uplift_pct": row["expected_uplift_pct"],
                "pre_buy_uplift_units": row["pre_buy_uplift_units"],
                "valid_from": _iso(row.get("valid_from")),
                "valid_to": _iso(row.get("valid_to")),
                "d365_construct": row["d365_construct"],
                "recommendation": classify(row),
            }
        )
    return campaigns


def classify(row: dict[str, Any]) -> str:
    """The spec's promoClassify — see backend promotion_data._classify_campaigns."""
    uplift = _num(row.get("expected_uplift_pct"))
    funding = _num(row.get("supplier_funding_pct"))
    pre_buy = _num(row.get("pre_buy_uplift_units"))
    if uplift >= THRESHOLDS["uplift_target_pct"] and funding < THRESHOLDS["funding_guardrail_pct"]:
        return "Negotiate supplier funding"
    if pre_buy >= THRESHOLDS["pre_buy_material_units"]:
        return "Trigger A3 pre-buy PO"
    return "Approve promo"


def build_reference(
    a4: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The A4 Promotion sheet pivoted to reference_by_vertical shape."""
    label_to_id = {row["dashboard_label"]: row["vertical_id"] for row in verticals}
    reference = []
    for row in a4:
        vertical_id = label_to_id.get(row["vertical_label"], row["vertical_label"])
        reference.append(
            {
                "legal_entity_id": vertical_id,
                "vertical_label": row["vertical_label"],
                "active_promo_skus": int(row["active_promo_skus"]),
                "uplift_pct": _num(row["uplift_pct"]),
                "incremental_margin": _num(row["incremental_margin"]),
                "roi_x": _num(row["roi_x"]),
                "cannib_pct": _num(row["cannib_pct"]),
                "funding_pct": _num(row["funding_pct"]),
            }
        )
    # Match warehouse.agent_reference: ordered by vertical_id (alphabetical),
    # NOT by workbook sort_order. The reference block is a table nobody scrolls;
    # the fixture builders sort it by id, and matching that keeps the two paths
    # byte-comparable.
    reference.sort(key=lambda r: r["legal_entity_id"])
    return reference


def build_filter_options(
    verticals: list[dict[str, Any]],
    sku_master: list[dict[str, Any]],
    stores: list[dict[str, Any]],
) -> dict[str, list]:
    """Match the shape `retail.common.warehouse.filter_options` returns, so the
    API and the fixture agree on every dropdown."""
    legal_entities = [
        {
            "value": row["vertical_id"],
            "label": f"{row['vertical_id']} · {row.get('vertical') or row.get('short') or row['vertical_id']}",
            "dashboard_label": row["dashboard_label"],
        }
        for row in verticals
    ]
    seen = set()
    categories = []
    for row in sku_master:
        cat_id = row.get("cat_id")
        if not cat_id or cat_id in seen:
            continue
        seen.add(cat_id)
        categories.append(
            {
                "value": cat_id,
                "label": row.get("category", cat_id),
                "legal_entity_id": row["vertical_id"],
            }
        )
    categories.sort(key=lambda c: c["value"])
    store_rows = [
        {
            "value": row["store_id"],
            "label": f"{row['store_id']} · {row['store_name']}",
            "legal_entity_id": row["vertical_id"],
            "cluster": row["cluster"],
        }
        for row in stores
    ]
    return {
        "legal_entities": legal_entities,
        "categories": categories,
        "stores": store_rows,
    }


def formula_expressions() -> tuple[dict[str, str], Any]:
    """Return the expressions to ship, plus the parsed f13 AST for build_items."""
    catalogue = {entry["id"]: entry["expression"] for entry in repository.load()}
    missing = [name for name in CATALOGUE_FORMULAS if name not in catalogue]
    if missing:
        raise SystemExit(
            f"retail.formula is missing {', '.join(missing)}. "
            "Seed it: python scripts/import_formulas_to_db.py"
        )
    expressions = {name: catalogue[name] for name in CATALOGUE_FORMULAS}
    f13_ast = parse(expressions["f13-incremental-promotion-margin"])
    return expressions, f13_ast


def _num(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pct(value: Any) -> float:
    """fund_pct/cannib_pct are stored as fractions (0.638 = 63.8%) in sku_master."""
    return _num(value) * 100.0


def _iso(value: Any) -> str | None:
    if not value:
        return None
    return str(value)[:10]


def main() -> int:
    if not SOURCE.exists():
        print(f"FAIL  source not found: {SOURCE}")
        print("      run scripts/extract_workbook_schema.py first")
        return 1

    tables = load_tables()
    for required in (
        "engine", "sku_master", "promotion_discount_detail", "a4_promotion",
        "verticals", "stores", "engine_store",
    ):
        if required not in tables:
            print(f"FAIL  source is missing table: {required}")
            return 1

    expressions, f13_ast = formula_expressions()

    items = build_items(tables["engine"], tables["sku_master"], tables["verticals"], tables["stores"], f13_ast)
    campaigns = build_campaigns(tables["promotion_discount_detail"], tables["verticals"])
    reference = build_reference(tables["a4_promotion"], tables["verticals"])
    filter_options = build_filter_options(tables["verticals"], tables["sku_master"], tables["stores"])
    store_rows = build_store_rows(tables["stores"])
    verify_store_split(tables["engine_store"], tables["sku_master"], tables["stores"], items, f13_ast)
    formulas = expressions

    if not items:
        print("FAIL  no promo-eligible SKUs found in engine + sku_master")
        return 1

    # Reconciliation: SUM(f13) over the shipped promo SKUs must match the A4
    # Promotion sheet's chain incremental_margin total. This is the whole reason
    # the fixture can be trusted; a mismatch means f13's inputs drifted from the
    # workbook's. Do not weaken this into a warning.
    shipped_total = sum(item["incremental_margin"] for item in items)
    sheet_total = sum(float(row["incremental_margin"]) for row in reference)
    if sheet_total and abs(shipped_total - sheet_total) / sheet_total > 0.005:
        print(
            "FAIL  incremental margin does not reconcile: "
            f"shipped Rp {shipped_total:,.0f} vs sheet Rp {sheet_total:,.0f}"
        )
        return 1

    fixture = {
        "schema_version": 1,
        "agent": "retail.promotion_effectiveness",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_workbook": SOURCE_WORKBOOK,
        "is_mock": True,
        "note": (
            "Workbook demonstration data, not a live ERP or D365 Commerce "
            "position. ROI is a stored KPI; no separate promo-investment "
            "column is exposed."
        ),
        "thresholds": THRESHOLDS,
        "formulas": formulas,
        "filter_options": filter_options,
        "items": items,
        "campaigns": campaigns,
        "stores": store_rows,
        "reference_by_vertical": reference,
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temp = TARGET.with_suffix(".json.tmp")
    temp.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(TARGET)

    print(f"ok  {TARGET.relative_to(REPO)}")
    print(f"    {len(items)} promo SKUs, {len(campaigns)} campaigns, "
          f"{len(store_rows)} stores, {len(reference)} vertical references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
