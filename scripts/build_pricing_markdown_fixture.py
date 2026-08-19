"""Build the Pricing & Markdown (Agent 5) dashboard fixture from workbook data.

Run it yourself:

    python scripts/build_pricing_markdown_fixture.py

Input:  resources/dbtemp/schema_with_data.json  (produced by extract_workbook_schema.py)
Output: frontend/src/agents/retail/pricing_markdown/data/fixture.json

WHY THIS DOES NOT TRUST THE "A5 Pricing & Markdown" SHEET
`Dataset_AI_Retail.xlsx` (untracked, repo root) carries a full audit of this
workbook (sheets "AUDIT Root Cause", "AUDIT Fix Register", "AUDIT
Before-After"). Root cause RC-2 there: A5!C6:G13 (avg depth %, at-risk,
recoverable, write-off, comp idx) are stale hardcoded values pasted from an
old snapshot, not live formulas -- confirmed independently here (this
script's first version reconciled its own from-scratch f12/f14 computation
against that sheet and found the sheet's numbers off by 4-8x, non-uniformly,
which is what a paste-once snapshot looks like next to a live recompute).
The same root cause is flagged for A6, A8 and A9.

The audit's own recommended fix (F-05 / T-12) is to source at-risk and
recoverable value from ENGINE_STORE (store grain) via SUMIFS rather than
from the stale A5 sheet or the chain-net ENGINE table. This script follows
that recommendation:

  - at_risk_value / recoverable_value per SKU = SUM across that SKU's stores
    of ENGINE_STORE!at_risk / ENGINE_STORE!markdown_recoverable (the AA
    column, renamed by the workbook fix from "At-risk value" to "Markdown
    recoverable" -- it was always the recoverable figure, mislabeled).
  - A SKU is a markdown candidate if ANY of its stores show
    state in {Expiry, Overstock, Slow-mover}; the displayed `state` label is
    the candidate state carrying the largest at-risk value for that SKU.
  - Descriptive, non-monetary fields (position, price, ads, dos, rop, max,
    vendor, brand, category) are read from the chain-net ENGINE table, which
    RC-2 does not flag as broken -- only the money-at-risk figures were.

VALIDATION
Not a reconciliation against the (known-stale) A5 sheet. Instead, the four
structural trials from AUDIT Fix Register that apply to inventory rows,
re-run here against the freshly extracted ENGINE_STORE:
  T-01  Position = OnHand + OpenPO
  T-02  Max > ROP
  T-03  AtRisk <= InventoryValue
  T-04  Healthy state must carry AtRisk = 0
Any violation aborts the build. The candidate-scope recoverable total is also
checked against the audit's own verified "Before-After: rumus hidup" figure
for ENGINE_STORE!AA (Rp 58,301,830,268) -- a live-recomputed number the
audit already confirmed independently, not this script re-deriving its own
expectation and then agreeing with itself.

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
CANDIDATE_PRIORITY = {"Expiry": 0, "Overstock": 1, "Slow-mover": 2}

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

# The audit's own verified "live formula" total for ENGINE_STORE!markdown
# recoverable, across every candidate-state row chain-wide (AUDIT
# Before-After, "Markdown recovery (ENGINE_STORE!AA)", SESUDAH column).
AUDIT_VERIFIED_RECOVERABLE_TOTAL = 58_301_830_268


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


def aggregate_markdown_by_sku(
    engine_store: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Roll ENGINE_STORE up to one markdown summary per SKU.

    `at_risk_value` sums every store (a SKU with any non-healthy store
    carries exposure there); `recoverable_value` sums only the
    candidate-state stores, since markdown_recoverable is already 0
    elsewhere by construction (T-04-adjacent: verified empirically -- no
    non-candidate row in this extraction carries a nonzero recoverable
    value). `state` is a DISPLAY label only: the candidate state contributing
    the most at-risk value for that SKU, chosen by CANDIDATE_PRIORITY when
    tied. It does not gate which stores are summed.
    """
    by_sku: dict[str, dict[str, Any]] = {}
    for row in engine_store:
        sku = row["sku_id"]
        bucket = by_sku.setdefault(
            sku,
            {"at_risk_value": 0.0, "recoverable_value": 0.0, "candidate_states": {}},
        )
        bucket["at_risk_value"] += _num(row["at_risk"])
        state = row["state"]
        if state in CANDIDATE_STATES:
            bucket["recoverable_value"] += _num(row["markdown_recoverable"])
            bucket["candidate_states"][state] = bucket["candidate_states"].get(state, 0.0) + _num(row["at_risk"])

    for sku, bucket in by_sku.items():
        candidates = bucket.pop("candidate_states")
        if candidates:
            bucket["is_markdown_candidate"] = True
            bucket["display_state"] = max(
                candidates.items(),
                key=lambda kv: (kv[1], -CANDIDATE_PRIORITY[kv[0]]),
            )[0]
        else:
            bucket["is_markdown_candidate"] = False
            bucket["display_state"] = None
        bucket["write_off_value"] = max(0.0, bucket["at_risk_value"] - bucket["recoverable_value"])

    return by_sku


def build_items(
    engine: list[dict[str, Any]],
    sku_master: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
    markdown_by_sku: dict[str, dict[str, Any]],
    lead_times: dict[str, float],
) -> list[dict[str, Any]]:
    """One row per SKU. Descriptive fields from ENGINE (chain-net, not
    flagged by RC-2); at-risk/recoverable/write-off/candidacy from the
    ENGINE_STORE aggregation above.
    """
    by_sku = {row["sku_id"]: row for row in sku_master}
    vertical_order = {row["vertical_id"]: i for i, row in enumerate(verticals)}
    ordered = sorted(
        engine,
        key=lambda row: (
            vertical_order.get(row.get("vertical_id"), len(verticals)),
            -markdown_by_sku.get(row["sku_id"], {}).get("at_risk_value", 0.0),
        ),
    )

    items = []
    for row in ordered:
        master = by_sku.get(row["sku_id"])
        if not master:
            continue

        md = markdown_by_sku.get(row["sku_id"], {
            "at_risk_value": 0.0, "recoverable_value": 0.0, "write_off_value": 0.0,
            "is_markdown_candidate": False, "display_state": None,
        })
        position = _num(row["position"])
        price = _num(row["price"])
        max_inventory = _num(row["max"])
        shelf_life_days = _num(master.get("expiry_d"))
        # Chain state (ENGINE!state) as the fallback label for non-candidates,
        # since the state-distribution chart (spec section 6) needs every SKU
        # labelled, not only the 234 markdown candidates.
        display_state = md["display_state"] or row["state"]

        items.append(
            {
                "sku_id": row["sku_id"],
                "name": master.get("item", row["sku_id"]),
                "vertical_id": row["vertical_id"],
                "category_id": row["cat_id"],
                "category_label": master.get("category", row["cat_id"]),
                "brand": master.get("brand", ""),
                "vendor": master.get("vendor", ""),
                "state": display_state,
                "severity_rank": STATE_ORDER.index(display_state) if display_state in STATE_ORDER else len(STATE_ORDER),
                "is_markdown_candidate": md["is_markdown_candidate"],
                "position": position,
                "rop": _num(row["rop"]),
                "max": max_inventory,
                "dos": _num(row["dos"]),
                "ads": _num(row["ads"]),
                "price": price,
                "inv_value": _num(row["inv_value"]),
                "at_risk_value": round(md["at_risk_value"], 2),
                "recoverable_value": round(md["recoverable_value"], 2),
                "write_off_value": round(md["write_off_value"], 2),
                "expiry_units": _num(row.get("expiry_u")),
                "shelf_life_days": shelf_life_days,
                "is_perishable": str(master.get("perishable", "N")).strip().upper() == "Y",
                "perishable": master.get("perishable", "N"),
                "growth": _num(master.get("growth")),
                "comp_idx": _num(master.get("comp_idx")),
                # f14-recoverable-at-risk-value's own input, for the browser
                # engine's What-If re-simulation (see engine.js).
                "elasticity": _num(master.get("elasticity")),
                "open_po": _num(row.get("open_po")),
                "on_hand": position - _num(row.get("open_po")),
                # What-If cascade inputs for the browser engine (Task 4).
                "base_ads": _num(master.get("base_ads")),
                "seasonality": _num(master.get("seasonality")),
                "store_size": _num(master.get("sum_vert_size")),
                "stock_factor": _num(master.get("stockf")),
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
    a5: list[dict[str, Any]],
    verticals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Vertical labels plus the two fields with no live per-SKU source
    (avg_depth_pct, comp_idx-as-fallback). `markdown_candidates`,
    `at_risk_state_value`, `recoverable` and `write_off` from this sheet are
    NOT carried through -- AUDIT Root Cause RC-2 flags them as stale
    hardcodes; the live equivalents are computed from items in selectors.js.
    """
    label_to_id = {row["dashboard_label"]: row["vertical_id"] for row in verticals}
    reference = []
    for row in a5:
        vertical_id = label_to_id.get(row["vertical_label"], row["vertical_label"])
        reference.append(
            {
                "legal_entity_id": vertical_id,
                "vertical_label": row["vertical_label"],
                # Vertical-level only; no per-SKU depth exists in the engine.
                # Carried as reference context, not reconciled -- see spec
                # section 11 and this script's module docstring.
                "avg_depth_pct": _num(row["avg_depth_pct"]),
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
    markdown_by_sku = aggregate_markdown_by_sku(tables["engine_store"])
    items = build_items(
        tables["engine"], tables["sku_master"], tables["verticals"], markdown_by_sku, lead_times
    )
    for item in items:
        item["best_action_tab"] = classify(item)
        item["recommendation"] = RECOMMENDATION_BY_TAB.get(item["best_action_tab"], "Hold price")

    stores_rollup = build_store_rows(tables["engine_store"], stores_by_id)
    reference = build_reference(tables["a5_pricing_markdown"], tables["verticals"])
    filter_options = build_filter_options(tables["verticals"], tables["sku_master"], tables["stores"])

    candidates = [i for i in items if i["is_markdown_candidate"]]
    if not candidates:
        print("FAIL  no markdown candidates found in engine_store")
        return 1

    shipped_recoverable = sum(i["recoverable_value"] for i in candidates)
    if abs(shipped_recoverable - AUDIT_VERIFIED_RECOVERABLE_TOTAL) / AUDIT_VERIFIED_RECOVERABLE_TOTAL > 0.005:
        print(
            "FAIL  recoverable value does not match the audit's verified total: "
            f"shipped Rp {shipped_recoverable:,.0f} vs audit Rp {AUDIT_VERIFIED_RECOVERABLE_TOTAL:,.0f}"
        )
        return 1

    fixture = {
        "schema_version": 1,
        "agent": "retail.pricing_markdown",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_workbook": SOURCE_WORKBOOK,
        "is_mock": True,
        "note": (
            "Workbook demonstration data, not a live ERP position. At-risk and "
            "recoverable value are summed from ENGINE_STORE (store grain) per "
            "AUDIT Fix Register F-05, not read from the A5 sheet's own cells, "
            "which a prior audit found to hold stale hardcoded values. Store/"
            "cluster/channel charts are gross and will not reconcile 1:1 with "
            "the chain-net headline."
        ),
        "formulas": formulas,
        "filter_options": filter_options,
        "items": items,
        "stores": stores_rollup,
        "reference_by_vertical": reference,
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temp = TARGET.with_suffix(".json.tmp")
    temp.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(TARGET)

    print(f"ok  {TARGET.relative_to(REPO)}")
    print(f"    {len(items)} items, {len(candidates)} markdown candidates, {len(stores_rollup)} stores")
    print(f"    at-risk Rp {sum(i['at_risk_value'] for i in candidates):,.0f}, "
          f"recoverable Rp {shipped_recoverable:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
