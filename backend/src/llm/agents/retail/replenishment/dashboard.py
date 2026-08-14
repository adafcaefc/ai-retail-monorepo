"""Agent 3 · Replenishment — the order lines, read from Postgres.

Returns the same shape `scripts/build_replenishment_fixture.py` writes, so the
board's selectors run over it unchanged. See `retail/common/warehouse.py` for
why the aggregation stays in the browser.

Two prices, both carried. The workbook states order value twice and the two
differ by about a fifth: `ENGINE!P` prices the shortfall at the selling price,
while `Replenishment Detail!amount` prices whole packs at the trade-agreement
price. A buyer approving a purchase order needs the cost; a merchandiser
sizing the commitment needs the retail value. Reporting one as "order value"
and hiding the other is how a board gets used to argue for the wrong decision.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    SCHEMA,
    SNAPSHOT_DATE,
    SUPPORTED_FILTERS,
    _rows,
    _scope_clause,
    constants,
    envelope,
    agent_reference,
    filter_options,
    formulas,
    get_engine,
)

AGENT_ID = "retail.replenishment"

# f01 through f11: the chain from a demand rate to a priced purchase order.
ENGINE_FORMULAS = (
    "f01-ads-per-store",
    "f03-open-po-per-store",
    "f04-position",
    "f05-rop",
    "f06-maximum-inventory",
    "f09-order-quantity-sales-units",
    "f10-order-quantity-purchase-units",
    "f11-order-value",
    "f20-days-of-supply",
)

# A3 spec section 2. Lead time decides the route, not the category: the spec's
# `catId in {BEV, HOU}` names categories this dataset has never had, while
# `lead_d` takes exactly three values that line up with the spec's own
# lead-time story one for one. `perishable == "Y"` and `lead_d == 2` select the
# same 75 rows, so the fresh rule and the lead-time rule agree where they meet.
ROUTES: tuple[dict[str, Any], ...] = (
    {
        "id": "direct",
        "label": "Direct Store Delivery",
        "lead_days": 2,
        "added_days": 2,
        "note": "Fresh, store-direct. Shortest lead, no consolidation.",
    },
    {
        "id": "flow",
        "label": "Flow-Through",
        "lead_days": 4,
        "added_days": 4,
        "note": "DC pick and pass. No put-away step.",
    },
    {
        "id": "cross",
        "label": "Cross-Docking",
        "lead_days": 7,
        "added_days": 5,
        "note": "DC consolidation across vendors.",
    },
)

NOTE = (
    "Workbook demonstration data, not a live ERP position. Order value is "
    "reported twice — at selling price, which is what the A3 sheet totals, and "
    "at trade-agreement price, which is what the purchase order would actually "
    "cost."
)

DERIVATION = {
    "skus_to_reorder": "measured",
    "order_units": "measured",
    "order_value_retail": "measured",
    "order_value_cost": "measured",
    "inbound_open_po": "measured",
    "fill_rate_pct": "measured",
    "avg_cover_days": "measured",
    "route": "modelled-from-lead-time",
}


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def route_for(lead_days: float) -> str:
    for route in ROUTES:
        if lead_days <= route["lead_days"]:
            return route["id"]
    return ROUTES[-1]["id"]


def build_lines(rows: list[dict]) -> list[dict]:
    """One order line per SKU, chain level.

    `order_value_retail` comes from the chain ENGINE and `order_value_cost`
    from the proposal, because the workbook computes them from different
    quantities: retail prices the shortfall, cost prices the whole packs a
    purchase order actually buys. The gap between them is real stock, not a
    reconciliation error, and the board labels it.
    """
    lines = []
    for row in rows:
        lead_days = _float(row["lead_time_days"])
        lines.append(
            {
                "sku_id": row["item_key"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "category_id": row["category_id"],
                "category_label": row["category_name"],
                "route": route_for(lead_days),
                "lead_days": lead_days,
                "perishable": "Y" if row["is_perishable"] else "N",
                "on_hand": _float(row["qty_on_hand"]),
                "open_po": _float(row["open_po_qty"]),
                "position": _float(row["position_qty"]),
                "rop": _float(row["rop_qty"]),
                "max": _float(row["max_qty"]),
                "dos": _float(row["days_cover"]),
                "ads": _float(row["ads"]),
                "is_reorder": bool(row["is_reorder"]),
                "order_qty_sales": _float(row["order_qty_sales"]),
                "order_qty_buy": _float(row["order_qty_buy"]),
                "buy_uom": row["buy_uom"],
                "pack_factor": _float(row["pack_factor"]),
                "order_value_retail": _float(row["order_value"]),
                "order_value_cost": _float(row["amount"]),
                "unit_price_retail": _float(row["unit_price"]),
                "unit_price_trade": _float(row["unit_price_ta"]),
                "designated_vendor": row["designated_short"],
                "best_price_vendor": row["best_short"],
                "best_price": _float(row["best_price"]),
                "saving_vs_designated": _float(row["saving_vs_designated"]),
                # -- What-If parameters ---------------------------------
                "base_ads": _float(row["base_ads"]),
                "seasonality": _float(row["seasonality_index"]),
                "store_size": _float(row["store_size"]),
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_depth": _float(row["cannibalisation_pct"]),
                "safety_days": _float(row["safety_days"]),
            }
        )
    return lines


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()
    where, params = _scope_clause(scope, "i.vertical_id", "i.category_id")
    params["day"] = SNAPSHOT_DATE

    with get_engine().connect() as connection:
        rows = _rows(
            connection,
            f"""
            SELECT p.item_key, p.qty_on_hand, p.open_po_qty, p.rop_qty,
                   p.max_qty, p.is_reorder, p.order_qty_sales, p.order_qty_buy,
                   p.buy_uom, p.unit_price_ta, p.amount, p.best_price,
                   p.saving_vs_designated,
                   c.position_qty, c.days_cover, c.ads, c.unit_price,
                   c.order_value,
                   i.name, i.vertical_id, i.category_id, i.category_name,
                   i.is_perishable, i.lead_time_days, i.safety_days,
                   i.pack_factor, i.base_ads, i.seasonality_index,
                   i.is_promo_eligible, i.cannibalisation_pct,
                   dv.vendor_short AS designated_short,
                   bv.vendor_short AS best_short,
                   sz.total        AS store_size
            FROM {SCHEMA}.replenishment_proposal p
            JOIN {SCHEMA}.dim_item i ON i.item_id = p.item_key
            JOIN {SCHEMA}.fact_inventory_chain_daily c
              ON c.item_key = p.item_key AND c.cal_date = p.as_of_date
            LEFT JOIN {SCHEMA}.dim_vendor dv
              ON dv.vendor_account = p.designated_vendor
            LEFT JOIN {SCHEMA}.dim_vendor bv
              ON bv.vendor_account = p.best_price_vendor
            JOIN (
                SELECT vertical_id, sum(size_index) AS total
                FROM {SCHEMA}.dim_store GROUP BY vertical_id
            ) sz ON sz.vertical_id = i.vertical_id
            JOIN {SCHEMA}.dim_vertical vt ON vt.vertical_id = i.vertical_id
            WHERE p.as_of_date = :day{where}
            -- The workbook's own order: vertical first, SKU within it.
            -- Alphabetical would open every board on Digital.
            ORDER BY vt.sort_order, p.item_key
            """,
            params,
        )

        # Per-store order aggregates. The proposal is chain level, so a store's
        # share is its share of the chain's position — which is what the A3
        # sheet's own by-store split does.
        store_where, store_params = _scope_clause(scope, "s.vertical_id", None)
        store_params["day"] = SNAPSHOT_DATE
        stores = _rows(
            connection,
            f"""
            SELECT s.store_id, s.name, s.vertical_id, s.cluster, s.channel,
                   count(*)                                     AS sku_count,
                   sum(CASE WHEN f.position_qty < f.rop_qty THEN 1 ELSE 0 END)
                                                                AS reorder_count,
                   -- Read, never recomputed. ENGINE_STORE priced each line
                   -- after rounding it, so re-deriving from the rounded
                   -- quantities compounds the difference — the same reason
                   -- chain-net is stored rather than rolled up from here.
                   coalesce(sum(f.order_qty_sales), 0)          AS order_units,
                   coalesce(sum(f.order_value), 0)              AS order_value_retail,
                   coalesce(sum(f.open_po_qty), 0)              AS open_po
            FROM {SCHEMA}.fact_inventory_daily f
            JOIN {SCHEMA}.dim_store s ON s.store_id = f.store_key
            JOIN {SCHEMA}.dim_item  i ON i.item_id  = f.item_key
            WHERE f.cal_date = :day{store_where}
            GROUP BY s.store_id, s.name, s.vertical_id, s.cluster, s.channel
            ORDER BY s.store_id
            """,
            store_params,
        )

        # Every quote on file for the SKUs in scope. `saving_vs_designated`
        # above is a difference between two of these; carrying only the
        # difference is what left a buyer unable to see who to switch to.
        #
        # Ordered by SKU rather than by the vertical order the lines follow:
        # this is a lookup keyed by SKU, not a table anybody scrolls. Cheapest
        # first within a SKU, so the panel does not sort and the fixture can be
        # compared row for row.
        quotes = _rows(
            connection,
            f"""
            SELECT t.item_key, t.vendor_account, v.vendor_short,
                   t.unit_price, t.min_qty_break, t.discount_pct,
                   t.is_designated
            FROM {SCHEMA}.trade_agreement t
            JOIN {SCHEMA}.dim_item i ON i.item_id = t.item_key
            JOIN {SCHEMA}.dim_vendor v ON v.vendor_account = t.vendor_account
            WHERE 1 = 1{where}
            ORDER BY t.item_key, t.unit_price, t.vendor_account
            """,
            {key: value for key, value in params.items() if key != "day"},
        )

        # Four columns the workbook holds identical across all 2,400 rows, so
        # they travel once rather than 2,400 times. Read with a DISTINCT rather
        # than assumed: if the source ever varies one, this raises instead of
        # picking a value and presenting it as everyone's terms.
        terms = _rows(
            connection,
            f"""
            SELECT DISTINCT currency, lead_time_days, valid_from, valid_to
            FROM {SCHEMA}.trade_agreement
            """,
        )
        if len(terms) != 1:
            raise ValueError(
                f"retail.trade_agreement has {len(terms)} distinct term sets, "
                "expected 1. They have to move onto the quote rows here and in "
                "scripts/build_replenishment_fixture.py together."
            )

        vendors = _rows(
            connection,
            f"""
            SELECT vendor_short, vendor_account, vendor_name, lead_time_days,
                   moq_units, otif_pct, fill_pct, defect_pct,
                   lead_adherence_pct, payment_terms
            FROM {SCHEMA}.dim_vendor
            ORDER BY vendor_account
            """,
        )

        options = filter_options(connection)
        # The agent's own KPI sheet, per vertical. Nothing on screen renders
        # it; it is what every figure above is reconciled against.
        reference = agent_reference(connection, AGENT_ID)

    # A3 filters by route, not by inventory state — that is A2's control.
    options.pop("states", None)
    options["routes"] = [
        {"value": route["id"], "label": route["label"]} for route in ROUTES
    ]

    return {
        **envelope(AGENT_ID, NOTE),
        "constants": constants(),
        "formulas": formulas(ENGINE_FORMULAS),
        "derivation": DERIVATION,
        "routes": [dict(route) for route in ROUTES],
        "filter_options": options,
        "lines": build_lines(rows),
        "quote_terms": {
            "currency": terms[0]["currency"],
            "lead_time_days": terms[0]["lead_time_days"],
            "valid_from": terms[0]["valid_from"].isoformat(),
            "valid_to": terms[0]["valid_to"].isoformat(),
        },
        "quotes": [
            {
                "sku_id": row["item_key"],
                "vendor": row["vendor_short"],
                "vendor_account": row["vendor_account"],
                "unit_price": _float(row["unit_price"]),
                "min_qty_break": _float(row["min_qty_break"]),
                "discount_pct": _float(row["discount_pct"]),
                "is_designated": bool(row["is_designated"]),
            }
            for row in quotes
        ],
        "stores": [
            {
                "store_id": row["store_id"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "cluster": row["cluster"],
                "channel": row["channel"],
                "sku_count": row["sku_count"],
                "reorder_count": row["reorder_count"],
                "order_units": _float(row["order_units"]),
                "order_value_retail": _float(row["order_value_retail"]),
                "open_po": _float(row["open_po"]),
            }
            for row in stores
        ],
        "vendors": [
            {
                "vendor": row["vendor_short"],
                "vendor_account": row["vendor_account"],
                "vendor_name": row["vendor_name"],
                "lead_time_days": _float(row["lead_time_days"]),
                "moq_units": _float(row["moq_units"]),
                "otif_pct": _float(row["otif_pct"]),
                "fill_pct": _float(row["fill_pct"]),
                "defect_pct": _float(row["defect_pct"]),
                "lead_adherence_pct": _float(row["lead_adherence_pct"]),
                "payment_terms": row["payment_terms"],
            }
            for row in vendors
        ],
        "reference_by_vertical": reference,
    }


__all__ = ["SUPPORTED_FILTERS", "build"]
