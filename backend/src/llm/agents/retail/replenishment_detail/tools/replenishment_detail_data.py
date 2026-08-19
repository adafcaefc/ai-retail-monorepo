"""Agent 3.1 · Replenishment Detail — the snapshot its chat and monitors read.

Calls `dashboard.build()` rather than running its own SQL. The exception codes,
the tie-out checks and the UOM conversion all live in exactly one place there,
and the whole point of this agent is that a planner and the agent describing it
to them are looking at the same lines. A second implementation here would
eventually flag a different set, and the disagreement would surface as an agent
confidently naming a line the grid does not.

What this adds is the roll-up: the six KPIs of spec section 7, the buy-UOM
segmentation that section demands in place of a mixed total, and the rankings a
chat turn needs to answer "which lines matter most" without reading 800 rows.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common import snapshot
from src.llm.agents.retail.replenishment_detail.dashboard import (
    AGENT_ID,
    ENGINE_FORMULAS,
    EXCEPTION_CODES,
    build,
)


def get_replenishment_detail_snapshot(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
) -> dict[str, Any]:
    """Line-level replenishment detail: order quantities, prices, savings, exceptions.

    The standard view for Agent 3.1. Call this before answering anything about
    an individual SKU's order quantity, its UOM conversion, its designated or
    best-price vendor, the amount or saving on a line, why a line is or is not
    flagged for reorder, or which lines cannot be actioned.

    UNITS. `unit_price_ta` and `best_price` are per SALES unit, not per buy
    UOM. Amount = order_qty_buy x pack_factor x unit_price_ta. Saving is priced
    on the same rounded quantity. On a Crate SKU with pack factor 12, treating
    the price as per-Crate understates the line twelvefold.

    Reorder is a strict `Position < ROP`; equality does not trigger. Position
    is `qty_on_hand + open_po`. `order_qty_buy` is a CEILING, so
    `ordered_sales_units` is at or above the raw `Max - Position` requirement
    and `rounding_uplift` is the difference.

    Buy quantities are NOT additive across UOMs. `order_qty_buy_by_uom`
    segments them; a single summed buy count mixing Crates, Pallets and Packs
    is arithmetically valid and operationally meaningless.

    Args:
        legal_entity_id: Vertical to narrow to (GRC, GMR, FSH, HNB, ELC, HNL,
            DGT, OMN). Omit for the whole chain.
        category_group: Category id (e.g. "GRC-C02") or category name (e.g.
            "Vegetable") to narrow to. Omit for all categories.
    """
    entity, category = snapshot.scope_filters(legal_entity_id, category_group)
    scope = DashboardScope(legal_entity_id=entity, category_group=category)
    dashboard = build(scope)

    lines = dashboard["lines"]
    reorder = [line for line in lines if line["is_reorder"]]

    return {
        **snapshot.envelope(
            AGENT_ID,
            legal_entity_id=entity,
            category_group=category,
            formulas=ENGINE_FORMULAS,
        ),
        "grain": (
            "One row per SKU, 800 rows for the whole chain — the "
            "`Replenishment Detail` worksheet. There is no store, cluster, "
            "channel, run id or approval state on this sheet, so no answer "
            "here can be given per store or per replenishment run. Store-level "
            "inventory lives in fact_inventory_daily and belongs to a "
            "different question."
        ),
        "unit_note": (
            "Prices are per sales unit. Amount = order_qty_buy x pack_factor x "
            "unit_price_ta. Buy quantities across different UOMs are not "
            "additive — read order_qty_buy_by_uom instead of summing them."
        ),
        "totals": _totals(lines, reorder),
        "by_vertical": _by_vertical(reorder, dashboard["reference_by_vertical"]),
        "by_category": _by_category(reorder),
        "order_qty_buy_by_uom": _by_uom(reorder),
        "largest_orders": _rank(reorder, "amount"),
        "largest_savings": _rank(
            [line for line in reorder if line["saving_vs_designated"] > 0],
            "saving_vs_designated",
        ),
        "alternate_vendor_lines": _rank(
            [line for line in reorder if line["has_alternate_vendor"]],
            "saving_vs_designated",
        ),
        "sourcing_note": (
            "A cheaper vendor is not automatically the right vendor. Lowest "
            "unit price is not lowest landed cost: lead time, MOQ, capacity, "
            "service level and freight are not in this data. Present a "
            "switch as an opportunity to evaluate, never as a decision."
        ),
        "exception_counts": _exception_counts(lines),
        "blocked_lines": _rank(
            [line for line in reorder if line["action_eligibility"] == "BLOCKED"],
            "amount",
        ),
        "exception_note": (
            "Exception codes come from the spec's data-quality rules. "
            "FORMULA_TIE_OUT_FAILED means the sheet's stored Amount or Saving "
            "does not reconcile against its own inputs, which is a data "
            "finding rather than a planning one."
        ),
        "reference_by_vertical": dashboard["reference_by_vertical"],
        "reference_note": (
            "The agent's own KPI sheet per vertical. Use it to sanity-check a "
            "computed total; a material difference is either a finding or a "
            "mistake, and worth naming as one."
        ),
    }


def _totals(lines: list[dict[str, Any]], reorder: list[dict[str, Any]]) -> dict[str, Any]:
    """The six KPIs of spec section 7, over the lines in scope."""
    amount = sum(line["amount"] for line in reorder)
    return {
        "reorder_sku_count": len(reorder),
        "skus_in_scope": len(lines),
        "order_qty_sales": round(sum(line["order_qty_sales"] for line in reorder), 2),
        "ordered_sales_units": round(
            sum(line["ordered_sales_units"] for line in reorder), 2
        ),
        "rounding_uplift_units": round(
            sum(line["rounding_uplift"] for line in reorder), 2
        ),
        "purchase_amount": round(amount, 2),
        "potential_saving": round(
            sum(line["saving_vs_designated"] for line in reorder), 2
        ),
        "alternate_vendor_opportunities": sum(
            1 for line in reorder if line["has_alternate_vendor"]
        ),
        "blocked_line_count": sum(
            1 for line in reorder if line["action_eligibility"] == "BLOCKED"
        ),
    }


def _by_vertical(
    reorder: list[dict[str, Any]], reference: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    reference_by_id = {row["legal_entity_id"]: row for row in reference}
    groups: dict[str, dict[str, Any]] = {}
    for line in reorder:
        bucket = groups.setdefault(
            line["vertical_id"],
            {
                "vertical_id": line["vertical_id"],
                "reorder_sku_count": 0,
                "order_qty_sales": 0.0,
                "purchase_amount": 0.0,
                "potential_saving": 0.0,
            },
        )
        bucket["reorder_sku_count"] += 1
        bucket["order_qty_sales"] += line["order_qty_sales"]
        bucket["purchase_amount"] += line["amount"]
        bucket["potential_saving"] += line["saving_vs_designated"]

    rows = [
        {
            **bucket,
            "vertical_label": reference_by_id.get(bucket["vertical_id"], {}).get(
                "vertical_label", bucket["vertical_id"]
            ),
            "order_qty_sales": round(bucket["order_qty_sales"], 2),
            "purchase_amount": round(bucket["purchase_amount"], 2),
            "potential_saving": round(bucket["potential_saving"], 2),
        }
        for bucket in groups.values()
    ]
    rows.sort(key=lambda row: row["purchase_amount"], reverse=True)
    return rows


def _by_category(reorder: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for line in reorder:
        bucket = groups.setdefault(
            line["category_id"],
            {
                "category_id": line["category_id"],
                "category_label": line["category_label"],
                "reorder_sku_count": 0,
                "purchase_amount": 0.0,
            },
        )
        bucket["reorder_sku_count"] += 1
        bucket["purchase_amount"] += line["amount"]

    rows = [
        {**bucket, "purchase_amount": round(bucket["purchase_amount"], 2)}
        for bucket in groups.values()
    ]
    rows.sort(key=lambda row: row["purchase_amount"], reverse=True)
    return rows[: snapshot.TOP_N]


def _by_uom(reorder: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Buy quantity segmented by UOM — spec section 7's critical display rule.

    Summing Crates, Pallets and Packs into one buy count is arithmetically
    valid and operationally meaningless, so the total is never offered.
    """
    groups: dict[str, dict[str, Any]] = {}
    for line in reorder:
        uom = line["buy_uom"] or "(none)"
        bucket = groups.setdefault(
            uom,
            {
                "buy_uom": uom,
                "line_count": 0,
                "order_qty_buy": 0.0,
                "purchase_amount": 0.0,
            },
        )
        bucket["line_count"] += 1
        bucket["order_qty_buy"] += line["order_qty_buy"]
        bucket["purchase_amount"] += line["amount"]

    rows = [
        {
            **bucket,
            "order_qty_buy": round(bucket["order_qty_buy"], 2),
            "purchase_amount": round(bucket["purchase_amount"], 2),
        }
        for bucket in groups.values()
    ]
    rows.sort(key=lambda row: row["purchase_amount"], reverse=True)
    return rows


def _exception_counts(lines: list[dict[str, Any]]) -> dict[str, int]:
    """Every code listed, including the zeroes.

    A code missing from the map reads as "not checked"; a code at zero reads as
    "checked, nothing found". Those are different answers.
    """
    counts = {code: 0 for code in EXCEPTION_CODES}
    for line in lines:
        for code in line["exception_codes"]:
            if code in counts:
                counts[code] += 1
    return counts


def _rank(lines: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """The top lines by one measure, trimmed to the fields a turn quotes."""
    ranked = sorted(lines, key=lambda line: line[key], reverse=True)
    return [
        {
            "sku_id": line["sku_id"],
            "name": line["name"],
            "vertical_id": line["vertical_id"],
            "category_label": line["category_label"],
            "position": line["position"],
            "rop": line["rop"],
            "order_qty_sales": line["order_qty_sales"],
            "order_qty_buy": line["order_qty_buy"],
            "buy_uom": line["buy_uom"],
            "pack_factor": line["pack_factor"],
            "ordered_sales_units": line["ordered_sales_units"],
            "unit_price_ta": line["unit_price_ta"],
            "amount": line["amount"],
            "designated_vendor": line["designated_vendor"],
            "best_price_vendor": line["best_price_vendor"],
            "best_price": line["best_price"],
            "saving_vs_designated": line["saving_vs_designated"],
            "action_eligibility": line["action_eligibility"],
            "exception_codes": line["exception_codes"],
        }
        for line in ranked[: snapshot.TOP_N]
    ]


TOOLS = {"get_replenishment_detail_snapshot": get_replenishment_detail_snapshot}


__all__ = ["TOOLS", "get_replenishment_detail_snapshot"]
