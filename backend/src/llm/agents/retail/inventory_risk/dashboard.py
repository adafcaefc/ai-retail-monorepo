"""Agent 2 · Inventory Risk — the rows, read from Postgres.

Returns the same shape `scripts/build_inventory_risk_fixture.py` writes, so the
board's selectors run over it unchanged. See `retail/common/warehouse.py` for
why the aggregation stays in the browser.

Two grains are involved and they are not interchangeable. `items` comes from
`fact_inventory_chain_daily` — the workbook's chain-level ENGINE, which is not
the per-store grid rolled up. `stores` is aggregated from
`fact_inventory_daily`, and those totals are GROSS: they sum local pockets of
risk and will exceed the chain-net headline, which nets surplus against
shortage across stores. A2 spec section 10 note 1 calls that out, and the board
labels it rather than reconciling it away.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    REPLENISH_STATES,
    SCHEMA,
    SNAPSHOT_DATE,
    STATE_ORDER,
    SUPPORTED_FILTERS,
    _rows,
    _scope_clause,
    chain_store_size,
    constants,
    envelope,
    agent_reference,
    filter_options,
    formulas,
    get_engine,
)

AGENT_ID = "retail.inventory_risk"

# The ten expressions A2's What-If engine evaluates, in dependency order. It
# refuses to start without all of them, so the board fails loudly at load
# rather than silently at the first slider drag.
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
)

NOTE = (
    "Workbook demonstration data, not a live ERP position. On-hand in the "
    "source workbook is a single reading, so the projection starts at today "
    "rather than back-casting a history that was never recorded."
)


def _float(value: Any) -> float:
    """Postgres NUMERIC arrives as Decimal; the payload is JSON."""
    return float(value) if value is not None else 0.0


def build_items(rows: list[dict], store_size: dict[str, float]) -> list[dict]:
    """One row per SKU at chain-net level, every predicate pre-resolved.

    The three KPI predicates follow the workbook's own A2 sheet, not the A2
    spec's "Formula (card fx)" column — the two disagree, and the spec presents
    them as if they did not. `state == "Slow-mover"` gives 51 where the raw
    `growth < 1 and dos > 10` predicate gives 62, because 11 SKUs satisfy it
    but were already claimed by a more urgent state. Following the spec made
    the card contradict the chart directly beneath it.
    """
    items = []
    for row in rows:
        state = row["state"]
        perishable = "Y" if row["is_perishable"] else "N"

        items.append(
            {
                "sku_id": row["item_key"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "category_id": row["category_id"],
                "category_name": row["category_name"],
                "brand": row["brand"],
                "vendor": row["vendor_short"],
                "state": state,
                "severity_rank": STATE_ORDER.index(state),
                "on_hand": _float(row["on_hand_qty"]),
                "open_po": _float(row["open_po_qty"]),
                "position": _float(row["position_qty"]),
                "rop": _float(row["rop_qty"]),
                "max": _float(row["max_qty"]),
                "dos": _float(row["days_cover"]),
                "ads": _float(row["ads"]),
                "price": _float(row["unit_price"]),
                "inv_value": _float(row["inventory_value"]),
                "at_risk_value": _float(row["at_risk_value"]),
                "expiry_units": _float(row["expiry_units"]),
                "shelf_life_days": row["shelf_life_days"],
                "is_perishable": bool(row["is_perishable"]),
                "growth": _float(row["growth_index"]),
                "is_stockout_risk": _float(row["position_qty"]) < _float(row["rop_qty"]),
                "is_overstock": state == "Overstock",
                "is_slow_mover": state == "Slow-mover",
                # -- What-If parameters, never answers ------------------
                "base_ads": _float(row["base_ads"]),
                "seasonality": _float(row["seasonality_index"]),
                # The vertical's total size index, not one store's: a chain-net
                # row already covers every store.
                "store_size": store_size[row["vertical_id"]],
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_depth": _float(row["cannibalisation_pct"]),
                "lead_days": _float(row["lead_time_days"]),
                "safety_days": _float(row["safety_days"]),
                "perishable": perishable,
                # The pair that lets the board scope to ONE store without this
                # route shipping the 16,000-row grid:
                #
                #   on_hand(sku, store) = base_ads * onhand_days * stock_factor
                #                         * store.health_index * store.size_index
                #
                # `atStore` in the browser's engine.js applies it, against the
                # `size_index` / `health_index` carried on the store rows below.
                # Verified against every ENGINE_STORE row by the fixture
                # builder, so a store-scoped position is the workbook's own.
                "onhand_days": _float(row["onhand_days"]),
                "stock_factor": _float(row["stock_factor"]),
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
        chain = _rows(
            connection,
            f"""
            SELECT c.item_key, c.ads, c.on_hand_qty, c.open_po_qty,
                   c.position_qty, c.rop_qty, c.max_qty, c.days_cover, c.state,
                   c.unit_price, c.inventory_value, c.at_risk_value,
                   c.expiry_units,
                   i.name, i.vertical_id, i.category_id, i.category_name,
                   i.brand, i.is_perishable, i.shelf_life_days, i.base_ads,
                   i.seasonality_index, i.lead_time_days, i.safety_days,
                   i.growth_index, i.is_promo_eligible, i.cannibalisation_pct,
                   i.onhand_days, i.stock_factor,
                   v.vendor_short
            FROM {SCHEMA}.fact_inventory_chain_daily c
            JOIN {SCHEMA}.dim_item i ON i.item_id = c.item_key
            JOIN {SCHEMA}.dim_vertical vt ON vt.vertical_id = i.vertical_id
            LEFT JOIN {SCHEMA}.dim_vendor v ON v.vendor_account = i.vendor_account
            WHERE c.cal_date = :day{where}
            -- The workbook's own order: vertical first, SKU within it.
            -- Alphabetical would open every board on Digital.
            ORDER BY vt.sort_order, c.item_key
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

        options = filter_options(connection)
        # The agent's own KPI sheet, per vertical. Nothing on screen renders
        # it; it is what every figure above is reconciled against.
        reference = agent_reference(connection, AGENT_ID)
        store_size = chain_store_size(connection)

    return {
        **envelope(AGENT_ID, NOTE),
        "state_order": list(STATE_ORDER),
        "constants": constants(),
        "formulas": formulas(ENGINE_FORMULAS),
        "filter_options": options,
        "items": build_items(chain, store_size),
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
        "reference_by_vertical": reference,
    }


__all__ = ["SUPPORTED_FILTERS", "build"]
