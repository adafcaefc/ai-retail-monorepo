"""Build the Assortment Optimization (Agent 6) dashboard fixture from workbook data.

Run it yourself:

    python scripts/build_assortment_optimization_fixture.py

Input:  resources/dbtemp/schema_with_data.json  (produced by extract_workbook_schema.py)
Output: frontend/src/agents/retail/assortment_optimization/data/fixture.json

WHY THIS DOES NOT TRUST THE "A6 Assortment" SHEET'S B:F COLUMNS
Same root cause as Agent 5 (see build_pricing_markdown_fixture.py's module
docstring): AUDIT Root Cause RC-2 in `Dataset_AI_Retail.xlsx` names
"A6!B6:F13" -- delist_candidates, grow_candidates, avg_gmroi, tail_share_pct,
capital_freed -- as stale hardcoded values pasted from an old snapshot, not
live formulas. Column G (contribution_day) is OUTSIDE that flagged range,
and checks out here: summing ENGINE_STORE!contribution_day per SKU and
totalling chain-wide reproduces the A6 sheet's own G-column total to the
rupiah (Rp 63,999,028,323 both ways) -- so contribution_day is trusted as
shipped, while delist/grow classification, GMROI, tail share and capital
freed are computed fresh from ENGINE / ENGINE_STORE / SKU_Master.

CLASSIFICATION (not given as a numeric rule by the spec; resolved here)
A6 spec section 2 defines Delist/Grow qualitatively ("low GMROI or tail SKU
or state in {Slow-mover, Overstock, Expiry}" / "Healthy with strong
contribution, GMROI, growth"). This script operationalizes "low"/"strong"
as chain-wide quartiles, computed once over all 800 SKUs:

  delist  = state in {Slow-mover, Overstock, Expiry}
            OR gmroi <= P25(gmroi, chain-wide)
            OR contribution_per_day <= P25(contribution_per_day, chain-wide)  [[tail]]
  grow    = state == Healthy AND gmroi >= P75(gmroi, WITHIN HEALTHY SKUs)
            AND contribution_per_day >= P75(contribution_per_day, WITHIN HEALTHY SKUs)
            AND growth >= 1.0
  hold    = neither

Grow's P75 cutoffs are computed within the Healthy subset, not chain-wide:
probed empirically, high GMROI in this dataset concentrates in
Stockout/Low-state SKUs (fast movers running short), not Healthy ones, so a
chain-wide P75 GMROI intersected with state==Healthy is empty. See
classify() for the full reasoning.

The four Suggested Best Action tabs (spec section 7) are resolved from that:
Grow Winners is the grow population; the delist population splits into
Vendor/Brand Review (vendor carries >=5 delist SKUs chain-wide), Rebalance
Space (a category is >=50% delist by SKU count), else Delist Tail -- checked
in that order, so every delist SKU lands in exactly one tab.

WHY NOT backend/src/formulas/repository.py
Same reasoning as Agent 5's script: reads resources/dbtemp/formula.json
directly, no database connection.

DATA HONESTY
Internally consistent demonstration data, not a live ERP position. The
payload carries `is_mock: true` and a note; the UI labels it rather than
presenting it as measured.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.formulas.expression import evaluate, parse  # noqa: E402

SOURCE = REPO / "resources" / "dbtemp" / "schema_with_data.json"
FORMULA_CATALOGUE = REPO / "resources" / "dbtemp" / "formula.json"
TARGET = (
    REPO
    / "frontend"
    / "src"
    / "agents"
    / "retail"
    / "assortment_optimization"
    / "data"
    / "fixture.json"
)
SOURCE_WORKBOOK = "Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx"

DELIST_STATES = ("Slow-mover", "Overstock", "Expiry")
STATE_ORDER = ("Stockout", "Low", "Expiry", "Overstock", "Slow-mover", "Healthy")
VENDOR_REVIEW_THRESHOLD = 5
REBALANCE_CATEGORY_SHARE = 0.5

# Formulas the browser What-If engine re-evaluates (unaffected by the
# delist/grow classification, which is percentile-based and recomputed
# entirely in selectors.js from the driven items).
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
)


def load_tables() -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = [dict(zip(names, row)) for row in table["rows"]]
    return tables


def load_formulas() -> dict[str, str]:
    payload = json.loads(FORMULA_CATALOGUE.read_text(encoding="utf-8"))
    catalogue = {entry["id"]: entry["expression"] for entry in payload["formulas"]}
    missing = [name for name in CATALOGUE_FORMULAS if name not in catalogue]
    if missing:
        raise SystemExit(f"formula.json is missing {', '.join(missing)}")
    return {name: catalogue[name] for name in CATALOGUE_FORMULAS}


def _num(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolated percentile over an already-sorted list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct
    lower = int(k)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = k - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


def contribution_by_sku(engine_store: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in engine_store:
        totals[row["sku_id"]] = totals.get(row["sku_id"], 0.0) + _num(row["contribution_day"])
    return totals


def designated_lead_times(trade_agreements: list[dict[str, Any]]) -> dict[str, float]:
    """Vendor lead time per item, from the DESIGNATED trade agreement.

    NOT `sku_master.lead_d`. The workbook's own ROP formula (ENGINE!G, read
    directly from the file) is:

        ROUND(ADS * (MAX(1, SUMIFS('Trade Agreement'!H, item, designated="Y")
                            + Constants!B20)
                     + MAX(0, SKU_Master.safety_d + Constants!B21)))

    -- the lead term is the trade agreement's, which is audit fix T-05/T-06
    ("ROP pakai lead statis di SKU master, bukan lead vendor") already ported
    into this workbook. Feeding f05 `sku_master.lead_d` instead reproduces
    neither ROP nor Max, which shifts the inventory state and therefore the
    delist verdict. Verified: this source reproduces all 800 stored ROP and
    Max values exactly.

    SUMIFS, not a lookup, because that is what the workbook does -- an item
    with two designated rows would sum them there, so it sums them here.
    """
    totals: dict[str, float] = {}
    for row in trade_agreements:
        if str(row.get("designated", "")).strip().upper() != "Y":
            continue
        totals[row["item"]] = totals.get(row["item"], 0.0) + _num(row.get("lead_time_d"))
    return totals


def verify_reorder_inputs(
    engine: list[dict[str, Any]],
    sku_master: dict[str, dict[str, Any]],
    lead_times: dict[str, float],
    asts: dict[str, Any],
) -> list[str]:
    """Re-derive every stored ROP and Max from f05/f06 and insist they match.

    This is the check whose absence let a wrong lead-time source through
    once already. If `lead_days` is sourced from the wrong column, ROP moves,
    the inventory state moves with it, and the delist verdict changes -- but
    every displayed figure still looks plausible, so nothing else catches it.
    """
    failures: list[str] = []
    for row in engine:
        master = sku_master.get(row["sku_id"])
        if not master:
            continue
        reorder = {
            "ads": _num(row["ads"]),
            "lead_time_days": lead_times.get(row["sku_id"], 0.0),
            "lead_time_adjust": 0,
            "safety_days": _num(master.get("safety_d")),
            "safety_adjust": 0,
        }
        rop = evaluate(asts["f05-rop"], reorder)
        max_inventory = evaluate(asts["f06-maximum-inventory"], reorder)
        if abs(rop - _num(row["rop"])) > 1:
            failures.append(f"{row['sku_id']}: f05 gives ROP {rop:,.0f}, ENGINE stores {_num(row['rop']):,.0f}")
        if abs(max_inventory - _num(row["max"])) > 1:
            failures.append(
                f"{row['sku_id']}: f06 gives Max {max_inventory:,.0f}, ENGINE stores {_num(row['max']):,.0f}"
            )
        if len(failures) >= 5:
            failures.append("... (further rows not listed)")
            break
    return failures


def build_items(
    engine: list[dict[str, Any]],
    sku_master: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
    contribution: dict[str, float],
    lead_times: dict[str, float],
    asts: dict[str, Any],
) -> list[dict[str, Any]]:
    """One row per SKU, with the whole productivity chain DERIVED here.

    WHY DERIVE RATHER THAN READ. Every other figure on the retail boards is
    read from the workbook, never re-derived -- that is the house rule. This
    board is the exception, and for a concrete reason: its delist/grow
    verdict is a comparison against percentile cutoffs, and the browser's
    What-If engine must reproduce that verdict exactly at baseline or the
    board contradicts its own data the moment a reader touches a slider.

    ENGINE's stored `ads` differs from f01 re-evaluated over the same inputs
    by about 1e-5 relative (workbook rounding). That is invisible in any
    displayed figure -- and decisive for the one SKU sitting exactly on the
    P75 cutoff, which flipped grow/hold between the two sides. Deriving both
    sides from f01 through the SAME evaluator removes the whole class of
    disagreement rather than tuning a tolerance around it.

    `contribution` (the per-SKU store-grain sum) is still passed in, and the
    reconciliation in main() checks the derived chain figure against it, so
    the derivation stays anchored to the workbook rather than floating free.
    """
    by_sku = {row["sku_id"]: row for row in sku_master}
    vertical_order = {row["vertical_id"]: i for i, row in enumerate(verticals)}
    ordered = sorted(
        engine,
        key=lambda row: (
            vertical_order.get(row.get("vertical_id"), len(verticals)),
            -contribution.get(row["sku_id"], 0.0),
        ),
    )

    items = []
    for row in ordered:
        master = by_sku.get(row["sku_id"])
        if not master:
            continue

        price = _num(row["price"])
        margin_pct = _num(master.get("margin_pct"))

        # f01 at baseline levers -- the same expression, through the same
        # evaluator, that `engine.js` runs in the browser.
        ads = evaluate(
            asts["f01-ads-per-store"],
            {
                "base_ads": _num(master.get("base_ads")),
                "seasonality": _num(master.get("seasonality")),
                "store_size": _num(master.get("sum_vert_size")),
                "demand_lever": 0,
                "promo_eligible": master.get("promo", "N"),
                "promo_lever": 0,
                "promo_depth": _num(master.get("cannib_pct")),
            },
        )
        inv_value = evaluate(
            asts["f21-inventory-value"],
            {"position": _num(row["position"]), "price": price},
        )
        # The productivity chain, in the engine's own order of operations.
        contribution_per_day = ads * price * margin_pct
        weekly_gmv = ads * 7 * price
        margin_rp = weekly_gmv * margin_pct
        gmroi = (margin_rp / inv_value) if inv_value else 0.0

        items.append(
            {
                "sku_id": row["sku_id"],
                "name": master.get("item", row["sku_id"]),
                "vertical_id": row["vertical_id"],
                "category_id": row["cat_id"],
                "category_label": master.get("category", row["cat_id"]),
                "brand": master.get("brand", ""),
                "vendor": master.get("vendor", ""),
                "state": row["state"],
                "severity_rank": STATE_ORDER.index(row["state"]) if row["state"] in STATE_ORDER else len(STATE_ORDER),
                "position": _num(row["position"]),
                "price": _num(row["price"]),
                "inv_value": inv_value,
                "weekly_gmv": weekly_gmv,
                "margin_rp": margin_rp,
                "funding_rp": _num(row["funding_rp"]),
                # None of the derived chain is rounded, deliberately. These
                # are comparison inputs -- the delist/grow cutoffs are
                # percentiles of them -- not display values (components
                # format at render time). Rounding here is what made the
                # browser engine disagree with this script about the verdict
                # of the one SKU sitting on a cutoff; `engine.test.js`
                # asserts the two now agree exactly.
                "gmroi": gmroi,
                "contribution_per_day": contribution_per_day,
                "growth": _num(master.get("growth")),
                "dos": _num(row["dos"]),
                "ads": ads,
                "rop": _num(row["rop"]),
                "max": _num(row["max"]),
                "open_po": _num(row.get("open_po")),
                "on_hand": _num(row["position"]) - _num(row.get("open_po")),
                "shelf_life_days": _num(master.get("expiry_d")),
                "perishable": master.get("perishable", "N"),
                # What-If cascade inputs for the browser engine.
                "base_ads": _num(master.get("base_ads")),
                "seasonality": _num(master.get("seasonality")),
                "store_size": _num(master.get("sum_vert_size")),
                "promo_eligible": master.get("promo", "N"),
                "promo_depth": _num(master.get("cannib_pct")),
                # The designated trade agreement's lead time -- see
                # designated_lead_times() for why this is not sku_master.lead_d.
                "lead_days": lead_times.get(row["sku_id"], 0.0),
                "safety_days": _num(master.get("safety_d")),
                "margin_pct": _num(master.get("margin_pct")),
            }
        )
    return items


def classify(items: list[dict[str, Any]]) -> dict[str, float]:
    """Adds `classification` ("delist"/"grow"/"hold") and `is_tail` to every
    item in place.

    Delist uses chain-wide P25 (any state can be a delist candidate on low
    GMROI or tail contribution alone, per spec section 2's plain OR). Grow
    uses P75 WITHIN THE HEALTHY SUBSET, not chain-wide: probed empirically,
    high GMROI is concentrated in Stockout/Low-state SKUs in this dataset
    (fast movers running short), not Healthy ones, so a chain-wide P75 GMROI
    cutoff intersected with state==Healthy is empty. Healthy-relative
    thresholds are also the more faithful reading of the spec's own
    wording -- Grow candidates compete against their Healthy peers, not
    against SKUs already in a completely different state.
    """
    gmroi_sorted = sorted(i["gmroi"] for i in items)
    contribution_sorted = sorted(i["contribution_per_day"] for i in items)
    p25_gmroi = percentile(gmroi_sorted, 0.25)
    p25_contribution = percentile(contribution_sorted, 0.25)

    healthy_gmroi_sorted = sorted(i["gmroi"] for i in items if i["state"] == "Healthy")
    healthy_contribution_sorted = sorted(i["contribution_per_day"] for i in items if i["state"] == "Healthy")
    p75_gmroi_healthy = percentile(healthy_gmroi_sorted, 0.75)
    p75_contribution_healthy = percentile(healthy_contribution_sorted, 0.75)

    for item in items:
        is_tail = item["contribution_per_day"] <= p25_contribution
        is_delist = item["state"] in DELIST_STATES or item["gmroi"] <= p25_gmroi or is_tail
        is_grow = (
            item["state"] == "Healthy"
            and item["contribution_per_day"] >= p75_contribution_healthy
            and item["gmroi"] >= p75_gmroi_healthy
            and item["growth"] >= 1.0
        )
        item["is_tail"] = is_tail
        item["classification"] = "grow" if (is_grow and not is_delist) else ("delist" if is_delist else "hold")

    return {
        "p25_gmroi_chain": p25_gmroi,
        "p25_contribution_chain": p25_contribution,
        "p75_gmroi_healthy": p75_gmroi_healthy,
        "p75_contribution_healthy": p75_contribution_healthy,
    }


def assign_best_action_tabs(items: list[dict[str, Any]]) -> None:
    """Adds `best_action_tab` in place. Grow Winners is the grow population;
    the delist population splits into Vendor/Brand Review, Rebalance Space,
    or plain Delist Tail -- see the module docstring for the thresholds.
    """
    delist_items = [i for i in items if i["classification"] == "delist"]

    vendor_delist_counts: dict[str, int] = {}
    for i in delist_items:
        vendor_delist_counts[i["vendor"]] = vendor_delist_counts.get(i["vendor"], 0) + 1

    category_totals: dict[str, int] = {}
    category_delist: dict[str, int] = {}
    for i in items:
        category_totals[i["category_id"]] = category_totals.get(i["category_id"], 0) + 1
    for i in delist_items:
        category_delist[i["category_id"]] = category_delist.get(i["category_id"], 0) + 1

    for item in items:
        if item["classification"] == "grow":
            item["best_action_tab"] = "grow_winners"
            item["recommendation"] = "Grow range / add space / expand stores"
        elif item["classification"] == "delist":
            category_share = category_delist.get(item["category_id"], 0) / max(1, category_totals.get(item["category_id"], 1))
            if vendor_delist_counts.get(item["vendor"], 0) >= VENDOR_REVIEW_THRESHOLD:
                item["best_action_tab"] = "vendor_brand_review"
                item["recommendation"] = "Vendor or brand review"
            elif category_share >= REBALANCE_CATEGORY_SHARE:
                item["best_action_tab"] = "rebalance_space"
                item["recommendation"] = "Rationalize tail and rebalance category"
            else:
                item["best_action_tab"] = "delist_tail"
                item["recommendation"] = "Delist / reduce facing / stop reorder"
        else:
            item["best_action_tab"] = None
            item["recommendation"] = "Hold assortment"


def build_store_rows(
    engine_store: list[dict[str, Any]],
    stores: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-store aggregates for the dimension charts. GROSS figures, gross
    the same way build_pricing_markdown_fixture.py's are (A6 spec section 6,
    section 11: "store-gross and chain-level views may differ").
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
                "contribution_per_day": 0.0,
                "inv_value": 0.0,
            }
        bucket["sku_count"] += 1
        bucket["contribution_per_day"] += _num(row.get("contribution_day"))
        bucket["inv_value"] += _num(row.get("inv_value"))

    return sorted(grouped.values(), key=lambda row: row["store_id"])


def build_state_value(engine_store: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inventory value by state, store-grain, full population -- A6 spec
    section 6, #ch-dim-state ("A6 Charts section 4")."""
    totals: dict[str, float] = {}
    for row in engine_store:
        totals[row["state"]] = totals.get(row["state"], 0.0) + _num(row["inv_value"])
    return [{"state": state, "value": round(value, 2)} for state, value in totals.items()]


def build_reference(
    a6: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Vertical labels only, plus the ONE column (contribution_day) that is
    not flagged stale by RC-2 -- kept as a reference/sanity figure, not
    relied on for correctness (the live per-item sum is what selectors.js
    actually aggregates).
    """
    label_to_id = {row["dashboard_label"]: row["vertical_id"] for row in verticals}
    reference = []
    for row in a6:
        vertical_id = label_to_id.get(row["vertical_label"], row["vertical_label"])
        reference.append(
            {
                "legal_entity_id": vertical_id,
                "vertical_label": row["vertical_label"],
                "contribution_per_day": _num(row["contribution_day"]),
            }
        )
    reference.sort(key=lambda r: r["legal_entity_id"])
    return reference


def build_filter_options(
    verticals: list[dict[str, Any]],
    sku_master: list[dict[str, Any]],
    stores: list[dict[str, Any]],
) -> dict[str, list]:
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
    return {"legal_entities": legal_entities, "categories": categories, "stores": store_rows}


def main() -> int:
    if not SOURCE.exists():
        print(f"FAIL  source not found: {SOURCE}")
        return 1

    tables = load_tables()
    for required in (
        "engine",
        "engine_store",
        "sku_master",
        "stores",
        "verticals",
        "trade_agreements",
        "a6_assortment",
    ):
        if required not in tables:
            print(f"FAIL  source is missing table: {required}")
            return 1

    formulas = load_formulas()
    asts = {name: parse(expr) for name, expr in formulas.items()}
    stores_by_id = {row["store_id"]: row for row in tables["stores"]}

    contribution = contribution_by_sku(tables["engine_store"])
    lead_times = designated_lead_times(tables["trade_agreements"])

    reorder_failures = verify_reorder_inputs(
        tables["engine"], {r["sku_id"]: r for r in tables["sku_master"]}, lead_times, asts
    )
    if reorder_failures:
        print("FAIL  f05/f06 do not reproduce the stored ROP/Max:")
        for line in reorder_failures:
            print(f"      {line}")
        return 1

    items = build_items(
        tables["engine"], tables["sku_master"], tables["verticals"], contribution, lead_times, asts
    )
    thresholds = classify(items)
    assign_best_action_tabs(items)

    stores_rollup = build_store_rows(tables["engine_store"], stores_by_id)
    by_state_value = build_state_value(tables["engine_store"])
    reference = build_reference(tables["a6_assortment"], tables["verticals"])
    filter_options = build_filter_options(tables["verticals"], tables["sku_master"], tables["stores"])

    delist = [i for i in items if i["classification"] == "delist"]
    grow = [i for i in items if i["classification"] == "grow"]
    if not delist or not grow:
        print(f"FAIL  degenerate classification: {len(delist)} delist, {len(grow)} grow")
        return 1

    # Two anchors, both against figures this script did not derive.
    #
    # 1. The derived chain contribution vs the ENGINE_STORE per-SKU sum: this
    #    is what keeps `build_items`' derivation tied to the workbook rather
    #    than floating free (see its docstring for why it derives at all).
    # 2. That same total vs the A6 sheet's own column G -- the one KPI column
    #    AUDIT RC-2 did not flag as stale.
    #
    # Both at 0.5%: the expected drift is ~1e-5, so anything approaching the
    # tolerance means something real moved. Do not loosen these.
    shipped_contribution = sum(i["contribution_per_day"] for i in items)
    store_sum_contribution = sum(contribution.values())
    sheet_contribution = sum(r["contribution_per_day"] for r in reference)

    for label, other in (
        ("the ENGINE_STORE per-SKU sum", store_sum_contribution),
        ("the A6 sheet column G", sheet_contribution),
    ):
        if other and abs(shipped_contribution - other) / other > 0.005:
            print(
                f"FAIL  derived contribution/day does not reconcile against {label}: "
                f"derived Rp {shipped_contribution:,.0f} vs Rp {other:,.0f}"
            )
            return 1

    fixture = {
        "schema_version": 1,
        "agent": "retail.assortment_optimization",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_workbook": SOURCE_WORKBOOK,
        "is_mock": True,
        "note": (
            "Workbook demonstration data, not a live ERP position. Delist/grow "
            "classification, GMROI, tail share and capital freed are computed "
            "live from ENGINE/ENGINE_STORE/SKU_Master (chain-wide quartiles), "
            "not read from the A6 sheet's own B:F cells, which a prior audit "
            "found to hold stale hardcoded values. Contribution/day is the one "
            "column that audit did not flag, and reconciles exactly."
        ),
        # Also unrounded, for the same reason as `gmroi` above: these are the
        # cutoffs the browser engine re-classifies against, so a rounded copy
        # here would move the boundary out from under it.
        "classification_thresholds": thresholds,
        "formulas": formulas,
        "filter_options": filter_options,
        "items": items,
        "stores": stores_rollup,
        "by_state_value": by_state_value,
        "reference_by_vertical": reference,
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temp = TARGET.with_suffix(".json.tmp")
    temp.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(TARGET)

    print(f"ok  {TARGET.relative_to(REPO)}")
    print(f"    {len(items)} items, {len(delist)} delist, {len(grow)} grow, {len(stores_rollup)} stores")
    print(f"    contribution/day Rp {shipped_contribution:,.0f}, "
          f"capital freed Rp {sum(i['inv_value'] for i in delist):,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
