"""Agent 2 · Inventory Risk — the snapshot its chat and monitors read.

ENGINE_STORE grain, from `fact_inventory_daily`: one row per SKU x store,
16,000 of them, matching the board's KPI cards row for row. It was chain-net
(`fact_inventory_chain_daily`, 800 netted rows) until the cards moved, and a
chat answer drawn from the other grain is the discrepancy a reader notices
first -- they are looking at the tile while they ask.

COUNTS ARE DISTINCT SKUs, VALUES ARE ROW SUMS, exactly as `computeKpis` does
client-side. `count(*)` here would answer "how many SKU-store rows are
slow-moving" (755) to a question about SKUs (75).

`worst_at_risk_skus` and `expiring_skus` still read the chain table: they rank
whole SKUs by total exposure, which is a chain-net question, and ranking rows
would fill the list with one SKU's twenty branches.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.retail.common import snapshot, warehouse
from src.llm.agents.retail.inventory_risk.dashboard import (
    AGENT_ID,
    ENGINE_FORMULAS,
)

CHAIN = f"{warehouse.SCHEMA}.fact_inventory_chain_daily"
PER_STORE = f"{warehouse.SCHEMA}.fact_inventory_daily"
ITEM = f"{warehouse.SCHEMA}.dim_item"


def get_inventory_risk_snapshot(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
) -> dict[str, Any]:
    """Current chain-net inventory risk: states, at-risk value, worst SKUs.

    The standard portfolio view for Agent 2. Call this before answering
    anything about stock states, days of supply, trapped capital, expiry, or
    where inventory value is at risk. Use query_retail_inventory only for a
    cut this does not already carry.

    Every figure is chain-net (one row per item, netted across stores). Where
    per-store detail appears it is prefixed `store_gross_` and is a GROSS
    figure that legitimately exceeds the chain-net headline.

    Args:
        legal_entity_id: Vertical to narrow to (GRC, GMR, FSH, HNB, ELC, HNL,
            DGT, OMN). Omit for the whole chain.
        category_group: Category id (e.g. "GRC-C02") or category name (e.g.
            "Vegetable") to narrow to. Omit for all categories.
    """
    entity, category = snapshot.scope_filters(legal_entity_id, category_group)
    clause, params = snapshot.where(
        entity,
        category,
        entity_column="i.vertical_id",
        category_column="i.category_id",
        category_name_column="i.category_name",
    )

    with snapshot._read_connection() as connection:
        by_state = snapshot._rows(
            connection,
            f"""
            SELECT c.state,
                   -- DISTINCT SKUs, matching the board's KPI cards. A SKU sits
                   -- in ~20 stores and can be Slow-mover in several, so count(*)
                   -- reports 755 slow-moving ROWS where the card reports the 75
                   -- SKUs they belong to -- and a reader comparing the chat
                   -- answer with the tile would find them disagreeing 10x.
                   count(DISTINCT c.item_key)                                    AS skus,
                   count(*)                                                      AS rows_at_store_grain,
                   -- Carried per state so the total below can count below-ROP
                   -- rows without caring which state they were labelled with.
                   count(DISTINCT CASE WHEN c.position_qty < c.rop_qty
                                       THEN c.item_key END)                      AS below_rop_skus,
                   coalesce(sum(CASE WHEN c.state <> 'Healthy' THEN c.position_qty * i.price ELSE 0 END), 0)
                                                                                AS at_risk_value,
                   coalesce(sum(c.position_qty * i.price), 0)                   AS inventory_value,
                   round(avg(c.days_cover), 2)                                  AS avg_days_cover,
                   -- ROUND per row, inside the sum, because that is what
                   -- f22-expiry-units does: `MAX(0, ROUND(position - ads *
                   -- shelf_life_days, 0))`. Rounding only the total drifts
                   -- from the board by a few units per vertical -- small
                   -- enough to look like noise and wrong for a reason nobody
                   -- would go looking for.
                   coalesce(sum(round(
                       CASE WHEN i.is_perishable = 1 AND c.days_cover > i.shelf_life_days
                            THEN c.position_qty - c.ads * i.shelf_life_days ELSE 0 END
                   , 0)), 0)                                                    AS expiry_units
            FROM {PER_STORE} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            JOIN {warehouse.SCHEMA}.dim_store s ON s.store_id = c.store_key
            WHERE 1 = 1{clause}
            GROUP BY c.state
            ORDER BY sum(CASE WHEN c.state <> 'Healthy' THEN c.position_qty * i.price ELSE 0 END) DESC
            """,
            params,
        )

        # Computed in one pass rather than summed from `by_state`, because
        # distinct-SKU counts do not add up across states: a SKU below ROP in
        # one store and Slow-mover in another appears in both rows, and adding
        # them would report more SKUs than the chain stocks.
        headline = snapshot._rows(
            connection,
            f"""
            SELECT count(DISTINCT c.item_key)                                    AS skus,
                   count(*)                                                      AS rows_at_store_grain,
                   count(DISTINCT CASE WHEN c.position_qty < c.rop_qty
                                       THEN c.item_key END)                      AS stockout_risk_skus,
                   count(DISTINCT CASE WHEN c.state = 'Stockout'
                                       THEN c.item_key END)                      AS stockout_skus,
                   count(DISTINCT CASE WHEN c.state = 'Overstock'
                                       THEN c.item_key END)                      AS overstock_skus,
                   count(DISTINCT CASE WHEN c.state = 'Slow-mover'
                                       THEN c.item_key END)                      AS slow_mover_skus
            FROM {PER_STORE} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            JOIN {warehouse.SCHEMA}.dim_store s ON s.store_id = c.store_key
            WHERE 1 = 1{clause}
            """,
            params,
        )[0]

        by_vertical = snapshot._rows(
            connection,
            f"""
            SELECT i.vertical_id,
                   v.dashboard_label,
                   count(DISTINCT c.item_key)                                    AS skus,
                   count(DISTINCT CASE WHEN c.position_qty < c.rop_qty
                                       THEN c.item_key END)                      AS stockout_risk_skus,
                   count(DISTINCT CASE WHEN c.state = 'Overstock'
                                       THEN c.item_key END)                      AS overstock_skus,
                   count(DISTINCT CASE WHEN c.state = 'Slow-mover'
                                       THEN c.item_key END)                      AS slow_mover_skus,
                   coalesce(sum(c.position_qty * i.price), 0)                   AS inventory_value,
                   coalesce(sum(CASE WHEN c.state <> 'Healthy' THEN c.position_qty * i.price ELSE 0 END), 0)
                                                                                AS at_risk_value,
                   round(avg(c.days_cover), 2)                                  AS avg_days_cover
            FROM {PER_STORE} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            JOIN {warehouse.SCHEMA}.dim_vertical v ON v.vertical_id = i.vertical_id
            JOIN {warehouse.SCHEMA}.dim_store s ON s.store_id = c.store_key
            WHERE 1 = 1{clause}
            GROUP BY i.vertical_id, v.dashboard_label, v.sort_order
            ORDER BY v.sort_order
            """,
            params,
        )

        worst = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   c.item_key,
                   i.name,
                   i.vertical_id,
                   i.category_name,
                   i.brand,
                   c.state,
                   round(c.position_qty, 0)               AS position,
                   round(c.rop_qty, 0)                    AS rop,
                   round(c.days_cover, 2)     AS days_cover,
                   round(c.at_risk_value, 0)              AS at_risk_value,
                   round(c.inventory_value, 0)            AS inventory_value,
                   i.is_perishable,
                   i.shelf_life_days
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            WHERE c.at_risk_value > 0{clause}
            ORDER BY c.at_risk_value DESC
            """,
            {**params, "top_n": snapshot.TOP_N},
        )

        expiring = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   c.item_key,
                   i.name,
                   i.vertical_id,
                   i.shelf_life_days,
                   round(c.days_cover, 2)  AS days_cover,
                   round(c.expiry_units, 0)   AS expiry_units,
                   round(c.at_risk_value, 0)           AS at_risk_value
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            WHERE c.expiry_units > 0{clause}
            ORDER BY c.expiry_units DESC
            """,
            {**params, "top_n": snapshot.TOP_N},
        )

        # The one per-store block, named so it cannot be read as chain-net.
        store_clause, store_params = snapshot.where(
            entity,
            category,
            entity_column="i.vertical_id",
            category_column="i.category_id",
            category_name_column="i.category_name",
        )
        stores = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   f.store_key,
                   s.name,
                   s.vertical_id,
                   s.cluster,
                   sum(CASE WHEN f.state <> 'Healthy' THEN 1 ELSE 0 END) AS at_risk_skus,
                   sum(CASE WHEN f.is_stockout = 1 THEN 1 ELSE 0 END)        AS stockout_skus
            FROM {PER_STORE} f
            JOIN {ITEM} i ON i.item_id = f.item_key
            JOIN {warehouse.SCHEMA}.dim_store s ON s.store_id = f.store_key
            WHERE 1 = 1{store_clause}
            GROUP BY f.store_key, s.name, s.vertical_id, s.cluster
            ORDER BY sum(CASE WHEN f.state <> 'Healthy' THEN 1 ELSE 0 END) DESC
            """,
            {**store_params, "top_n": snapshot.TOP_N},
        )

        reference = snapshot.reference(connection, AGENT_ID)

    totals = {
        # Counts come from `headline` (one DISTINCT pass); money and units are
        # additive and still sum from `by_state`.
        "skus": headline["skus"],
        "rows_at_store_grain": headline["rows_at_store_grain"],
        "inventory_value": sum(row["inventory_value"] or 0 for row in by_state),
        "at_risk_value": sum(row["at_risk_value"] or 0 for row in by_state),
        "expiry_units": sum(row["expiry_units"] or 0 for row in by_state),
        # Below ROP wherever it happens, not filtered to Stockout/Low: an Expiry
        # row can be below ROP too, now that Expiry is tested first.
        "stockout_risk_skus": headline["stockout_risk_skus"],
        "stockout_skus": headline["stockout_skus"],
        "overstock_skus": headline["overstock_skus"],
        "slow_mover_skus": headline["slow_mover_skus"],
    }

    return {
        **snapshot.envelope(
            AGENT_ID,
            legal_entity_id=entity,
            category_group=category,
            formulas=ENGINE_FORMULAS,
        ),
        "grain": "chain_net",
        "totals": totals,
        "state_order": list(warehouse.STATE_ORDER),
        "by_state": by_state,
        "by_vertical": by_vertical,
        "worst_at_risk_skus": worst,
        "expiring_skus": expiring,
        "store_gross_worst": stores,
        "store_gross_note": (
            "Per-store counts, GROSS. They sum each store's own local risk and "
            "will exceed the chain-net figures above, which net surplus "
            "against shortage. Never present these as chain totals."
        ),
        "reference_by_vertical": reference,
        "reference_note": (
            "The workbook's own published KPIs per vertical. Use them to check "
            "a computed headline; a material difference is either a finding or "
            "a mistake, and worth naming as one."
        ),
    }


TOOLS = {
    "get_inventory_risk_snapshot": get_inventory_risk_snapshot,
}


__all__ = ["TOOLS", "get_inventory_risk_snapshot"]
