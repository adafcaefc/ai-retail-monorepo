"""Agent 6 · Assortment Optimization — the rows, read from Azure SQL.

Returns the same shape `scripts/build_assortment_optimization_fixture.py`
writes, so the board's selectors run over it unchanged. The route does NOT
return a finished dashboard: `selectors.js` derives every KPI, dimension
breakdown, quadrant and action preview from these rows, and a second
implementation in Python would have to be kept in step with it forever.

TWO GRAINS, AND THEY ARE NOT INTERCHANGEABLE
`items` is chain-net, from `fact_inventory_chain_daily` -- the workbook's
ENGINE sheet, which is not the per-store grid rolled up. `stores` and
`by_state_value` aggregate `fact_inventory_daily` and are GROSS: they sum
local pockets and will not reconcile 1:1 with the chain-level headline. A6
spec section 11 says so, and the board labels it rather than reconciling it
away.

WHY THE QUARTILES ARE COMPUTED HERE AND NOT IN SQL
`classify` needs P25/P75 over the whole 800-row population, and the cutoffs
must be the ones the browser re-classifies against. Computing them in SQL
would put the boundary in two places -- a `PERCENTILE_CONT` here and a
`percentile()` there -- and the one SKU sitting on a cutoff would flip
between them. This is the fixture builder's own function, run over rows the
database returned.

CONTRIBUTION IS ROUNDED PER ROW BEFORE IT IS SUMMED
`ENGINE_STORE!Contribution/day` is a rounded column, so the workbook's store
total is a sum of rounded values, not a rounded sum. Summing the raw products
instead drifts by up to a few rupiah per store across its 100 SKUs -- small,
but it is the difference between reconciling and nearly reconciling, and the
per-store rollup is one of the things this board is audited on. The
`stores`/`by_state_value` SQL rollups round per row in SQL for this reason;
the item-grain figure below evaluates the same rule (f15) through the
catalogue instead, so both sides state one rounding decision rather than two.

THE PRODUCTIVITY CHAIN IS DERIVED FROM f01, NOT READ
Every other retail board reads its figures from the warehouse. This one
derives ADS through the catalogue's own evaluator, and the fixture builder
does the same, for a concrete reason: the delist/grow verdict is a comparison
against percentile cutoffs, and the browser re-runs f01 the moment a slider
moves. The chain table's stored `ads` differs from f01 re-evaluated over the
same inputs by about 1e-5 relative -- invisible in any displayed figure, and
decisive for the SKU sitting exactly on the P75 cutoff, which flips grow/hold
between the two. Both sides through one evaluator removes the class of
disagreement instead of tuning a tolerance around it.
"""

from __future__ import annotations

from typing import Any

from src.formulas.expression import evaluate, parse
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    SCHEMA,
    SNAPSHOT_DATE,
    STATE_ORDER,
    SUPPORTED_FILTERS,
    _rows,
    _scope_clause,
    agent_reference,
    chain_store_size,
    envelope,
    filter_options,
    formulas,
    get_engine,
)

AGENT_ID = "retail.assortment_optimization"

# The nine expressions A6's What-If engine evaluates. It refuses to start
# without all of them, so the board fails at load rather than at the first
# slider drag.
ENGINE_FORMULAS = (
    "f01-ads-per-store",
    "f03-open-po-per-store",
    "f04-position",
    "f05-rop",
    "f06-maximum-inventory",
    "f07-inventory-state",
    "f12-at-risk-value",
    "f15-contribution-per-day",
    "f20-days-of-supply",
    "f21-inventory-value",
)

# A6 spec section 2: these states are delist candidates on state alone.
DELIST_STATES = frozenset({"Slow-mover", "Overstock", "Expiry"})

# Vendor and category concentration have no constant: `assign_best_action_tabs`
# compares each group's delist rate with the chain's own, so the cutoff is a
# fact about the population in scope rather than a number to keep in step.

NOTE = (
    "Workbook demonstration data, not a live ERP position. Delist/grow "
    "classification, GMROI, tail share and capital freed are computed live "
    "from the chain and store fact tables against chain-wide quartiles, not "
    "read from the A6 sheet's own B:F cells, which a prior audit found to "
    "hold stale hardcoded values."
)


def _float(value: Any) -> float:
    """SQL Server DECIMAL arrives as Decimal; the payload is JSON."""
    return float(value) if value is not None else 0.0


def percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolated percentile over an already-sorted list.

    Character for character the fixture builder's, so the two agree on the
    SKU that sits exactly on a cutoff. A different interpolation rule here
    would move that SKU between `delist` and `hold` depending on which path
    served the board.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct
    lower = int(k)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = k - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


def build_items(
    rows: list[dict],
    contribution: dict[str, float],
    store_size: dict[str, float],
    asts: dict[str, Any],
) -> list[dict]:
    """One row per SKU at chain-net level, every predicate pre-resolved.

    Ordered by vertical, then by contribution DESCENDING -- the register opens
    on what earns most within each book, which is the order the fixture ships
    and the order the board's own tests assert.
    """
    ordered = sorted(
        rows,
        key=lambda row: (
            row["sort_order"],
            -contribution.get(row["item_key"], 0.0),
        ),
    )

    items = []
    for row in ordered:
        state = row["state"]
        price = _float(row["unit_price"])
        margin_pct = _float(row["margin_pct"])
        inv_value = _float(row["inventory_value"])

        # f01 at baseline levers -- the same expression, through the same
        # evaluator, that `engine.js` runs in the browser.
        arch_horizon_factor = _float(row.get("arch_horizon_factor", 1.0)) or 1.0
        ads = evaluate(
            asts["f01-ads-per-store"],
            {
                "base_ads": _float(row["base_ads"]),
                "seasonality": _float(row["seasonality_index"]),
                "arch_horizon_factor": arch_horizon_factor,
                "store_size": store_size[row["vertical_id"]],
                "demand_lever": 0,
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_lever": 0,
                "promo_depth": _float(row["cannibalisation_pct"]),
            },
        )

        # The productivity chain, in the engine's own order of operations.
        weekly_gmv = ads * 7 * price
        margin_rp = weekly_gmv * margin_pct
        gmroi = (margin_rp / inv_value) if inv_value else 0.0

        items.append(
            {
                "sku_id": row["item_key"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "category_id": row["category_id"],
                "category_label": row["category_name"],
                "brand": row["brand"],
                "vendor": row["vendor_short"] or "",
                "state": state,
                "severity_rank": (
                    STATE_ORDER.index(state) if state in STATE_ORDER else len(STATE_ORDER)
                ),
                "position": _float(row["position_qty"]),
                "price": price,
                "inv_value": inv_value,
                "weekly_gmv": weekly_gmv,
                "margin_rp": margin_rp,
                "funding_rp": _float(row["funding_rp"]),
                # `gmroi` stays unrounded -- it has no catalogue formula. Not
                # so for `contribution_per_day`: it was hand-typed unrounded
                # to avoid moving the percentile boundary out from under the
                # browser engine, but the actual risk was never rounding
                # itself -- it was rounding on one side and not the other.
                # f15 rounds; evaluating it here and in `engine.js` from the
                # same catalogue expression means both sides agree by
                # construction, at whatever precision f15 states.
                "gmroi": gmroi,
                "contribution_per_day": evaluate(
                    asts["f15-contribution-per-day"],
                    {"ads": ads, "price": price, "margin_pct": margin_pct},
                ),
                "growth": _float(row["growth_index"]),
                "dos": _float(row["days_cover"]),
                "ads": ads,
                "rop": _float(row["rop_qty"]),
                "max": _float(row["max_qty"]),
                "open_po": _float(row["open_po_qty"]),
                "on_hand": _float(row["on_hand_qty"]),
                "shelf_life_days": _float(row["shelf_life_days"]),
                "perishable": "Y" if row["is_perishable"] else "N",
                # -- What-If parameters, never answers ------------------
                "base_ads": _float(row["base_ads"]),
                "seasonality": _float(row["seasonality_index"]),
                "arch_horizon_factor": arch_horizon_factor,
                # The vertical's total size index, not one store's: a
                # chain-net row already covers every store.
                "store_size": store_size[row["vertical_id"]],
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_depth": _float(row["cannibalisation_pct"]),
                # `dim_item.lead_time_days`, which is the column this
                # workbook's ROP is computed from. The designated trade
                # agreement carries a different term for all 800 items, and
                # the browser recomputes ROP from this field on every lever
                # move -- feeding it the other column opens the board at one
                # ROP and jumps to another the moment a slider is touched.
                "lead_days": _float(row["lead_time_days"]),
                "safety_days": _float(row["safety_days"]),
                "margin_pct": margin_pct,
            }
        )
    return items


def classify(items: list[dict[str, Any]]) -> dict[str, float]:
    """Add `classification` and `is_tail` to every item, in place.

    Delist uses chain-wide P25: any state can be a delist candidate on low
    GMROI or tail contribution alone, per A6 spec section 2's plain OR. Grow
    uses P75 WITHIN THE HEALTHY SUBSET rather than chain-wide, because in this
    dataset high GMROI concentrates in Stockout/Low SKUs -- fast movers
    running short -- so a chain-wide P75 intersected with `state == Healthy`
    is empty. Grow candidates compete against their Healthy peers.
    """
    gmroi_sorted = sorted(i["gmroi"] for i in items)
    contribution_sorted = sorted(i["contribution_per_day"] for i in items)
    p25_gmroi = percentile(gmroi_sorted, 0.25)
    p25_contribution = percentile(contribution_sorted, 0.25)

    healthy_gmroi = sorted(i["gmroi"] for i in items if i["state"] == "Healthy")
    healthy_contribution = sorted(
        i["contribution_per_day"] for i in items if i["state"] == "Healthy"
    )
    p75_gmroi_healthy = percentile(healthy_gmroi, 0.75)
    p75_contribution_healthy = percentile(healthy_contribution, 0.75)

    for item in items:
        is_tail = item["contribution_per_day"] <= p25_contribution
        is_delist = (
            item["state"] in DELIST_STATES
            or item["gmroi"] <= p25_gmroi
            or is_tail
        )
        is_grow = (
            item["state"] == "Healthy"
            and item["contribution_per_day"] >= p75_contribution_healthy
            and item["gmroi"] >= p75_gmroi_healthy
            and item["growth"] >= 1.0
        )
        item["is_tail"] = is_tail
        item["classification"] = (
            "grow" if (is_grow and not is_delist) else ("delist" if is_delist else "hold")
        )

    return {
        "p25_gmroi_chain": p25_gmroi,
        "p25_contribution_chain": p25_contribution,
        "p75_gmroi_healthy": p75_gmroi_healthy,
        "p75_contribution_healthy": p75_contribution_healthy,
    }


def delist_share(items: list[dict[str, Any]], key: str) -> dict[str, float]:
    """Each group's delist rate: delist SKUs over that group's whole range."""
    totals: dict[str, int] = {}
    delisted: dict[str, int] = {}
    for item in items:
        group = item[key]
        totals[group] = totals.get(group, 0) + 1
        if item["classification"] == "delist":
            delisted[group] = delisted.get(group, 0) + 1
    return {g: delisted.get(g, 0) / n for g, n in totals.items() if n}


def assign_best_action_tabs(items: list[dict[str, Any]]) -> None:
    """Add `best_action_tab` and `recommendation`, in place.

    Grow Winners is the grow population. The delist population splits by what
    the decision actually IS: a vendor over-represented in the delist list is a
    supplier conversation, a category over-represented is a planogram one, and
    what is left is line-by-line.

    OVER-REPRESENTED AGAINST THE CHAIN, NOT AGAINST A STORED NUMBER. The
    comparison is each group's delist rate against the chain's own delist rate,
    so the split re-derives itself for every scope and every lever position and
    there is no constant to keep in step across the four places this rule
    lives.

    This replaced a fixed count ("a vendor with >= 8 delist SKUs"), which does
    not survive contact with this range: eight vendors carry 33 to 75 delist
    SKUs each, so every vendor cleared it and all 404 delist rows landed in
    Vendor Review, leaving Delist Tail and Rebalance Space empty on screen. An
    absolute count cannot express concentration -- only a share can.
    """
    if not items:
        return

    chain_rate = sum(1 for i in items if i["classification"] == "delist") / len(items)
    vendor_rate = delist_share(items, "vendor")
    category_rate = delist_share(items, "category_id")

    for item in items:
        if item["classification"] == "grow":
            item["best_action_tab"] = "grow_winners"
            item["recommendation"] = "Grow range / add space / expand stores"
        elif item["classification"] == "delist":
            if vendor_rate.get(item["vendor"], 0.0) > chain_rate:
                item["best_action_tab"] = "vendor_brand_review"
                item["recommendation"] = "Vendor or brand review"
            elif category_rate.get(item["category_id"], 0.0) > chain_rate:
                item["best_action_tab"] = "rebalance_space"
                item["recommendation"] = "Rationalize tail and rebalance category"
            else:
                item["best_action_tab"] = "delist_tail"
                item["recommendation"] = "Delist / reduce facing / stop reorder"
        else:
            item["best_action_tab"] = None
            item["recommendation"] = "Hold assortment"


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()
    where, params = _scope_clause(scope, "i.vertical_id", "i.category_id")
    params["day"] = SNAPSHOT_DATE

    with get_engine().connect() as connection:
        chain = _rows(
            connection,
            f"""
            SELECT c.item_key, c.ads, c.on_hand_qty, c.open_po_qty,
                   c.position_qty, c.rop_qty, c.max_qty, c.days_cover,
                   c.state, c.unit_price, c.inventory_value, c.funding_rp,
                   i.name, i.vertical_id, i.category_id, i.category_name,
                   i.brand, i.is_perishable, i.shelf_life_days, i.base_ads,
                   i.seasonality_index, i.lead_time_days, i.safety_days,
                   i.growth_index, i.is_promo_eligible, i.cannibalisation_pct,
                   i.margin_pct,
                   vt.sort_order,
                   v.vendor_short
            FROM {SCHEMA}.fact_inventory_chain_daily c
            JOIN {SCHEMA}.dim_item i ON i.item_id = c.item_key
            JOIN {SCHEMA}.dim_vertical vt ON vt.vertical_id = i.vertical_id
            LEFT JOIN {SCHEMA}.dim_vendor v ON v.vendor_account = i.vendor_account
            WHERE c.cal_date = :day{where}
            """,
            params,
        )

        # Contribution per SKU, summed from that SKU's store rows. Rounded per
        # row first -- see the module docstring.
        contribution_rows = _rows(
            connection,
            f"""
            SELECT f.item_key,
                   sum(round(f.ads * i.price * i.margin_pct, 0)) AS contribution
            FROM {SCHEMA}.fact_inventory_daily f
            JOIN {SCHEMA}.dim_item i ON i.item_id = f.item_key
            WHERE f.cal_date = :day{where}
            GROUP BY f.item_key
            """,
            params,
        )

        stores = _rows(
            connection,
            f"""
            SELECT s.store_id, s.name, s.vertical_id, s.cluster, s.channel,
                   count(*)                                    AS sku_count,
                   sum(round(f.ads * i.price * i.margin_pct, 0))
                                                               AS contribution_per_day,
                   coalesce(sum(f.position_qty * i.price), 0)  AS inv_value
            FROM {SCHEMA}.fact_inventory_daily f
            JOIN {SCHEMA}.dim_store s ON s.store_id = f.store_key
            JOIN {SCHEMA}.dim_item  i ON i.item_id  = f.item_key
            WHERE f.cal_date = :day{where}
            GROUP BY s.store_id, s.name, s.vertical_id, s.cluster, s.channel
            ORDER BY s.store_id
            """,
            params,
        )

        state_value = _rows(
            connection,
            f"""
            SELECT f.state, coalesce(sum(f.position_qty * i.price), 0) AS inv_value
            FROM {SCHEMA}.fact_inventory_daily f
            JOIN {SCHEMA}.dim_item i ON i.item_id = f.item_key
            WHERE f.cal_date = :day{where}
            GROUP BY f.state
            """,
            params,
        )

        engine_formulas = formulas(ENGINE_FORMULAS)
        options = filter_options(connection)
        reference = agent_reference(connection, AGENT_ID)
        store_size = chain_store_size(connection)

    contribution = {
        row["item_key"]: _float(row["contribution"]) for row in contribution_rows
    }

    asts = {name: parse(text) for name, text in engine_formulas.items()}
    items = build_items(chain, contribution, store_size, asts)
    thresholds = classify(items)
    assign_best_action_tabs(items)
    state_map = {row["state"]: _float(row["inv_value"]) for row in state_value}

    return {
        **envelope(AGENT_ID, NOTE),
        "classification_thresholds": thresholds,
        "formulas": engine_formulas,
        "filter_options": options,
        "items": items,
        "stores": [
            {
                "store_id": row["store_id"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "cluster": row["cluster"],
                "channel": row["channel"],
                "sku_count": row["sku_count"],
                "contribution_per_day": _float(row["contribution_per_day"]),
                "inv_value": _float(row["inv_value"]),
            }
            for row in stores
        ],
        "by_state_value": [
            {"state": state, "value": state_map[state]}
            for state in STATE_ORDER
            if state in state_map
        ],
        "reference_by_vertical": reference,
    }


__all__ = ["AGENT_ID", "SUPPORTED_FILTERS", "build"]
