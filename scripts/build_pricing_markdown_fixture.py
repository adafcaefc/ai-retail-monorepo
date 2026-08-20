"""Build the Pricing & Markdown (Agent 5) dashboard fixture from workbook data.

Run it yourself:

    python scripts/build_pricing_markdown_fixture.py

Input:  resources/dbtemp/schema_with_data.json  (produced by extract_workbook_schema.py)
Output: frontend/src/agents/retail/pricing_markdown/data/fixture.json

WHY THIS DOES NOT TRUST THE "A5 Pricing & Markdown" SHEET'S OWN CELLS
`Dataset_AI_Retail.xlsx` (untracked, repo root) carries a full audit of this
workbook (sheets "AUDIT Root Cause", "AUDIT Fix Register", "AUDIT
Before-After"). Root cause RC-2 there: A5!C6:G13 (avg depth %, at-risk,
recoverable, write-off, comp idx) are stale hardcoded values pasted from an
old snapshot, not live formulas -- confirmed independently here (this
script's first version reconciled its own from-scratch f12/f14 computation
against that sheet and found the sheet's numbers off by 4-8x, non-uniformly,
which is what a paste-once snapshot looks like next to a live recompute).
The same root cause is flagged for A6, A8 and A9.

ROW GRAIN, NOT A PER-SKU ROLLUP
The A5 sheet's own concept of "Markdown candidates" is a count of ENGINE_STORE
*rows* in a candidate state (1,638: Expiry 153 + Overstock 730 + Slow-mover
755) -- not a count of SKUs that merely touch one of those states somewhere
among their ~20 stores (170, this script's own earlier and undercounting
version). `items` here is therefore one row per ENGINE_STORE record, the same
grain the sheet itself uses -- every KPI (candidates, at-risk, recoverable,
write-off, avg depth, comp idx) is summed or averaged directly over these rows,
no SKU-level rollup in between.

  - `at_risk_value` = that row's own ENGINE_STORE!At-risk (column T).
  - A row is a markdown candidate iff its own `state` is in
    {Expiry, Overstock, Slow-mover}. No aggregation across a SKU's stores.
  - Descriptive, non-monetary fields not carried per-row on ENGINE_STORE
    (name, category label, brand, vendor, comp_idx, elasticity, ...) are
    joined from SKU_Master, constant across a SKU's ~20 rows.

`recoverable_value` IS COMPUTED, NOT READ FROM COLUMN AA
The audit's recommended fix (F-05 / T-12) was to read recoverable value from
ENGINE_STORE!markdown_recoverable ("column AA, renamed from 'At-risk value' to
'Markdown recoverable'"). That rename never reached the currently pinned v8.5
workbook: column AA's header there is still literally "At-risk value", and its
values are byte-identical to column T for every row checked -- it is a
duplicate of gross at-risk, not a distinct recoverable figure, and reading it
as `markdown_recoverable` KeyErrors (confirmed) because no such column exists
in the current extraction. So `recoverable_value` is computed here instead,
via f23-markdown-at-risk-gross -> f14-recoverable-at-risk-value at zero
levers -- the exact same two formulas `frontend/.../pricing_markdown/data/
engine.js`'s What-If engine already runs when a lever moves. Baseline and
simulated recoverable now share one computation instead of two that could
silently disagree.

VALIDATION
Not a reconciliation against the (known-stale) A5 sheet cells. Instead, the
four structural trials from AUDIT Fix Register that apply to inventory rows,
re-run here against the freshly extracted ENGINE_STORE:
  T-01  Position = OnHand + OpenPO
  T-02  Max > ROP
  T-03  AtRisk <= InventoryValue
  T-04  Healthy state must carry AtRisk = 0
Any violation aborts the build. `markdown_candidates` is also checked against
1,638 exactly -- the count independently confirmed against both the raw
`.xlsx` (via openpyxl) and this JSON extract, three ways, before this script
was rewritten to this grain.

WHY NOT backend/src/formulas/repository.py
Agent 4's fixture builder loads its formula catalogue via
`from src.formulas import repository; repository.load()`, which queries a
live database. That is a real backend dependency this pass explicitly
avoids. This script reads resources/dbtemp/formula.json directly instead --
the same catalogue, as a local file, no connection required. f14 is shipped
in the fixture for the browser's What-If engine (Task 4) to project a NEW
recoverable value under a lever scenario; it is not used to compute the
shipped baseline, which comes from the workbook's own (now-corrected)
ENGINE_STORE!markdown_recoverable instead.

DATA HONESTY
Internally consistent demonstration data, not a live ERP position. The
payload carries `is_mock: true` and a note; the UI labels it rather than
presenting it as measured.

f14/f23, TWO FORMULAS THAT TRAVEL TOGETHER
f14-recoverable-at-risk-value takes {gross, state, elasticity,
markdown_lever}, not the position/ads/shelf_life/price inputs its name might
suggest -- those belong to f23-markdown-at-risk-gross, whose `gross` output is
f14's own first input. Both are shipped in `formulas` so the browser's
What-If engine can chain them; shipping only f14 (or shipping a substitute
expression under its id) breaks the markdown lever, which f14 is the one
formula in this catalogue to model.
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
from src.formulas.expression import evaluate, parse  # noqa: E402

SOURCE = REPO / "resources" / "dbtemp" / "schema_with_data.json"
FORMULA_CATALOGUE = REPO / "resources" / "dbtemp" / "formula.json"
TARGET = (
    REPO
    / "frontend"
    / "src"
    / "agents"
    / "retail"
    / "pricing_markdown"
    / "data"
    / "fixture.json"
)
SOURCE_WORKBOOK = "AI_360_Retail_Suite_v8.5_General_9Agents 20260819.xlsx"

CANDIDATE_STATES = ("Expiry", "Overstock", "Slow-mover")
STATE_ORDER = ("Stockout", "Low", "Expiry", "Overstock", "Slow-mover", "Healthy")

# Independently confirmed against the pinned v8.5 workbook three ways (raw
# .xlsx via openpyxl, this JSON extract, per-state row counts summing to it)
# before this script was rewritten to row grain. A mismatch means the
# extraction or the workbook itself changed underneath this script.
EXPECTED_MARKDOWN_CANDIDATES = 1638

# f14's own baseline depth constants at markdown_lever=0 (see
# resources/dbtemp/formula.json's f14-recoverable-at-risk-value expression).
# build_reference() below weights these by candidate at-risk value, the same
# computation backend/src/llm/agents/retail/pricing_markdown/dashboard.py's
# build_reference() runs for the live path.
DEPTH_BY_STATE = {"Expiry": 0.4, "Overstock": 0.25, "Slow-mover": 0.3}

# Formulas the browser What-If engine re-evaluates (f12/f23/f14 included for
# that purpose only -- see the module docstring). Not evaluated in this
# script. f14 takes {gross, state, elasticity, markdown_lever}; `gross` is
# f23's own output, so both travel together or the browser engine cannot
# chain them.
CATALOGUE_FORMULAS = (
    "f01-ads-per-store",
    "f03-open-po-per-store",
    "f04-position",
    "f05-rop",
    "f06-maximum-inventory",
    "f07-inventory-state",
    "f12-at-risk-value",
    "f14-recoverable-at-risk-value",
    "f20-days-of-supply",
    "f21-inventory-value",
    "f22-expiry-units",
    "f23-markdown-at-risk-gross",
)


def load_tables() -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = [dict(zip(names, row)) for row in table["rows"]]
    return tables


def load_formulas() -> dict[str, str]:
    """Read the formula catalogue as a local file -- no database connection."""
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
    neither ROP nor Max, so the browser engine's re-derived state would
    disagree with the shipped one the moment a lever moves.

    SUMIFS, not a lookup, because that is what the workbook does.
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
    hz_cov: float,
) -> list[str]:
    """Re-derive every stored ROP and Max from f05/f06 and insist they match.

    Without this, a wrong lead-time source is invisible: every displayed
    figure still looks plausible while the browser engine quietly classifies
    a different set of SKUs than the fixture shipped.
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
        max_inventory = evaluate(
            asts["f06-maximum-inventory"], {**reorder, "horizon_coverage": hz_cov}
        )
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


def run_structural_trials(engine_store: list[dict[str, Any]]) -> list[str]:
    """AUDIT Fix Register's T-01..T-04, re-run against this extraction.

    These are the trials that apply to a single inventory row (T-05..T-11 are
    about vendor lead time, PO consolidation and What-If baseline freezing --
    out of scope for a markdown board). A violation means the workbook fix
    did not fully take, or this extraction predates it.
    """
    failures: list[str] = []

    bad = [r for r in engine_store if abs(_num(r["position"]) - (_num(r["on_hand"]) + _num(r["open_po"]))) > 1]
    if bad:
        failures.append(f"T-01 Position = OnHand + OpenPO: {len(bad)} row(s) violate it")

    bad = [r for r in engine_store if _num(r["max"]) <= _num(r["rop"])]
    if bad:
        failures.append(f"T-02 Max > ROP: {len(bad)} row(s) violate it")

    bad = [r for r in engine_store if _num(r["at_risk"]) > _num(r["inv_value"]) + 1]
    if bad:
        failures.append(f"T-03 AtRisk <= InventoryValue: {len(bad)} row(s) violate it")

    bad = [r for r in engine_store if r["state"] == "Healthy" and _num(r["at_risk"]) > 0]
    if bad:
        failures.append(f"T-04 Healthy state must carry AtRisk = 0: {len(bad)} row(s) violate it")

    return failures


def build_items(
    engine_store: list[dict[str, Any]],
    sku_master: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
    lead_times: dict[str, float],
    hz_cov: float,
    asts: dict[str, Any],
) -> list[dict[str, Any]]:
    """One row per ENGINE_STORE record -- see the module docstring for why.

    `recoverable_value`/`write_off_value` are computed per row via
    f23-markdown-at-risk-gross -> f14-recoverable-at-risk-value at zero
    levers (`markdown_lever=0`), not read from a workbook column -- see the
    module docstring for why that column no longer exists to read.
    """
    by_sku = {row["sku_id"]: row for row in sku_master}
    vertical_order = {row["vertical_id"]: i for i, row in enumerate(verticals)}
    ordered = sorted(
        engine_store,
        key=lambda row: (
            vertical_order.get(row.get("vertical_id"), len(verticals)),
            -_num(row.get("at_risk")),
        ),
    )

    items = []
    for row in ordered:
        master = by_sku.get(row["sku_id"])
        if not master:
            continue

        state = row["state"]
        position = _num(row["position"])
        price = _num(row["price"])
        ads = _num(row["ads"])
        max_inventory = _num(row["max"])
        shelf_life_days = _num(master.get("expiry_d"))
        elasticity = _num(master.get("elasticity"))
        at_risk_value = _num(row["at_risk"])

        gross = evaluate(
            asts["f23-markdown-at-risk-gross"],
            {
                "state": state, "position": position, "ads": ads,
                "shelf_life_days": shelf_life_days, "max_inventory": max_inventory,
                "price": price,
            },
        )
        recoverable_value = evaluate(
            asts["f14-recoverable-at-risk-value"],
            {"gross": gross, "state": state, "elasticity": elasticity, "markdown_lever": 0},
        )
        write_off_value = max(0.0, at_risk_value - recoverable_value)

        # This row already IS one store, so f01's store_size is that store's
        # own size_index (not the vertical total a chain-net item would need),
        # and f03's ratio is 1 at rest -- see engine.js's What-If cascade.
        store_size = _num(row.get("size"))

        items.append(
            {
                "sku_id": row["sku_id"],
                "store_id": row["store_id"],
                "name": master.get("item", row["sku_id"]),
                "vertical_id": row["vertical_id"],
                "category_id": row["cat_id"],
                "category_label": master.get("category", row["cat_id"]),
                "brand": master.get("brand", ""),
                "vendor": master.get("vendor", ""),
                "cluster": row.get("cluster"),
                "channel": row.get("channel"),
                "state": state,
                "severity_rank": STATE_ORDER.index(state) if state in STATE_ORDER else len(STATE_ORDER),
                "is_markdown_candidate": state in CANDIDATE_STATES,
                "position": position,
                "rop": _num(row["rop"]),
                "max": max_inventory,
                "dos": _num(row["dos"]),
                "ads": ads,
                "price": price,
                "inv_value": _num(row["inv_value"]),
                "at_risk_value": round(at_risk_value, 2),
                "recoverable_value": round(recoverable_value, 2),
                "write_off_value": round(write_off_value, 2),
                "expiry_units": _num(row.get("expiry")),
                "shelf_life_days": shelf_life_days,
                "is_perishable": str(row.get("perish", master.get("perishable", "N"))).strip().upper() == "Y",
                "perishable": row.get("perish", master.get("perishable", "N")),
                "growth": _num(master.get("growth")),
                "comp_idx": _num(master.get("comp_idx")),
                # f14-recoverable-at-risk-value's own input, for the browser
                # engine's What-If re-simulation (see engine.js).
                "elasticity": elasticity,
                "open_po": _num(row.get("open_po")),
                "on_hand": _num(row.get("on_hand")),
                # What-If cascade inputs for the browser engine (Task 4).
                # arch_horizon_factor/horizon_coverage are required by
                # f01-ads-per-store/f06-maximum-inventory respectively (v8.5)
                # -- omitting them crashes the engine the instant a lever
                # moves, the same defect fixed today in Replenishment's
                # fixture builder.
                "base_ads": _num(master.get("base_ads")),
                "seasonality": _num(master.get("seasonality")),
                "arch_horizon_factor": _num(row.get("archhz")),
                "store_size": store_size,
                "total_store_size": store_size,
                "horizon_coverage": hz_cov,
                "stock_factor": _num(row.get("stockf")),
                "onhand_days": _num(master.get("onhand_days")),
                "promo_eligible": master.get("promo", "N"),
                "promo_depth": _num(master.get("cannib_pct")),
                # The designated trade agreement's lead time -- see
                # designated_lead_times() for why this is not sku_master.lead_d.
                "lead_days": lead_times.get(row["sku_id"], 0.0),
                "safety_days": _num(master.get("safety_d")),
            }
        )
    return items


def classify(item: dict[str, Any]) -> str | None:
    """A5 spec section 7's markdownClassify, as a clean 4-way partition.

    Suppress Reorder is the subset of Overstock candidates that still carry
    open PO (inbound supply that would worsen an already-excess position --
    the exact case spec section 11 names). Keeps the four tabs a true
    partition of the candidate population.
    """
    if not item["is_markdown_candidate"]:
        return None
    if item["state"] == "Expiry":
        return "expiry_markdown"
    if item["state"] == "Overstock":
        return "suppress_reorder" if item["open_po"] > 0 else "overstock_clearance"
    if item["state"] == "Slow-mover":
        return "slow_mover_price_cut"
    return None


RECOMMENDATION_BY_TAB = {
    "expiry_markdown": "Immediate markdown / short expiry clearance",
    "overstock_clearance": "Clearance markdown and block replenishment",
    "slow_mover_price_cut": "Price cut or targeted promo",
    "suppress_reorder": "Suppress reorder and clear existing position first",
}


def build_store_rows(
    engine_store: list[dict[str, Any]],
    stores: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per-store aggregates for the dimension charts. GROSS figures: they sum
    local pockets of risk and will exceed the chain-net headline (A5 spec
    section 11) -- intentional, not a reconciliation bug.
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
                "expiry_count": 0,
                "overstock_count": 0,
                "slow_mover_count": 0,
                "other_count": 0,
                "at_risk_value": 0.0,
                "inv_value": 0.0,
            }
        bucket["sku_count"] += 1
        state = row["state"]
        if state == "Expiry":
            bucket["expiry_count"] += 1
        elif state == "Overstock":
            bucket["overstock_count"] += 1
        elif state == "Slow-mover":
            bucket["slow_mover_count"] += 1
        else:
            bucket["other_count"] += 1
        bucket["at_risk_value"] += _num(row.get("at_risk"))
        bucket["inv_value"] += _num(row.get("inv_value"))

    return sorted(grouped.values(), key=lambda row: row["store_id"])


def build_reference(
    items: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Avg markdown depth per vertical, weighted by candidate at-risk value.

    Previously this read avg_depth_pct verbatim off the workbook's "A5
    Pricing & Markdown" sheet -- the same stale-hardcode issue AUDIT Root
    Cause RC-2 flags, and the reason `markdown_candidates`,
    `at_risk_state_value`, `recoverable` and `write_off` from that sheet were
    already dropped from this function. avg_depth_pct was left as an
    apparent oversight rather than a deliberate exception: nothing about it
    needs the sheet -- it is computed here the same way
    backend/src/llm/agents/retail/pricing_markdown/dashboard.py's own
    build_reference() already does for the live path, weighting f14's
    baseline depth constants (DEPTH_BY_STATE) by each candidate SKU's
    at_risk_value.
    """
    label_by_vertical = {
        row["vertical_id"]: row.get("dashboard_label") or row.get("vertical") or row["vertical_id"]
        for row in verticals
    }

    totals: dict[str, list[float]] = {}
    for item in items:
        if not item["is_markdown_candidate"]:
            continue
        weight = item["at_risk_value"]
        depth = DEPTH_BY_STATE.get(item["state"])
        if depth is None or weight <= 0:
            continue
        bucket = totals.setdefault(item["vertical_id"], [0.0, 0.0])
        bucket[0] += depth * weight
        bucket[1] += weight

    reference = [
        {
            "legal_entity_id": vertical_id,
            "vertical_label": label_by_vertical.get(vertical_id, vertical_id),
            "avg_depth_pct": round((weighted / total) * 100, 2) if total else 0.0,
        }
        for vertical_id, (weighted, total) in totals.items()
    ]
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
                # id first: category name is not unique across verticals
                # (e.g. DGT-C01 and OMN-C01 are both "Electronics"), so the
                # bare name alone cannot tell two dropdown entries apart.
                "label": f"{cat_id} · {row.get('category', cat_id)}",
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
    # A fixture built from the wrong workbook is committed to the repo
    # and read by every board in standalone mode, so it needs the same
    # check the seeders make before they touch the warehouse.
    workbook_guard.check(SOURCE)

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
        "a5_pricing_markdown",
        "constants",
    ):
        if required not in tables:
            print(f"FAIL  source is missing table: {required}")
            return 1

    # f06-maximum-inventory's hzCov term (Constants!B24, v8.5).
    by_cell = {row["source_cell"]: row for row in tables["constants"]}
    if "B24" not in by_cell:
        print("FAIL  Constants!B24 (hzCov) is not in the extract")
        return 1
    hz_cov = float(by_cell["B24"]["value"])

    formulas = load_formulas()
    asts = {name: parse(expr) for name, expr in formulas.items()}

    trial_failures = run_structural_trials(tables["engine_store"])
    if trial_failures:
        print("FAIL  structural trials against ENGINE_STORE:")
        for line in trial_failures:
            print(f"      {line}")
        return 1

    lead_times = designated_lead_times(tables["trade_agreements"])
    reorder_failures = verify_reorder_inputs(
        tables["engine"],
        {r["sku_id"]: r for r in tables["sku_master"]},
        lead_times,
        asts,
        hz_cov,
    )
    if reorder_failures:
        print("FAIL  f05/f06 do not reproduce the stored ROP/Max:")
        for line in reorder_failures:
            print(f"      {line}")
        return 1

    stores_by_id = {row["store_id"]: row for row in tables["stores"]}
    items = build_items(
        tables["engine_store"], tables["sku_master"], tables["verticals"], lead_times, hz_cov, asts,
    )
    for item in items:
        item["best_action_tab"] = classify(item)
        item["recommendation"] = RECOMMENDATION_BY_TAB.get(item["best_action_tab"], "Hold price")

    stores_rollup = build_store_rows(tables["engine_store"], stores_by_id)
    reference = build_reference(items, tables["verticals"])
    filter_options = build_filter_options(tables["verticals"], tables["sku_master"], tables["stores"])

    candidates = [i for i in items if i["is_markdown_candidate"]]
    if len(candidates) != EXPECTED_MARKDOWN_CANDIDATES:
        print(
            f"FAIL  markdown_candidates is {len(candidates)}, expected exactly "
            f"{EXPECTED_MARKDOWN_CANDIDATES} (Expiry/Overstock/Slow-mover rows "
            "in ENGINE_STORE) -- the workbook or extraction changed underneath "
            "this script"
        )
        return 1

    fixture = {
        "schema_version": 1,
        "agent": "retail.pricing_markdown",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_workbook": SOURCE_WORKBOOK,
        "is_mock": True,
        "note": (
            "Workbook demonstration data, not a live ERP position. `items` is "
            "one row per ENGINE_STORE record (SKU x store, 16,000 rows) -- the "
            "A5 sheet's own grain -- not a chain-net SKU rollup, so every KPI "
            "sums/averages directly over these rows. At-risk value is read "
            "from ENGINE_STORE; recoverable value is computed via f23/f14 at "
            "zero levers, not read from the A5 sheet's own cells, which a "
            "prior audit found to hold stale hardcoded values."
        ),
        "formulas": formulas,
        "filter_options": filter_options,
        "items": items,
        "stores": stores_rollup,
        "reference_by_vertical": reference,
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temp = TARGET.with_suffix(".json.tmp")
    # Compact, not indent=2: items grew 20x (800 -> 16,000 rows) with this
    # rewrite, and pretty-printing roughly doubles a file this size for zero
    # benefit -- nothing reads this file by eye. Matches every other retail
    # fixture builder's own format.
    temp.write_text(
        json.dumps(fixture, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    temp.replace(TARGET)

    print(f"ok  {TARGET.relative_to(REPO)}")
    print(f"    {len(items)} items, {len(candidates)} markdown candidates, {len(stores_rollup)} stores")
    print(f"    at-risk Rp {sum(i['at_risk_value'] for i in candidates):,.0f}, "
          f"recoverable Rp {sum(i['recoverable_value'] for i in candidates):,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
