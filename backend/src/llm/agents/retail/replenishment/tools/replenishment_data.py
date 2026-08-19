"""Agent 3 · Replenishment — the snapshot its chat and monitors read.

Two things here are easy to get wrong and expensive to get wrong.

UNITS. Every order exists in two of them. `order_qty_sales` is how customers
buy the item; `order_qty_buy` is how you buy it from the vendor, related by
`dim_item.pack_factor` through formula f10 (CEILING, so a part carton rounds
up and the two never divide cleanly). A purchase order raised in sales units
is not a smaller order, it is a wrong one. Both travel in every row here, named
so they cannot be confused.

VALUE AND AUTHORITY. `amount` is what a line costs at the designated vendor's
trade-agreement price. The ERP approval matrix routes a purchase order by that
value -- Purchasing Manager to 100mn, Procurement Director to 500mn, CFO above
-- so the tiers are computed here rather than left to the model to recall.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.retail.common import snapshot, warehouse
from src.llm.agents.retail.replenishment.dashboard import (
    AGENT_ID,
    ENGINE_FORMULAS,
)

PROPOSAL = f"{warehouse.SCHEMA}.replenishment_proposal"
ITEM = f"{warehouse.SCHEMA}.dim_item"
VENDOR = f"{warehouse.SCHEMA}.dim_vendor"

# ERP Approval Matrix, Purchase Order row. Values in IDR.
TIER_1_LIMIT = 100_000_000
TIER_2_LIMIT = 500_000_000

APPROVAL_TIERS = {
    "tier_1": f"Purchasing Manager, up to IDR {TIER_1_LIMIT:,}",
    "tier_2": f"Procurement Director, up to IDR {TIER_2_LIMIT:,}",
    "tier_3": "CFO, unlimited",
}


def get_replenishment_snapshot(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
) -> dict[str, Any]:
    """Current purchase plan: what to reorder, in buy units, at what cost.

    The standard portfolio view for Agent 3. Call this before answering
    anything about reorder quantities, purchase orders, order value, vendor
    sourcing, savings, or coverage. Use query_retail_replenishment only for a
    cut this does not already carry.

    Quantities appear in BOTH units: order_qty_sales (customer units) and
    order_qty_buy (vendor purchase units). Quote buy units for a purchase
    order.

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
        by_vertical = snapshot._rows(
            connection,
            f"""
            SELECT i.vertical_id,
                   v.dashboard_label,
                   sum(CASE WHEN p.is_reorder = 1 THEN 1 ELSE 0 END)          AS skus_to_reorder,
                   round(sum(CASE WHEN p.is_reorder = 1 THEN p.order_qty_sales ELSE 0 END), 0)
                                                                 AS order_units_sales,
                   round(sum(CASE WHEN p.is_reorder = 1 THEN p.order_qty_buy ELSE 0 END), 0)
                                                                 AS order_units_buy,
                   round(sum(CASE WHEN p.is_reorder = 1 THEN p.amount ELSE 0 END), 0)
                                                                 AS order_value,
                   round(sum(CASE WHEN p.is_reorder = 1 THEN p.saving_vs_designated ELSE 0 END), 0)
                                                                 AS saving_available
            FROM {PROPOSAL} p
            JOIN {ITEM} i ON i.item_id = p.item_key
            JOIN {warehouse.SCHEMA}.dim_vertical v ON v.vertical_id = i.vertical_id
            WHERE 1 = 1{clause}
            GROUP BY i.vertical_id, v.dashboard_label, v.sort_order
            ORDER BY v.sort_order
            """,
            params,
        )

        largest = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   p.item_key,
                   i.name,
                   i.vertical_id,
                   i.category_name,
                   round(p.qty_on_hand, 0)          AS on_hand,
                   round(p.open_po_qty, 0)          AS open_po,
                   round(p.rop_qty, 0)              AS rop,
                   round(p.max_qty, 0)              AS max_level,
                   round(p.order_qty_sales, 0)      AS order_qty_sales,
                   round(p.order_qty_buy, 0)        AS order_qty_buy,
                   p.buy_uom,
                   i.pack_factor,
                   round(p.amount, 0)               AS amount,
                   p.designated_vendor,
                   p.best_price_vendor,
                   round(p.saving_vs_designated, 0) AS saving_vs_designated
            FROM {PROPOSAL} p
            JOIN {ITEM} i ON i.item_id = p.item_key
            WHERE p.is_reorder = 1{clause}
            ORDER BY p.amount DESC
            """,
            {**params, "top_n": snapshot.TOP_N},
        )

        savings = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   p.item_key,
                   i.name,
                   i.vertical_id,
                   p.designated_vendor,
                   round(p.unit_price_ta, 2)     AS designated_unit_price,
                   p.best_price_vendor,
                   round(p.best_price, 2)        AS best_unit_price,
                   round(p.amount, 0)               AS amount,
                   round(p.saving_vs_designated, 0) AS saving_vs_designated
            FROM {PROPOSAL} p
            JOIN {ITEM} i ON i.item_id = p.item_key
            WHERE p.is_reorder = 1 AND p.saving_vs_designated > 0{clause}
            ORDER BY p.saving_vs_designated DESC
            """,
            {**params, "top_n": snapshot.TOP_N},
        )

        # Vendor service risk, weighted by what is actually being ordered from
        # each. A poor OTIF on a vendor with no open lines is not this week's
        # problem.
        vendors = snapshot._rows(
            connection,
            f"""
            SELECT p.designated_vendor              AS vendor_account,
                   d.vendor_short,
                   d.otif_pct,
                   d.fill_pct,
                   d.defect_pct,
                   d.lead_adherence_pct,
                   d.lead_time_days,
                   sum(CASE WHEN p.is_reorder = 1 THEN 1 ELSE 0 END)  AS reorder_lines,
                   round(sum(CASE WHEN p.is_reorder = 1 THEN p.amount ELSE 0 END), 0) AS order_value
            FROM {PROPOSAL} p
            JOIN {ITEM} i ON i.item_id = p.item_key
            JOIN {VENDOR} d ON d.vendor_account = p.designated_vendor
            WHERE 1 = 1{clause}
            GROUP BY p.designated_vendor, d.vendor_short, d.otif_pct, d.fill_pct,
                     d.defect_pct, d.lead_adherence_pct, d.lead_time_days
            ORDER BY CASE WHEN sum(CASE WHEN p.is_reorder = 1 THEN p.amount ELSE 0 END) IS NULL THEN 1 ELSE 0 END,
                     sum(CASE WHEN p.is_reorder = 1 THEN p.amount ELSE 0 END) DESC
            """,
            params,
        )

        by_uom = snapshot._rows(
            connection,
            f"""
            SELECT p.buy_uom,
                   sum(CASE WHEN p.is_reorder = 1 THEN 1 ELSE 0 END) AS lines,
                   round(sum(CASE WHEN p.is_reorder = 1 THEN p.order_qty_buy ELSE 0 END), 0)
                                                        AS order_units_buy,
                   round(sum(CASE WHEN p.is_reorder = 1 THEN p.amount ELSE 0 END), 0) AS order_value
            FROM {PROPOSAL} p
            JOIN {ITEM} i ON i.item_id = p.item_key
            WHERE 1 = 1{clause}
            GROUP BY p.buy_uom
            ORDER BY CASE WHEN sum(CASE WHEN p.is_reorder = 1 THEN p.amount ELSE 0 END) IS NULL THEN 1 ELSE 0 END,
                     sum(CASE WHEN p.is_reorder = 1 THEN p.amount ELSE 0 END) DESC
            """,
            params,
        )

        approval = snapshot._rows(
            connection,
            f"""
            WITH classified AS (
                SELECT CASE
                         WHEN p.amount <= :tier1 THEN 'tier_1'
                         WHEN p.amount <= :tier2 THEN 'tier_2'
                         ELSE 'tier_3'
                       END AS tier,
                       p.amount
                FROM {PROPOSAL} p
                JOIN {ITEM} i ON i.item_id = p.item_key
                WHERE p.is_reorder = 1{clause}
            )
            SELECT tier,
                   count(*) AS lines,
                   round(sum(amount), 0) AS order_value
            FROM classified
            GROUP BY tier
            ORDER BY tier
            """,
            {**params, "tier1": TIER_1_LIMIT, "tier2": TIER_2_LIMIT},
        )

        reference = snapshot.reference(connection, AGENT_ID)

    totals = {
        "skus_to_reorder": sum(row["skus_to_reorder"] for row in by_vertical),
        "order_units_sales": sum(
            row["order_units_sales"] or 0 for row in by_vertical
        ),
        "order_units_buy": sum(row["order_units_buy"] or 0 for row in by_vertical),
        "order_value": sum(row["order_value"] or 0 for row in by_vertical),
        "saving_available": sum(
            row["saving_available"] or 0 for row in by_vertical
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
        "policy": (
            "Up-to-max: a line reorders when position < ROP, for "
            "MAX(0, max - position) sales units (f09), converted to buy units "
            "by CEILING(sales / pack_factor) (f10)."
        ),
        "totals": totals,
        "by_vertical": by_vertical,
        "largest_orders": largest,
        "unit_note": (
            "order_qty_sales is customer units; order_qty_buy is vendor "
            "purchase units. Quote buy units and buy_uom for a purchase order."
        ),
        "sourcing_savings": savings,
        "sourcing_note": (
            "saving_vs_designated is the gain from sourcing a line at "
            "best_price_vendor instead of designated_vendor. Switching vendor "
            "is a sourcing decision with service consequences, not a free "
            "saving: check the vendor's OTIF and lead adherence below."
        ),
        "vendors": vendors,
        "by_buy_uom": by_uom,
        "approval_tiers": APPROVAL_TIERS,
        "approval_split": approval,
        "approval_note": (
            "Lines grouped by the ERP approval tier their own value falls in. "
            "Route an action to the tier that matches the value it actually "
            "commits."
        ),
        "reference_by_vertical": reference,
        "reference_note": (
            "The workbook's own published KPIs per vertical. Note its "
            "order_value is priced differently from `amount` here (retail vs "
            "trade-agreement cost), so a gap between them is expected and is "
            "not a finding on its own."
        ),
    }


TOOLS = {
    "get_replenishment_snapshot": get_replenishment_snapshot,
}


__all__ = ["TOOLS", "get_replenishment_snapshot"]
