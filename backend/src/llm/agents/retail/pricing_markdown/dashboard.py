"""Agent 5 · Pricing & Markdown — the rows the board aggregates.

Returns the shape `scripts/build_pricing_markdown_fixture.py` ships, not the
pre-aggregated `kpis/views/side` envelope Promotion Effectiveness returns: the
board's own selectors (`frontend/.../pricing_markdown/data/selectors.js`)
expect semi-raw `items`/`stores`/`formulas`/`reference_by_vertical` and do the
KPI/chart aggregation themselves, same as the fixture. See
`retail/common/warehouse.py` for why the aggregation stays in the browser.

TWO GRAINS, LIKE THE FIXTURE BUILDER
-------------------------------------
`fact_inventory_chain_daily` (chain-net, one row per item) carries every
descriptive field the candidate table and KPI cards show: position, rop, max,
ads, days_cover, price, inventory_value, expiry_units. RC-2 of the workbook
audit did not flag these as broken.

`fact_inventory_daily` (store grain, ~16,000 rows) is where markdown
candidacy and its money figures come from, per the audit's own recommended
fix (F-05): a SKU is a markdown candidate if ANY of its stores show state in
{Expiry, Overstock, Slow-mover}, and `at_risk_value` / `recoverable_value` are
summed across that SKU's stores rather than read off the chain fact's own
`at_risk_value` column (a different, chain-net figure). Neither
`fact_inventory_daily` nor `fact_inventory_chain_daily` stores the two
markdown-specific columns migration 004 added
(`markdown_at_risk_value`/`markdown_recoverable`) populated — the seeder never
wrote them — so this module computes them itself, at request time, via the
same f12/f23/f14 formulas the browser's What-If engine runs, read from
`retail.formula` (never hand-restated). This is deliberately unscoped by any
filter: an item's own money figures must be its true full-chain values
regardless of which vertical/category the caller is looking at, exactly as
`scripts/build_pricing_markdown_fixture.py::aggregate_markdown_by_sku` runs
over the whole ENGINE_STORE table before any scope is applied.

WHY `is_mock` STAYS TRUE
See `warehouse.envelope()`: rows are real, but they are one workbook snapshot
day, not a live ERP position. That does not change when Postgres replaces the
checked-in fixture as the source, so the board's "Workbook data" label is
accurate before and after this module exists.
"""

from __future__ import annotations

from typing import Any

from src.formulas import repository
from src.formulas.expression import evaluate, parse
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    SCHEMA,
    SNAPSHOT_DATE,
    STATE_ORDER,
    SUPPORTED_FILTERS,
    _rows,
    chain_store_size,
    envelope,
    filter_options,
    formulas,
    get_engine,
)

AGENT_ID = "retail.pricing_markdown"

CHAIN = f"{SCHEMA}.fact_inventory_chain_daily"
STORE_FACT = f"{SCHEMA}.fact_inventory_daily"
ITEM = f"{SCHEMA}.dim_item"
STORE_DIM = f"{SCHEMA}.dim_store"
VERTICAL = f"{SCHEMA}.dim_vertical"
TRADE_AGREEMENT = f"{SCHEMA}.trade_agreement"

# Formulas the browser What-If engine re-evaluates (see
# frontend/.../pricing_markdown/data/engine.js's REQUIRED_FORMULAS). f12, f23
# and f14 are also evaluated here, server-side, to compute the baseline
# at-risk/recoverable/write-off figures shipped on every item.
ENGINE_FORMULAS = (
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

# A5 spec section 2: markdown candidates are exactly these three states.
# Stockout and Low are Replenishment's (Agent 3) territory.
CANDIDATE_STATES = frozenset({"Expiry", "Overstock", "Slow-mover"})
CANDIDATE_PRIORITY = {"Expiry": 0, "Overstock": 1, "Slow-mover": 2}

# A5 spec section 7's markdownClassify. Overstock candidates that still carry
# open PO need reorder suppressed before anything else -- mirrored from
# scripts/build_pricing_markdown_fixture.py::classify().
BEST_ACTION_BY_STATE = {"Expiry": "expiry_markdown", "Slow-mover": "slow_mover_price_cut"}
RECOMMENDATION_BY_TAB = {
    "expiry_markdown": "Immediate markdown / short expiry clearance",
    "overstock_clearance": "Clearance markdown and block replenishment",
    "slow_mover_price_cut": "Price cut or targeted promo",
    "suppress_reorder": "Suppress reorder and clear existing position first",
}

NOTE = (
    "Workbook demonstration data, not a live ERP position. At-risk and "
    "recoverable value are summed from fact_inventory_daily (store grain) per "
    "AUDIT Fix Register F-05, not read from a chain-net column. Store/"
    "cluster/channel charts are gross and will not reconcile 1:1 with the "
    "chain-net headline."
)

# legal_entity_id and category_group narrow the returned `items`; state and
# store_id stay client-side only (frontend/.../data/selectors.js's scopeItems
# and scopeStores), the same split promotion_effectiveness uses for store_id.
# An item's own at-risk/recoverable value must reflect its true full-chain
# total regardless of scope, so narrowing further here would corrupt that
# figure rather than merely trim the payload -- see the module docstring.
# (Imported from warehouse, already exactly this pair -- re-exported below.)

_MONEY_FORMULA_IDS = (
    "f12-at-risk-value",
    "f23-markdown-at-risk-gross",
    "f14-recoverable-at-risk-value",
)
_ast_cache: dict[str, Any] | None = None


def _asts() -> dict[str, Any]:
    global _ast_cache
    if _ast_cache is None:
        catalogue = {entry["id"]: entry["expression"] for entry in repository.load()}
        _ast_cache = {name: parse(catalogue[name]) for name in _MONEY_FORMULA_IDS}
    return _ast_cache


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _store_money(row: dict[str, Any]) -> dict[str, float]:
    """f12/f23/f14 for one store-grain row, at the workbook's baseline lever.

    `markdown_lever=0` is the workbook's own resting position (Constants
    B18) -- the same baseline the browser engine starts every What-If
    scenario from.
    """
    asts = _asts()
    state = row["state"]
    position = _float(row["position_qty"])
    price = _float(row["price"])
    at_risk = evaluate(asts["f12-at-risk-value"], {"state": state, "position": position, "price": price})
    gross = evaluate(
        asts["f23-markdown-at-risk-gross"],
        {
            "state": state,
            "position": position,
            "ads": _float(row["ads"]),
            "shelf_life_days": _float(row["shelf_life_days"]),
            "max_inventory": _float(row["max_qty"]),
            "price": price,
        },
    )
    recoverable = evaluate(
        asts["f14-recoverable-at-risk-value"],
        {
            "gross": gross,
            "state": state,
            "elasticity": _float(row["elasticity"]),
            "markdown_lever": 0,
        },
    )
    return {"at_risk": at_risk, "gross": gross, "recoverable": recoverable}


def aggregate_markdown_by_sku(store_money_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Roll fact_inventory_daily up to one markdown summary per SKU.

    Mirrors scripts/build_pricing_markdown_fixture.py::aggregate_markdown_by_sku:
    `at_risk_value` sums every store (a SKU with any non-Healthy store carries
    exposure there); `recoverable_value` sums only the candidate-state stores.
    `state` is a DISPLAY label only -- the candidate state contributing the
    most at-risk value for that SKU, tie-broken by CANDIDATE_PRIORITY. It does
    not gate which stores are summed into at_risk_value.

    Takes rows already merged with `_store_money` (via `build()`'s single
    pass over `store_rows`) rather than recomputing it here -- f12/f23/f14 run
    once per store row, not twice.
    """
    by_sku: dict[str, dict[str, Any]] = {}
    for row in store_money_rows:
        sku = row["item_key"]
        bucket = by_sku.setdefault(
            sku,
            {"at_risk_value": 0.0, "recoverable_value": 0.0, "candidate_states": {}, "open_po": 0.0},
        )
        bucket["at_risk_value"] += row["at_risk"]
        bucket["open_po"] += _float(row.get("open_po_qty"))
        state = row["state"]
        if state in CANDIDATE_STATES:
            bucket["recoverable_value"] += row["recoverable"]
            bucket["candidate_states"][state] = bucket["candidate_states"].get(state, 0.0) + row["at_risk"]

    for bucket in by_sku.values():
        candidates = bucket.pop("candidate_states")
        if candidates:
            bucket["is_markdown_candidate"] = True
            bucket["display_state"] = max(
                candidates.items(), key=lambda kv: (kv[1], -CANDIDATE_PRIORITY[kv[0]])
            )[0]
        else:
            bucket["is_markdown_candidate"] = False
            bucket["display_state"] = None
        bucket["write_off_value"] = max(0.0, bucket["at_risk_value"] - bucket["recoverable_value"])

    return by_sku


def classify(state: str | None, is_candidate: bool, open_po: float) -> str | None:
    if not is_candidate or not state:
        return None
    if state == "Overstock":
        return "suppress_reorder" if open_po > 0 else "overstock_clearance"
    return BEST_ACTION_BY_STATE.get(state)


def build_items(
    chain_rows: list[dict[str, Any]],
    markdown_by_sku: dict[str, dict[str, Any]],
    lead_days: dict[str, float],
    store_sizes: dict[str, float],
) -> list[dict[str, Any]]:
    """One row per SKU, chain-net descriptive fields plus store-grain money."""
    empty_money = {
        "at_risk_value": 0.0,
        "recoverable_value": 0.0,
        "write_off_value": 0.0,
        "is_markdown_candidate": False,
        "display_state": None,
        "open_po": 0.0,
    }
    items = []
    for row in chain_rows:
        md = markdown_by_sku.get(row["item_key"], empty_money)
        display_state = md["display_state"] or row["state"]
        best_action_tab = classify(md["display_state"], md["is_markdown_candidate"], md["open_po"])
        store_size = store_sizes.get(row["vertical_id"], 0.0)
        items.append(
            {
                "sku_id": row["item_key"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "category_id": row["category_id"],
                "category_label": row["category_name"],
                "brand": row["brand"],
                "vendor": row["vendor_account"],
                "state": display_state,
                "severity_rank": STATE_ORDER.index(display_state)
                if display_state in STATE_ORDER
                else len(STATE_ORDER),
                "is_markdown_candidate": md["is_markdown_candidate"],
                "position": _float(row["position_qty"]),
                "rop": _float(row["rop_qty"]),
                "max": _float(row["max_qty"]),
                "dos": _float(row["days_cover"]),
                "ads": _float(row["ads"]),
                "price": _float(row["unit_price"]),
                "inv_value": _float(row["inventory_value"]),
                "at_risk_value": round(md["at_risk_value"], 2),
                "recoverable_value": round(md["recoverable_value"], 2),
                "write_off_value": round(md["write_off_value"], 2),
                "expiry_units": _float(row["expiry_units"]),
                "shelf_life_days": _float(row["shelf_life_days"]),
                "is_perishable": bool(row["is_perishable"]),
                "perishable": "Y" if row["is_perishable"] else "N",
                "growth": _float(row["growth_index"]),
                "comp_idx": _float(row["competitor_index"]),
                "elasticity": _float(row["elasticity"]),
                "open_po": _float(row["open_po_qty"]),
                "on_hand": _float(row["on_hand_qty"]),
                # What-If cascade inputs the browser engine re-evaluates.
                "base_ads": _float(row["base_ads"]),
                "seasonality": _float(row["seasonality_index"]),
                "store_size": store_size,
                "total_store_size": store_size,
                "stock_factor": _float(row["stock_factor"]),
                "onhand_days": _float(row["onhand_days"]),
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_depth": _float(row["cannibalisation_pct"]),
                # The designated trade agreement's lead time, not
                # dim_item.lead_time_days -- see the lead_days query below.
                "lead_days": lead_days.get(row["item_key"], 0.0),
                "safety_days": _float(row["safety_days"]),
                "best_action_tab": best_action_tab,
                "recommendation": RECOMMENDATION_BY_TAB.get(best_action_tab, "Hold price"),
            }
        )
    return items


def build_stores(store_money_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-store aggregates for the dimension charts. GROSS figures: they sum
    local pockets of risk and will exceed the chain-net headline (A5 spec
    section 11) -- intentional, not a reconciliation bug.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for row in store_money_rows:
        store_id = row["store_key"]
        bucket = grouped.get(store_id)
        if bucket is None:
            bucket = grouped[store_id] = {
                "store_id": store_id,
                "name": row["store_name"],
                "vertical_id": row["store_vertical_id"],
                "cluster": row["cluster"],
                "channel": row["channel"],
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
        bucket["at_risk_value"] += row["at_risk"]
        # f21-inventory-value: ROUND(position * price). Trivial enough not to
        # round-trip through the expression engine for every one of 16k rows.
        bucket["inv_value"] += _float(row["position_qty"]) * _float(row["price"])

    return sorted(grouped.values(), key=lambda row: row["store_id"])


def build_reference(items: list[dict[str, Any]], legal_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Avg markdown depth per vertical, weighted by candidate at-risk value.

    No `retail.agent_kpi_reference` row exists for this agent (the seeder's
    `build_agent_kpi_reference` only wires agents 1-4), so this is computed
    from the state-based depth table f14's own expression states inline
    (Expiry 40%, Overstock 25%, Slow-mover 30%), the same three constants
    the fixture's `avg_depth_pct` was standing in for as reference-only
    context. `items` here is the FULL, unscoped population, matching how
    `agent_kpi_reference` is never scoped either.
    """
    label_by_vertical = {row["value"]: row["label"] for row in legal_entities}
    depth_by_state = {"Expiry": 0.4, "Overstock": 0.25, "Slow-mover": 0.3}

    totals: dict[str, list[float]] = {}
    for item in items:
        if not item["is_markdown_candidate"]:
            continue
        weight = item["at_risk_value"]
        depth = depth_by_state.get(item["state"])
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


def _designated_lead_times(connection: Any) -> dict[str, float]:
    """Vendor lead time per item, from the DESIGNATED trade agreement.

    NOT dim_item.lead_time_days -- audit fix T-05/T-06 ("ROP pakai lead
    statis di SKU master, bukan lead vendor"). See
    scripts/build_pricing_markdown_fixture.py::designated_lead_times() for
    the full account; this is the same SUMIFS, in SQL.
    """
    rows = _rows(
        connection,
        f"""
        SELECT item_key, sum(lead_time_days) AS lead_days
        FROM {TRADE_AGREEMENT}
        WHERE is_designated = 1
        GROUP BY item_key
        """,
    )
    return {row["item_key"]: _float(row["lead_days"]) for row in rows}


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()

    with get_engine().connect() as connection:
        # UNSCOPED on purpose -- see the module docstring. Every store row
        # chain-wide is needed to get any one SKU's own money figures right.
        store_rows = _rows(
            connection,
            f"""
            SELECT f.item_key, f.store_key, f.state, f.position_qty, f.max_qty,
                   f.ads, f.open_po_qty,
                   i.price AS price, i.shelf_life_days, i.elasticity,
                   s.name AS store_name, s.vertical_id AS store_vertical_id,
                   s.cluster, s.channel
            FROM {STORE_FACT} f
            JOIN {ITEM} i ON i.item_id = f.item_key
            JOIN {STORE_DIM} s ON s.store_id = f.store_key
            WHERE f.cal_date = :day
            """,
            {"day": SNAPSHOT_DATE},
        )
        store_money_rows = [{**row, **_store_money(row)} for row in store_rows]
        markdown_by_sku = aggregate_markdown_by_sku(store_money_rows)
        stores_rollup = build_stores(store_money_rows)

        # UNSCOPED too -- the reference block and the depth-by-vertical
        # weighting need the full population, same as agent_kpi_reference is
        # never scoped for the sibling boards. Scope is applied in Python
        # below, once, to the item list actually returned.
        chain_rows = _rows(
            connection,
            f"""
            SELECT c.item_key, c.ads, c.position_qty, c.rop_qty, c.max_qty,
                   c.days_cover, c.state, c.on_hand_qty, c.open_po_qty,
                   c.unit_price, c.inventory_value, c.expiry_units,
                   i.name, i.vertical_id, i.category_id, i.category_name,
                   i.brand, i.vendor_account, i.shelf_life_days, i.is_perishable,
                   i.growth_index, i.competitor_index, i.elasticity, i.base_ads,
                   i.seasonality_index, i.stock_factor, i.onhand_days,
                   i.is_promo_eligible, i.cannibalisation_pct, i.safety_days
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            JOIN {VERTICAL} vt ON vt.vertical_id = i.vertical_id
            WHERE c.cal_date = :day
            ORDER BY vt.sort_order, c.item_key
            """,
            {"day": SNAPSHOT_DATE},
        )
        lead_days = _designated_lead_times(connection)
        store_sizes = chain_store_size(connection)
        options = filter_options(connection)

    all_items = build_items(chain_rows, markdown_by_sku, lead_days, store_sizes)
    reference = build_reference(all_items, options["legal_entities"])

    items = [
        item
        for item in all_items
        if (not scope.legal_entity_id or item["vertical_id"] == scope.legal_entity_id)
        and (not scope.category_group or item["category_id"] == scope.category_group)
    ]
    stores = [
        store
        for store in stores_rollup
        if not scope.legal_entity_id or store["vertical_id"] == scope.legal_entity_id
    ]

    return {
        **envelope(AGENT_ID, NOTE),
        "formulas": formulas(ENGINE_FORMULAS),
        "filter_options": {
            key: options[key] for key in ("legal_entities", "categories", "stores", "states")
        },
        "items": items,
        "stores": stores,
        "reference_by_vertical": reference,
    }


__all__ = ["SUPPORTED_FILTERS", "build"]
