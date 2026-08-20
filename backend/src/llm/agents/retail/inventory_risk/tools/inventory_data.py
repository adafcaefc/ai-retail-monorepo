"""Agent 2 · Inventory Risk — the snapshot its chat and monitors read.

Chain-net throughout, from `fact_inventory_chain_daily`: one row per item, 800
of them, with surplus in one store already netted against shortage in another.
The per-store table is deliberately not summed here. It is a legitimate second
grain, roughly 1.25x larger in at-risk value, and a snapshot that carried both
without labelling them would invite exactly the comparison that makes the two
look like a discrepancy rather than two answers to two questions.

The store block below is the one place per-store data appears, and it is named
`store_gross_*` for that reason.
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
                   count(*)                                                     AS skus,
                   -- Carried per state so the total below can count below-ROP
                   -- rows without caring which state they were labelled with.
                   sum(CASE WHEN c.position_qty < c.rop_qty THEN 1 ELSE 0 END)   AS below_rop_skus,
                   coalesce(sum(CASE WHEN c.state <> 'Healthy' THEN c.position_qty * i.price ELSE 0 END), 0)
                                                                                AS at_risk_value,
                   coalesce(sum(c.position_qty * i.price), 0)                   AS inventory_value,
                   round(avg(c.days_cover), 2)                                  AS avg_days_cover,
                   coalesce(sum(
                       CASE WHEN i.is_perishable = 1 AND c.days_cover > i.shelf_life_days
                            THEN c.position_qty - c.ads * i.shelf_life_days ELSE 0 END
                   ), 0)                                                        AS expiry_units
            FROM {PER_STORE} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            JOIN {warehouse.SCHEMA}.dim_store s ON s.store_id = c.store_key
            WHERE 1 = 1{clause}
            GROUP BY c.state
            ORDER BY sum(CASE WHEN c.state <> 'Healthy' THEN c.position_qty * i.price ELSE 0 END) DESC
            """,
            params,
        )

        by_vertical = snapshot._rows(
            connection,
            f"""
            SELECT i.vertical_id,
                   v.dashboard_label,
                   count(*)                                                     AS skus,
                   sum(CASE WHEN c.position_qty < c.rop_qty THEN 1 ELSE 0 END)   AS stockout_risk_skus,
                   sum(CASE WHEN c.state = 'Overstock' THEN 1 ELSE 0 END)       AS overstock_skus,
                   sum(CASE WHEN c.state = 'Slow-mover' THEN 1 ELSE 0 END)      AS slow_mover_skus,
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
        "skus": sum(row["skus"] for row in by_state),
        "inventory_value": sum(row["inventory_value"] or 0 for row in by_state),
        "at_risk_value": sum(row["at_risk_value"] or 0 for row in by_state),
        "expiry_units": sum(row["expiry_units"] or 0 for row in by_state),
        # Summed across every state, not filtered to Stockout/Low: an Expiry row
        # can be below ROP too, now that Expiry is tested first.
        "stockout_risk_skus": sum(row["below_rop_skus"] or 0 for row in by_state),
        "overstock_skus": sum(
            row["skus"] for row in by_state if row["state"] == "Overstock"
        ),
        "slow_mover_skus": sum(
            row["skus"] for row in by_state if row["state"] == "Slow-mover"
        ),
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
