"""Agent 2 · Inventory Risk — the rows, read from Postgres.

Returns the same shape `scripts/build_inventory_risk_fixture.py` writes, so the
board's selectors run over it unchanged. See `retail/common/warehouse.py` for
why the aggregation stays in the browser.

`items` is ENGINE_STORE grain: one row per SKU x store, 16,000 of them, the
same grid the workbook's own dropdown filters and the Formula Manager calls its
primary source. It was chain-net (`fact_inventory_chain_daily`, 800 netted
rows) until the KPI cards were found to be answering a question nobody asked --
"how many SKUs are slow-moving once surplus in one store cancels shortage in
another" -- and reading 37 slow movers where the grid holds 75.

`stores` is aggregated from the same `fact_inventory_daily` and its totals are
GROSS. That is no longer a second grain, just a second shape: with `items` at
store grain the two finally reconcile, where before they could not.

One thing does NOT reconcile, by design. The workbook's `A2 Inventory Risk`
summary sheet publishes chain-net figures (overstock 26, stockout-risk 345),
and `reference_by_vertical` still carries them. They are a benchmark from the
other grain, not a target these cards are expected to hit.
"""

from __future__ import annotations

from typing import Any

from src.formulas.expression import evaluate, parse
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    HORIZON_COVERAGE,
    arch_horizon_factor as _arch_horizon_factor,
    REPLENISH_STATES,
    SCHEMA,
    SNAPSHOT_DATE,
    STATE_ORDER,
    SUPPORTED_FILTERS,
    _rows,
    _scope_clause,
    constants,
    envelope,
    agent_reference,
    filter_options,
    formulas,
    get_engine,
    seasonality,
)

AGENT_ID = "retail.inventory_risk"

# The eleven expressions this board runs, in dependency order. They are used
# twice over, which is the point: `build_items` evaluates every one of them
# here to produce the baseline rows, and the payload ships the same eleven so
# the browser's What-If engine re-evaluates the same rules when a lever moves.
# One catalogue, one answer, whichever side of the wire asks.
#
# The browser refuses to start without all eleven, so the board fails loudly at
# load rather than silently at the first slider drag.
#
# f02-on-hand is gone from this list. It rebuilt a store's on-hand from the
# SKU's base ADS and the store's health/size indices, which is what `atStore`
# needed while `items` was chain-net and a store view had to be derived. This
# route ships the store grid itself now, so on-hand is read, not reconstructed.
ENGINE_FORMULAS = (
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
    "f23-markdown-at-risk-gross",
)

NOTE = (
    "Workbook demonstration data, not a live ERP position. On-hand in the "
    "source workbook is a single reading, so the projection starts at today "
    "rather than back-casting a history that was never recorded."
)


def _float(value: Any) -> float:
    """Postgres NUMERIC arrives as Decimal; the payload is JSON."""
    return float(value) if value is not None else 0.0


def build_items(rows: list[dict], asts: dict[str, tuple]) -> list[dict]:
    """One row per SKU x store -- the workbook's own ENGINE_STORE grain --
    every figure evaluated from the catalogue.

    NOTHING DERIVED HERE IS TYPED HERE. Each column below is the answer of a
    `retail.formula` expression, run through `src.formulas.expression` in the
    order the formulas consume one another -- the same order, from the same
    catalogue, that `engine.js` runs in the browser when a What-If lever moves.
    This function only supplies parameters and decides that order.

    THIS IS STORE GRAIN, NOT CHAIN-NET.
    It used to read `fact_inventory_chain_daily` -- the workbook's 800-row
    ENGINE sheet, one netted row per SKU -- which made every KPI answer a
    question nobody asked: "how many SKUs are slow-moving once surplus in one
    store is allowed to cancel shortage in another". The workbook's own
    ENGINE_STORE grid, and the dropdown a buyer actually filters, count the
    16,000 SKU x store rows instead. Chain-net said 37 slow movers; the grid
    says 75 distinct SKUs across 755 rows. Same rule, same catalogue, right
    population.

    The full f01 -> f07 chain reproduces all 16,000 ENGINE_STORE rows exactly
    (ads, position, rop and state, to 1e-6), which is why nothing here reads a
    stored answer: `store_size` is this row's own store, and f03's allocation
    ratio is 1 because `open_po_qty` was already allocated to this store when
    the grid was seeded.

    COUNTS ARE DISTINCT SKUs, VALUES ARE ROW SUMS -- and that split is decided
    downstream, in `selectors.js`'s `computeKpis`, not here. This function
    emits rows; it does not count them.

    THE THREE KPI PREDICATES FOLLOW f07, NOT THE SPEC'S CARD COLUMN.
    The A2 spec's "Formula (card fx)" column and the sheet beside it disagree,
    and the spec presents them as if they did not: the raw
    `growth < 1 and dos > 10` predicate claims rows a more urgent state has
    already taken, so following the spec made the card contradict the chart
    directly beneath it. `is_stockout_risk` is the same argument: f07 assigns
    Stockout below `0.6 x ROP` and Low below ROP, so those two states ARE the
    rows below the reorder point, by construction -- reading them off the state
    costs nothing and cannot drift from f07.
    """
    items = []
    for row in rows:
        price = _float(row["unit_price"])
        perishable = "Y" if row["is_perishable"] else "N"
        promo_eligible = "Y" if row["is_promo_eligible"] else "N"
        shelf_life_days = row["shelf_life_days"] or 0
        growth = _float(row["growth_index"])
        lead_days = _float(row["lead_time_days"])
        safety_days = _float(row["safety_days"])
        base_ads = _float(row["base_ads"])
        seasonality_index = _float(row["seasonality_index"])
        promo_depth = _float(row["cannibalisation_pct"])
        # This row IS one store, so f01's `store_size` is that store's own
        # size index -- the vertical total belonged to the chain-net grain and
        # would inflate ADS by roughly the store count if left in place.
        store_size_index = _float(row["size_index"])
        # f01's archetype/horizon multiplier, preferred from `dim_item` and
        # recovered from the stored `ads` when that column is NULL -- which it
        # is until sql/retail/008 has been applied AND the dims re-seeded.
        #
        # NOT a 1.0 fallback. One would be f01's arithmetic identity and would
        # therefore look harmless, but it silently reproduces the pre-v8.5
        # dataset -- an ADS the workbook never calculated, and with it a
        # different DoS, state and expiry figure on every card below. The
        # division recovers the real factor exactly (see `_arch_horizon_factor`)
        # and only falls back when the row carries no usable inputs at all.
        stored_factor = row.get("arch_horizon_factor")
        arch_horizon_factor = (
            _float(stored_factor)
            if stored_factor is not None
            else _arch_horizon_factor(
                _float(row["ads"]), base_ads, seasonality_index, store_size_index
            )
        )

        def run(formula_id: str, values: dict[str, Any]) -> Any:
            return evaluate(asts[formula_id], values)

        # -- the chain, in dependency order ------------------------------
        # Levers sit at zero throughout: this is the baseline board, and zero
        # is the setting the workbook itself was calculated at (Constants
        # B16-B21). The browser re-runs these same expressions off the
        # parameters carried below when a lever actually moves.
        ads = run(
            "f01-ads-per-store",
            {
                "base_ads": base_ads,
                "seasonality": seasonality_index,
                "arch_horizon_factor": arch_horizon_factor,
                "store_size": store_size_index,
                "demand_lever": 0,
                "promo_eligible": promo_eligible,
                "promo_lever": 0,
                "promo_depth": promo_depth,
            },
        )

        # `open_po_qty` on a store row was ALREADY allocated to this store when
        # the grid was seeded (the workbook's own
        # `open_po_chain x store.size / vertical total`), so passing the two
        # sizes as equal makes f03's ratio one and stops it allocating a second
        # time. It runs anyway rather than being short-circuited: the ratio
        # being one is a property of this grain, not a licence to skip the rule
        # -- and `inbound_lever` still has to reach the expression.
        open_po = run(
            "f03-open-po-per-store",
            {
                "open_po_total": _float(row["open_po_qty"]),
                "store_size": store_size_index,
                "total_store_size": store_size_index,
                "inbound_lever": 0,
            },
        )

        on_hand = _float(row["on_hand_qty"])
        position = run("f04-position", {"on_hand": on_hand, "open_po": open_po})

        reorder = {
            "ads": ads,
            "lead_time_days": lead_days,
            "lead_time_adjust": 0,
            "safety_days": safety_days,
            "safety_adjust": 0,
        }
        rop = run("f05-rop", reorder)
        max_qty = run(
            "f06-maximum-inventory",
            {**reorder, "horizon_coverage": HORIZON_COVERAGE},
        )

        dos = run("f20-days-of-supply", {"ads": ads, "position": position})

        state = run(
            "f07-inventory-state",
            {
                "position": position,
                "rop": rop,
                "days_of_supply": dos,
                "perishable": perishable,
                "shelf_life_days": shelf_life_days,
                "velocity": growth,
            },
        )

        items.append(
            {
                "sku_id": row["item_key"],
                # The other half of this row's identity. A SKU now appears once
                # per store, so anything keying or de-duplicating on `sku_id`
                # alone silently collapses 16,000 rows back down to 800.
                "store_id": row["store_key"],
                "store_name": row["store_name"],
                "cluster": row["cluster"],
                "channel": row["channel"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "category_id": row["category_id"],
                "category_name": row["category_name"],
                "brand": row["brand"],
                "vendor": row["vendor_short"],
                "state": state,
                "severity_rank": STATE_ORDER.index(state),
                "on_hand": on_hand,
                "open_po": open_po,
                "position": position,
                "rop": rop,
                "max": max_qty,
                "dos": dos,
                "ads": ads,
                "price": price,
                "inv_value": run(
                    "f21-inventory-value", {"position": position, "price": price}
                ),
                "at_risk_value": run(
                    "f12-at-risk-value",
                    {"state": state, "position": position, "price": price},
                ),
                "expiry_units": run(
                    "f22-expiry-units",
                    {
                        "perishable": perishable,
                        "position": position,
                        "ads": ads,
                        "shelf_life_days": shelf_life_days,
                    },
                ),
                # The money line under the Overstock and Expiry tiles. Both sum
                # this one field rather than re-deriving f23's branches, which
                # is what `selectors.js` used to do in two places.
                "markdown_at_risk_gross": run(
                    "f23-markdown-at-risk-gross",
                    {
                        "state": state,
                        "position": position,
                        "ads": ads,
                        "shelf_life_days": shelf_life_days,
                        "max_inventory": max_qty,
                        "price": price,
                    },
                ),
                "shelf_life_days": row["shelf_life_days"],
                "is_perishable": bool(row["is_perishable"]),
                "growth": growth,
                # All three read the state f07 just returned -- see the
                # docstring for why none of them restates a threshold.
                "is_stockout_risk": state in REPLENISH_STATES,
                "is_overstock": state == "Overstock",
                "is_slow_mover": state == "Slow-mover",
                # -- What-If parameters, never answers ------------------
                "base_ads": base_ads,
                "seasonality": seasonality_index,
                # This store's own size index, feeding f01 directly. Shipped
                # alongside an equal `total_store_size` so the browser's f03
                # reaches the same ratio-of-one the baseline above used --
                # `open_po` below is already this store's allocated share.
                "store_size": store_size_index,
                "total_store_size": store_size_index,
                # f01's archetype/horizon factor. Resolved once above, from
                # `dim_item` where sql/retail/008 has been seeded and by
                # dividing it back out of the stored `ads` where it has not --
                # never from a bare 1.0, which would silently reproduce the
                # pre-v8.5 dataset.
                "arch_horizon_factor": arch_horizon_factor,
                # `Constants` B24. A model parameter rather than a fact about
                # this SKU, but f06 reads it per row, so it rides along.
                "horizon_coverage": HORIZON_COVERAGE,
                "promo_eligible": promo_eligible,
                "promo_depth": promo_depth,
                "lead_days": lead_days,
                "safety_days": safety_days,
                "perishable": perishable,
                # `onhand_days` / `stock_factor` used to ride along here so the
                # browser could rebuild a store's on-hand with f02 (`atStore`).
                # This route now ships the store grid itself, so that
                # reconstruction has nothing left to reconstruct -- the row IS
                # the store -- and both fields left with it rather than being
                # paid for 16,000 times over.
                "next_agent": (
                    "3 Replenish" if state in REPLENISH_STATES else "5 Markdown"
                ),
            }
        )
    return items


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()
    where, params = _scope_clause(scope, "i.vertical_id", "i.category_id")
    params["day"] = SNAPSHOT_DATE

    with get_engine().connect() as connection:
        # ENGINE_STORE grain: one row per SKU x store, 16,000 of them. The
        # chain-net table is deliberately NOT read here any more -- see
        # `build_items`. Only the three raw inputs f01/f03/f04 consume are
        # taken from the fact table (`ads` for the archetype fallback,
        # `on_hand_qty`, `open_po_qty`); position/rop/max/dos/state are all
        # re-derived from the catalogue rather than read as stored answers.
        store_rows = _rows(
            connection,
            f"""
            SELECT f.item_key, f.store_key, f.ads, f.on_hand_qty, f.open_po_qty,
                   i.price AS unit_price,
                   i.name, i.vertical_id, i.category_id, i.category_name,
                   i.brand, i.is_perishable, i.shelf_life_days, i.base_ads,
                   i.seasonality_index, i.arch_horizon_factor,
                   i.lead_time_days, i.safety_days,
                   i.growth_index, i.is_promo_eligible, i.cannibalisation_pct,
                   s.name AS store_name, s.cluster, s.channel, s.size_index,
                   v.vendor_short
            FROM {SCHEMA}.fact_inventory_daily f
            JOIN {SCHEMA}.dim_item i ON i.item_id = f.item_key
            JOIN {SCHEMA}.dim_store s ON s.store_id = f.store_key
            JOIN {SCHEMA}.dim_vertical vt ON vt.vertical_id = i.vertical_id
            LEFT JOIN {SCHEMA}.dim_vendor v ON v.vendor_account = i.vendor_account
            WHERE f.cal_date = :day{where}
            -- The workbook's own order: vertical first, SKU within it, then
            -- store so a SKU's twenty rows stay together.
            ORDER BY vt.sort_order, f.item_key, f.store_key
            """,
            params,
        )

        # Per-store aggregates. The raw grid is 16,000 rows and every A2 visual
        # over it renders an aggregate, so it collapses here: ~4 MB becomes
        # ~5 KB with nothing lost that is actually drawn.
        store_where, store_params = _scope_clause(scope, "s.vertical_id", None)
        store_params["day"] = SNAPSHOT_DATE
        stores = _rows(
            connection,
            f"""
            SELECT s.store_id, s.name, s.vertical_id, s.cluster, s.channel,
                   -- Not decoration: with the two item columns above these
                   -- reconstruct any row of the per-store grid, which is what
                   -- lets the store filter work off aggregates.
                   s.size_index, s.health_index,
                   count(*)                                        AS sku_count,
                   sum(CASE WHEN f.state = 'Stockout' THEN 1 ELSE 0 END)    AS stockout_count,
                   sum(CASE WHEN f.state = 'Low' THEN 1 ELSE 0 END)         AS low_count,
                   sum(CASE WHEN f.position_qty < f.rop_qty THEN 1 ELSE 0 END)
                                                                   AS stockout_risk_count,
                   sum(CASE WHEN f.state = 'Healthy' THEN 1 ELSE 0 END)     AS healthy_count,
                   sum(CASE WHEN f.state <> 'Healthy' THEN 1 ELSE 0 END)    AS at_risk_count,
                   -- At risk for a reason OTHER than sitting below the reorder
                   -- point, so this and stockout_risk_count above partition
                   -- at_risk_count exactly. Excluding the three states by name
                   -- stopped doing that once Expiry began outranking
                   -- Stockout/Low: a perishable row can be below ROP and read
                   -- "Expiry", which counted it on both sides.
                   sum(CASE
                       WHEN f.state <> 'Healthy' AND f.position_qty >= f.rop_qty
                       THEN 1 ELSE 0
                   END)                                               AS other_at_risk_count,
                   coalesce(sum(f.position_qty * i.price), 0)      AS inv_value,
                   coalesce(sum(
                       CASE WHEN f.state <> 'Healthy'
                            THEN f.position_qty * i.price ELSE 0 END
                   ), 0)                                           AS at_risk_value
            FROM {SCHEMA}.fact_inventory_daily f
            JOIN {SCHEMA}.dim_store s ON s.store_id = f.store_key
            JOIN {SCHEMA}.dim_item  i ON i.item_id  = f.item_key
            WHERE f.cal_date = :day{store_where}
            GROUP BY s.store_id, s.name, s.vertical_id, s.cluster, s.channel,
                     s.size_index, s.health_index
            ORDER BY s.store_id
            """,
            store_params,
        )

        at_risk_by_state_rows = _rows(
            connection,
            f"""
            SELECT f.state, i.category_id, i.category_name,
                   coalesce(sum(f.position_qty * i.price), 0) AS at_risk_value
            FROM {SCHEMA}.fact_inventory_daily f
            JOIN {SCHEMA}.dim_store s ON s.store_id = f.store_key
            JOIN {SCHEMA}.dim_item  i ON i.item_id  = f.item_key
            WHERE f.cal_date = :day AND f.state <> 'Healthy'{store_where}
            GROUP BY f.state, i.category_id, i.category_name
            ORDER BY sum(f.position_qty * i.price) DESC
            """,
            store_params,
        )

        options = filter_options(connection)
        # The agent's own KPI sheet, per vertical. Nothing on screen renders
        # it; it is what every figure above is reconciled against.
        reference = agent_reference(connection, AGENT_ID)

        # The projection burns a shaped daily curve rather than a flat ADS, so
        # this board needs the same two inputs A1 reads. Neither moves a single
        # stock figure above; both decide how that stock is spent over the
        # horizon. Without them the browser falls back to a flat week, which is
        # a straight line drawn where a measured week should be.
        seasonal = seasonality(connection)
        trend_by_vertical = {
            row["legal_entity_id"]: row.get("trend_pct", 0.0)
            for row in agent_reference(connection, "retail.demand_forecasting")
        }

    catalogue_formulas = formulas(ENGINE_FORMULAS)
    # Parsed once for all 800 rows rather than per row: `build_items` walks the
    # whole chain per SKU, and re-parsing twelve expressions each time would be
    # ~10,000 parses for one dashboard load.
    asts = {
        name: parse(expression) for name, expression in catalogue_formulas.items()
    }

    by_state_buckets: dict[str, dict[str, Any]] = {}
    for row in at_risk_by_state_rows:
        st = row["state"]
        if st not in by_state_buckets:
            by_state_buckets[st] = {"state": st, "total": 0.0, "segments": []}
        val = _float(row["at_risk_value"])
        by_state_buckets[st]["total"] += val
        by_state_buckets[st]["segments"].append({
            "category_id": row["category_id"],
            "label": row["category_name"],
            "value": val,
        })

    at_risk_by_state_gross = [
        {
            "state": st,
            "total": by_state_buckets[st]["total"],
            "segments": sorted(
                by_state_buckets[st]["segments"],
                key=lambda s: s["value"],
                reverse=True,
            ),
        }
        for st in STATE_ORDER
        if st in by_state_buckets
    ]

    return {
        **envelope(AGENT_ID, NOTE),
        "state_order": list(STATE_ORDER),
        # `hz_cov` on top of the shared set: it is f06's horizon term, this is
        # the only board that evaluates f06, and the browser needs the same
        # value the baseline above used or a lever drag would move Max on its
        # own. Agent 1 layers `interval_z` the same way.
        "constants": {**constants(), "hz_cov": HORIZON_COVERAGE},
        "seasonality": seasonal,
        "formulas": catalogue_formulas,
        "filter_options": options,
        "at_risk_by_state": at_risk_by_state_gross,
        "items": build_items(store_rows, asts),
        "stores": [
            {
                "store_id": row["store_id"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "cluster": row["cluster"],
                "channel": row["channel"],
                "size_index": _float(row["size_index"]),
                "health_index": _float(row["health_index"]),
                "sku_count": row["sku_count"],
                "stockout_count": row["stockout_count"],
                "low_count": row["low_count"],
                "stockout_risk_count": row["stockout_risk_count"],
                "healthy_count": row["healthy_count"],
                "at_risk_count": row["at_risk_count"],
                "other_at_risk_count": row["other_at_risk_count"],
                "inv_value": _float(row["inv_value"]),
                "at_risk_value": _float(row["at_risk_value"]),
            }
            for row in stores
        ],
        # A2's own totals, plus A1's typed annual trend. The trend is not an A2
        # figure and is not displayed as one -- it is carried because the
        # projection compounds it, and it belongs beside the vertical it
        # describes rather than in a second block keyed the same way.
        "reference_by_vertical": [
            {**row, "trend_pct": trend_by_vertical.get(row["legal_entity_id"], 0.0)}
            for row in reference
        ],
    }


__all__ = ["SUPPORTED_FILTERS", "build"]
