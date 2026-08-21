"""Agent 5 · Pricing & Markdown — the rows the board aggregates.

Returns the shape `scripts/build_pricing_markdown_fixture.py` ships, not the
pre-aggregated `kpis/views/side` envelope Promotion Effectiveness returns: the
board's own selectors (`frontend/.../pricing_markdown/data/selectors.js`)
expect semi-raw `items`/`stores`/`formulas`/`reference_by_vertical` and do the
KPI/chart aggregation themselves, same as the fixture. See
`retail/common/warehouse.py` for why the aggregation stays in the browser.

ONE GRAIN, LIKE THE FIXTURE BUILDER (NOT TWO ANY MORE)
-------------------------------------------------------
`items` is one row per `fact_inventory_daily` record (SKU x store) -- the A5
sheet's own grain, matching `scripts/build_pricing_markdown_fixture.py`'s own
rewrite to this same grain. This used to roll the store fact up to one row
per chain-net SKU by default (a SKU counted as a markdown candidate if ANY of
its stores showed a candidate state), which undercounts: the workbook's own
"Markdown candidates" is a count of store-level rows in {Expiry, Overstock,
Slow-mover} (1,638), not a count of SKUs that merely touch one of those
states somewhere among their ~20 stores (170). `legal_entity_id`,
`category_group` and `store_id` are now all the same kind of filter --
intrinsic fields on this already-per-store row -- so `store_id` no longer
needs its own recompute path; it just narrows rows, exactly like the other
two.

`fact_inventory_daily` does not store the two markdown-specific columns
migration 004 added (`markdown_at_risk_value`/`markdown_recoverable`)
populated -- the seeder never wrote them -- so this module computes
at-risk/recoverable/inventory-value/expiry-units itself, per row, at request
time, via the same f12/f21/f22/f23/f14 formulas the browser's What-If engine
runs, read from `retail.formula` (never hand-restated).

WHY `is_mock` STAYS TRUE
See `warehouse.envelope()`: rows are real, but they are one workbook snapshot
day, not a live ERP position. That does not change when Postgres replaces the
checked-in fixture as the source, so the board's "Workbook data" label is
accurate before and after this module exists.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.formulas import repository
from src.formulas.expression import evaluate, parse
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    HORIZON_COVERAGE,
    SCHEMA,
    SNAPSHOT_DATE,
    STATE_ORDER,
    SUPPORTED_FILTERS as _BASE_SUPPORTED_FILTERS,
    _rows,
    envelope,
    filter_options,
    formulas,
    get_engine,
)

# store_id is this agent's own addition on top of the pair every Retail board
# shares (legal_entity_id/category_group). Now that `items` is unconditionally
# store grain, all three are the same kind of filter -- an intrinsic field on
# each row -- but this stays a local override rather than moving into
# warehouse.SUPPORTED_FILTERS, which promotion_effectiveness also imports and
# still only honours store_id client-side.
SUPPORTED_FILTERS: frozenset[str] = _BASE_SUPPORTED_FILTERS | {"store_id"}

AGENT_ID = "retail.pricing_markdown"

STORE_FACT = f"{SCHEMA}.fact_inventory_daily"
ITEM = f"{SCHEMA}.dim_item"
STORE_DIM = f"{SCHEMA}.dim_store"
VERTICAL = f"{SCHEMA}.dim_vertical"

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

# legal_entity_id and category_group narrow the returned `items` by row;
# store_id narrows it by row AND recomputes each item's state/candidacy/money
# at that one store's grain (see `build()` and the module docstring). `state`
# stays client-side only for `items` (frontend/.../data/selectors.js's
# scopeItems), since it labels a row post-hoc rather than selecting which
# stores feed its money.
# promotion_effectiveness still treats store_id as client-side-only -- this
# agent is the one exception, hence the local SUPPORTED_FILTERS override
# above rather than changing the pair every Retail board shares.
#
# The `stores` rollup (by_store/by_cluster/by_channel) is a separate concern
# from `items` above: category_group and state ALSO narrow it server-side, in
# `build()`, because those two fields have already been summed away across
# every SKU at a store by the time a per-store row exists -- unlike store_id,
# which matches an intrinsic field on the pre-aggregated row and so can still
# be (and is) filtered client-side by scopeStores(). This only applies when
# reading from the live API; the bundled fixture (offline/standalone builds)
# has no request-time recompute step, so it keeps showing each store's full
# all-category/all-state total for those three charts -- the same documented
# gap store_id already has on that path. `by_legal_entity` doesn't read this
# `stores` rollup at all -- selectors.js's computeByLegalEntity sums `items`'
# own at_risk_gross instead, so it always reflects every filter client-side.

# Weeks in `synthetic.markdown_ladder_store_sku_16w` -- see that table's
# migration (sql/retail/012_...) and generator (scripts/generate_synthetic_
# markdown_ladder_16w.py) for what the two lines represent. Read here as a
# per-vertical aggregate, unscoped by legal_entity_id/category_group/store_id
# the way `reference` below is unscoped -- it is a benchmark line, not a
# figure a filter narrows.
LADDER_WEEKS = 16

_MONEY_FORMULA_IDS = (
    "f12-at-risk-value",
    "f23-markdown-at-risk-gross",
    "f14-recoverable-at-risk-value",
    "f21-inventory-value",
    "f22-expiry-units",
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
    inventory_value = evaluate(asts["f21-inventory-value"], {"position": position, "price": price})
    expiry_units = evaluate(
        asts["f22-expiry-units"],
        {
            "perishable": "Y" if row["is_perishable"] else "N",
            "position": position,
            "ads": _float(row["ads"]),
            "shelf_life_days": _float(row["shelf_life_days"]),
        },
    )
    return {
        "at_risk": at_risk, "gross": gross, "recoverable": recoverable,
        "inventory_value": inventory_value, "expiry_units": expiry_units,
    }


def classify(state: str | None, is_candidate: bool, open_po: float) -> str | None:
    if not is_candidate or not state:
        return None
    if state == "Overstock":
        return "suppress_reorder" if open_po > 0 else "overstock_clearance"
    return BEST_ACTION_BY_STATE.get(state)


def build_items(store_money_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per `fact_inventory_daily` record (SKU x store) -- this board's
    real grain, matching `scripts/build_pricing_markdown_fixture.py`'s own
    rewrite to the same grain. No SKU-level rollup: candidacy, state, and
    every money figure are this row's own, already merged in via
    `_store_money`. `lead_time_days` comes straight off the `dim_item` join
    in `build()`'s query, same as `safety_days`/`shelf_life_days` below --
    see the removed `_designated_lead_times()` for why that used to be a
    separate query against the wrong table.
    """
    items = []
    for row in store_money_rows:
        state = row["state"]
        is_candidate = state in CANDIDATE_STATES
        open_po = _float(row["open_po_qty"])
        best_action_tab = classify(state, is_candidate, open_po)
        items.append(
            {
                "sku_id": row["item_key"],
                "store_id": row["store_key"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "category_id": row["category_id"],
                "category_label": row["category_name"],
                "brand": row["brand"],
                "vendor": row["vendor_account"],
                "cluster": row["cluster"],
                "channel": row["channel"],
                "state": state,
                "severity_rank": STATE_ORDER.index(state) if state in STATE_ORDER else len(STATE_ORDER),
                "is_markdown_candidate": is_candidate,
                "position": _float(row["position_qty"]),
                "rop": _float(row["rop_qty"]),
                "max": _float(row["max_qty"]),
                "dos": _float(row["days_cover"]),
                "ads": _float(row["ads"]),
                "price": _float(row["price"]),
                "inv_value": round(row["inventory_value"], 2),
                "at_risk_value": round(row["at_risk"], 2),
                # f23's own at-risk-portion output -- NOT at_risk_value (f12,
                # the row's full position x price for any non-Healthy
                # state). avg_depth_pct's weight, both here and in
                # build_reference() below -- at_risk_value overstates it
                # 3x-20x per row and must not be used as a depth weight. See
                # the matching fix in scripts/build_pricing_markdown_fixture.py.
                "at_risk_gross": round(row["gross"], 2),
                "recoverable_value": round(row["recoverable"], 2),
                "write_off_value": round(max(0.0, row["at_risk"] - row["recoverable"]), 2),
                "expiry_units": round(row["expiry_units"], 2),
                "shelf_life_days": _float(row["shelf_life_days"]),
                "is_perishable": bool(row["is_perishable"]),
                "perishable": "Y" if row["is_perishable"] else "N",
                "growth": _float(row["growth_index"]),
                "comp_idx": _float(row["competitor_index"]),
                "elasticity": _float(row["elasticity"]),
                "open_po": open_po,
                "on_hand": _float(row["on_hand_qty"]),
                # What-If cascade inputs the browser engine re-evaluates. This
                # row already IS one store, so store_size is that store's own
                # size_index (not the vertical total a chain-net item would
                # need), and f03's ratio is 1 at rest.
                "base_ads": _float(row["base_ads"]),
                "seasonality": _float(row["seasonality_index"]),
                "arch_horizon_factor": _float(row["arch_horizon_factor"]),
                "store_size": _float(row["size_index"]),
                "total_store_size": _float(row["size_index"]),
                "horizon_coverage": HORIZON_COVERAGE,
                "stock_factor": _float(row["stock_factor"]),
                "onhand_days": _float(row["onhand_days"]),
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_depth": _float(row["cannibalisation_pct"]),
                # dim_item.lead_time_days, seeded from SKU_Master.lead_d --
                # see build_items()'s own docstring for why.
                "lead_days": _float(row["lead_time_days"]),
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
    """Avg markdown depth per vertical, weighted by candidate at-risk GROSS.

    No `retail.agent_kpi_reference` row exists for this agent (the seeder's
    `build_agent_kpi_reference` only wires agents 1-4), so this is computed
    from the state-based depth table f14's own expression states inline
    (Expiry 40%, Overstock 25%, Slow-mover 30%), the same three constants
    the fixture's `avg_depth_pct` was standing in for as reference-only
    context. `items` here is the FULL, unscoped population, matching how
    `agent_kpi_reference` is never scoped either.

    The weight is `at_risk_gross` (f23's own at-risk-portion output), not
    `at_risk_value` (f12's full position value for any non-Healthy row) --
    the latter overstates the weight 3x-20x per row and was the entire
    source of a 34%-vs-35% gap against a from-scratch, hand-checked
    recompute of this exact figure. See build_items()'s `_store_money`.
    """
    label_by_vertical = {row["value"]: row["label"] for row in legal_entities}
    depth_by_state = {"Expiry": 0.4, "Overstock": 0.25, "Slow-mover": 0.3}

    totals: dict[str, list[float]] = {}
    for item in items:
        if not item["is_markdown_candidate"]:
            continue
        weight = item["at_risk_gross"]
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


def _ladder_by_vertical(connection: Any) -> list[dict[str, Any]]:
    """The 32-week (16 back, 16 forward) markdown-ladder-vs-no-action
    projection, per vertical.

    Reads `synthetic.markdown_ladder_store_sku_16w` if it exists (migration
    012) -- a fabricated, gate-checked projection from today's real
    at_risk_value/write_off_value, NOT a measured history on either side (at-
    risk value has no real past to record; see that table's own migration
    for why the history side is modelled the same way the forward side
    already was). Guarded the same way replenishment/dashboard.py guards
    `synthetic.inbound_store_sku_16w`: an environment that has not run
    migration 012 simply gets an empty list back and the chart does not
    render, rather than the request failing. The history columns (migration
    013) are guarded separately -- an environment with 012 but not yet 013
    gets `history_no_action`/`history_ladder` as all-zero rather than a
    failed query.

    Aggregated to (sku_id, store_id) -> vertical here, in SQL, rather than
    shipped at the raw 16,000-row grain: the chart draws one pair of lines
    per scope, not one per SKU, so there is nothing for a client-side
    selector to do with the per-row detail that summing here doesn't already
    do -- and shipping 64 extra numbers on all 16,000 items would bloat the
    payload for data nothing reads at that grain.
    """
    has_table = connection.execute(
        text("SELECT OBJECT_ID(N'synthetic.markdown_ladder_store_sku_16w', N'U')")
    ).scalar()
    if has_table is None:
        return []

    has_history = connection.execute(
        text("SELECT COL_LENGTH(N'synthetic.markdown_ladder_store_sku_16w', N'no_action_hist_w1')")
    ).scalar()

    no_action_cols = ", ".join(f"sum(m.no_action_w{n}) AS no_action_w{n}" for n in range(1, LADDER_WEEKS + 1))
    ladder_cols = ", ".join(f"sum(m.ladder_w{n}) AS ladder_w{n}" for n in range(1, LADDER_WEEKS + 1))
    select_cols = f"i.vertical_id, {no_action_cols}, {ladder_cols}"
    if has_history is not None:
        hist_no_action_cols = ", ".join(
            f"sum(m.no_action_hist_w{n}) AS no_action_hist_w{n}" for n in range(1, LADDER_WEEKS + 1)
        )
        hist_ladder_cols = ", ".join(
            f"sum(m.ladder_hist_w{n}) AS ladder_hist_w{n}" for n in range(1, LADDER_WEEKS + 1)
        )
        select_cols += f", {hist_no_action_cols}, {hist_ladder_cols}"

    rows = _rows(
        connection,
        f"""
        SELECT {select_cols}
        FROM synthetic.markdown_ladder_store_sku_16w m
        JOIN {ITEM} i ON i.item_id = m.sku_id
        GROUP BY i.vertical_id
        """,
        {},
    )
    return [
        {
            "legal_entity_id": row["vertical_id"],
            "no_action": [_float(row[f"no_action_w{n}"]) for n in range(1, LADDER_WEEKS + 1)],
            "ladder": [_float(row[f"ladder_w{n}"]) for n in range(1, LADDER_WEEKS + 1)],
            "history_no_action": (
                [_float(row[f"no_action_hist_w{n}"]) for n in range(1, LADDER_WEEKS + 1)]
                if has_history is not None
                else [0.0] * LADDER_WEEKS
            ),
            "history_ladder": (
                [_float(row[f"ladder_hist_w{n}"]) for n in range(1, LADDER_WEEKS + 1)]
                if has_history is not None
                else [0.0] * LADDER_WEEKS
            ),
        }
        for row in rows
    ]


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()

    with get_engine().connect() as connection:
        # UNSCOPED in SQL on purpose. Read every store row chain-wide; scope
        # is applied in Python below, once, since `reference` needs the full
        # unscoped population (a benchmark, not a figure any filter narrows)
        # while `items`/`stores` need the scoped one -- both start from this
        # same set.
        store_rows = _rows(
            connection,
            f"""
            SELECT f.item_key, f.store_key, f.state, f.position_qty, f.max_qty,
                   f.rop_qty, f.days_cover, f.on_hand_qty, f.ads, f.open_po_qty,
                   i.name, i.vertical_id, i.category_id, i.category_name,
                   i.brand, i.vendor_account, i.price, i.shelf_life_days,
                   i.is_perishable, i.growth_index, i.competitor_index,
                   i.elasticity, i.base_ads, i.seasonality_index,
                   i.arch_horizon_factor, i.stock_factor, i.onhand_days,
                   i.is_promo_eligible, i.cannibalisation_pct, i.safety_days,
                   i.lead_time_days,
                   s.name AS store_name, s.vertical_id AS store_vertical_id,
                   s.cluster, s.channel, s.size_index
            FROM {STORE_FACT} f
            JOIN {ITEM} i ON i.item_id = f.item_key
            JOIN {STORE_DIM} s ON s.store_id = f.store_key
            JOIN {VERTICAL} vt ON vt.vertical_id = i.vertical_id
            WHERE f.cal_date = :day
            ORDER BY vt.sort_order, f.item_key, f.store_key
            """,
            {"day": SNAPSHOT_DATE},
        )
        store_money_rows = [{**row, **_store_money(row)} for row in store_rows]

        options = filter_options(connection)
        ladder_by_vertical = _ladder_by_vertical(connection)

    all_items = build_items(store_money_rows)
    # Reference stays unscoped: it is a benchmark (avg markdown depth per
    # vertical), not a figure any filter claims to narrow, same as
    # agent_kpi_reference is never scoped for the sibling boards.
    reference = build_reference(all_items, options["legal_entities"])

    items = [
        item
        for item in all_items
        if (not scope.legal_entity_id or item["vertical_id"] == scope.legal_entity_id)
        and (not scope.category_group or item["category_id"] == scope.category_group)
        and (not scope.store_id or item["store_id"] == scope.store_id)
    ]

    # `category_group`/`state` narrow the store rollup here, not client-side:
    # by the time a row reaches `stores_rollup` it has already been summed
    # across every category/state at that store, so there is nothing left
    # for a client-side filter to key on -- unlike `legal_entity_id`, which
    # matches an intrinsic field on the aggregated row and is applied after,
    # alongside `stores` below.
    stores_scoped_rows = store_money_rows
    if scope.category_group:
        stores_scoped_rows = [r for r in stores_scoped_rows if r["category_id"] == scope.category_group]
    if scope.state:
        stores_scoped_rows = [r for r in stores_scoped_rows if r["state"] == scope.state]
    stores_rollup = build_stores(stores_scoped_rows)
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
        # Additive: see _ladder_by_vertical()'s docstring. Empty list on an
        # environment that has not run migration 012 -- nothing else here
        # changes shape or values when that happens.
        "ladder_by_vertical": ladder_by_vertical,
    }


__all__ = ["SUPPORTED_FILTERS", "build"]
