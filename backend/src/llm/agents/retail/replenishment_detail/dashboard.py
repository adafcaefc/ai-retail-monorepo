"""Agent 3.1 · Replenishment Detail — the line-level sheet, read from SQL.

Its own agent, its own sheet, its own query. `retail.replenishment_proposal`
is the `Replenishment Detail` worksheet: 800 rows, one per SKU, carrying all
nineteen fields the spec's section 5 field table names. Everything this board
shows comes from there plus the two dimensions that give a code a name —
`dim_item` for the item name, category, vertical and pack factor, `dim_vendor`
for the vendor short names behind the two vendor accounts.

Deliberately *not* read here: `fact_inventory_chain_daily`. Agent 3 joins it
for the What-If parameters its simulator drives (base ADS, seasonality, promo
depth, store size) and for the retail-priced order value. This board has no
simulator and prices at cost, so joining that fact would pull in columns
nothing renders and quietly make the two boards' row counts depend on a join
that has nothing to do with either question.

**Position is reconstructed, not read** (spec section 6.1):

    Position = Qty on hand + Open PO

The sheet stores the two components and the spec's own inverse
(`Qty on hand = MAX(0, Position - Open PO)`) is what produced them upstream.
Reconstructing here rather than reading a stored Position is what lets the
inspector show the identity as a trace instead of asserting it.

**Amount prices whole packs at a per-sales-unit price** (spec section 6.5, and
finding 5 in section 17):

    Amount = Order qty buy x Pack factor x Unit price

Calling `unit_price_ta` a per-buy-UOM price is the single most available way to
be wrong on this data, and on a Crate SKU it is a twelvefold error. The grid,
the tooltips and the chat prompt all say "per sales unit" for that reason.

All 800 lines are returned, not just the reorder ones. "Reorder = YES" is the
default *view* (section 8.1) and the board applies it; making it a filter here
would leave the fill-rate denominator unreachable and give no way to answer
"what did we decide not to order".
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
    agent_reference,
    envelope,
    filter_options,
    formulas,
    get_engine,
)

AGENT_ID = "retail.replenishment_detail"

# The chain from a demand rate to a priced purchase order — this board is
# showing that chain's working, so it carries the formulas the trace quotes.
# f04 and f09 are what "Reorder = YES because Position < ROP" resolves to.
ENGINE_FORMULAS = (
    "f04-position",
    "f05-rop",
    "f06-maximum-inventory",
    "f09-order-quantity-sales-units",
    "f10-order-quantity-purchase-units",
    "f11-order-value",
)

NOTE = (
    "Workbook demonstration data, not a live ERP position. One row per SKU, "
    "800 rows: this sheet carries no store, run id or approval state, so it is "
    "a recommendation snapshot rather than an execution ledger. Unit price is "
    "per sales unit, so Amount = order qty (buy) x pack factor x unit price."
)

# Spec section 14, ordered most-blocking first — which is also the order the
# inspector lists them in. A line missing its pack factor cannot be converted
# at all; a line that fails tie-out can still be read, it just cannot be
# trusted.
EXCEPTION_CODES = (
    "MISSING_PACK_FACTOR",
    "MISSING_BUY_UOM",
    "MISSING_VENDOR",
    "MISSING_TA_PRICE",
    "INVALID_ROP_MAX",
    "NEGATIVE_INVENTORY_INPUT",
    "FORMULA_TIE_OUT_FAILED",
)

# How far Amount and Saving may drift from their recomputed value before a line
# is called out. The workbook rounds currency to whole rupiah in places, so an
# exact comparison would flag arithmetic that is correct; one rupiah is below
# the resolution anybody reads this at.
TIE_OUT_TOLERANCE_IDR = 1.0

# The read. `{where}` takes the scope clause; `:day` is the snapshot date.
# LEFT JOIN on both vendors on purpose: a line with no designated vendor is a
# MISSING_VENDOR exception this board exists to surface, and an inner join
# would drop exactly the rows worth looking at.
LINES_SQL = f"""
    SELECT p.item_key, p.qty_on_hand, p.open_po_qty, p.demand_per_day,
           p.rop_qty, p.max_qty, p.is_reorder,
           p.order_qty_sales, p.order_qty_buy, p.buy_uom,
           p.unit_price_ta, p.amount, p.best_price, p.saving_vs_designated,
           i.name, i.vertical_id, i.category_id, i.category_name,
           i.pack_factor, i.lead_time_days,
           dv.vendor_short AS designated_short,
           bv.vendor_short AS best_short
    FROM {SCHEMA}.replenishment_proposal p
    JOIN {SCHEMA}.dim_item i ON i.item_id = p.item_key
    LEFT JOIN {SCHEMA}.dim_vendor dv
      ON dv.vendor_account = p.designated_vendor
    LEFT JOIN {SCHEMA}.dim_vendor bv
      ON bv.vendor_account = p.best_price_vendor
    JOIN {SCHEMA}.dim_vertical vt ON vt.vertical_id = i.vertical_id
    WHERE p.as_of_date = :day{{where}}
    -- The workbook's own order: vertical first, SKU within it. Alphabetical
    -- would open the board on Digital, which is not where a planner starts.
    ORDER BY vt.sort_order, p.item_key
"""


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def ordered_sales_units(line: dict[str, Any]) -> float:
    """Sales units a whole-pack purchase order actually brings in.

    Spec section 6.4. Not `order_qty_sales`: the buy quantity is a ceiling, so
    the order lands at or above the requirement that raised it.
    """
    return line["order_qty_buy"] * line["pack_factor"]


def rounding_uplift(line: dict[str, Any]) -> float:
    """Sales units bought above the raw `Max - Position` requirement.

    Real stock and real money, which is why it is its own column rather than an
    unexplained reason the cost line fails to divide back into the requirement
    (spec section 17, finding 6).
    """
    return ordered_sales_units(line) - line["order_qty_sales"]


def saving_pct(line: dict[str, Any]) -> float:
    """Saving as a share of the line's amount, guarded at zero amount.

    A line with nothing to order has no denominator. Returning 0.0 rather than
    omitting the field keeps the column numeric, so sorting by it does not have
    to special-case a hole.
    """
    amount = line["amount"]
    return (line["saving_vs_designated"] / amount * 100.0) if amount else 0.0


def exception_codes(line: dict[str, Any]) -> list[str]:
    """Why a line cannot be believed or acted on, per spec section 14.

    The tie-out checks are the two worth having. They recompute Amount and
    Saving from the inputs on the row and compare against what the sheet
    stored, so a line whose price basis has been misread stops being invisible.
    Both price the *rounded* quantity — pricing the unrounded requirement is
    the twelvefold error the module docstring names.
    """
    codes: list[str] = []
    pack_factor = line["pack_factor"]
    order_sales = line["order_qty_sales"]
    order_buy = line["order_qty_buy"]

    if pack_factor <= 0 and order_sales > 0:
        codes.append("MISSING_PACK_FACTOR")
    if _is_blank(line["buy_uom"]) and order_buy > 0:
        codes.append("MISSING_BUY_UOM")
    if _is_blank(line["designated_vendor"]):
        codes.append("MISSING_VENDOR")
    if line["unit_price_ta"] <= 0 and order_sales > 0:
        codes.append("MISSING_TA_PRICE")
    if line["rop"] < 0 or line["max"] < 0 or line["max"] < line["rop"]:
        codes.append("INVALID_ROP_MAX")
    if line["qty_on_hand"] < 0 or line["open_po"] < 0 or order_sales < 0:
        codes.append("NEGATIVE_INVENTORY_INPUT")

    if pack_factor > 0 and line["unit_price_ta"] > 0:
        units = ordered_sales_units(line)
        expected_amount = units * line["unit_price_ta"]
        expected_saving = units * (line["unit_price_ta"] - line["best_price"])
        drifted = (
            abs(expected_amount - line["amount"]) > TIE_OUT_TOLERANCE_IDR
            or abs(expected_saving - line["saving_vs_designated"])
            > TIE_OUT_TOLERANCE_IDR
        )
        if drifted:
            codes.append("FORMULA_TIE_OUT_FAILED")

    return codes


def action_eligibility(line: dict[str, Any], codes: list[str]) -> str:
    """`ELIGIBLE` only when every spec section 10.1 condition holds.

    `NO_ORDER` stays distinct from `BLOCKED`. A line with nothing to buy is not
    a data problem, and merging the two would drop several hundred healthy SKUs
    into an exception queue nobody could then read.
    """
    if not line["is_reorder"] or line["order_qty_sales"] <= 0:
        return "NO_ORDER"
    if codes or line["order_qty_buy"] <= 0:
        return "BLOCKED"
    return "ELIGIBLE"


def build_lines(rows: list[dict]) -> list[dict[str, Any]]:
    """One detail line per SKU: the sheet's nineteen fields plus the working.

    Pure, so the reorder rule, the UOM conversion, the tie-out checks and the
    eligibility rules can all be tested against the spec's worked example
    (section 13) without a database.
    """
    lines = []
    for row in rows:
        qty_on_hand = _float(row["qty_on_hand"])
        open_po = _float(row["open_po_qty"])
        # Spec 6.1. The sheet stores the components; Position is the identity
        # over them, and showing it as a derivation is what the inspector's
        # inventory-basis section explains.
        position = qty_on_hand + open_po
        rop = _float(row["rop_qty"])
        max_qty = _float(row["max_qty"])
        pack_factor = _float(row["pack_factor"])

        line: dict[str, Any] = {
            # -- identity ---------------------------------------------------
            "sku_id": row["item_key"],
            "name": row["name"],
            "category_id": row["category_id"],
            "category_label": row["category_name"],
            "vertical_id": row["vertical_id"],
            # -- inventory basis --------------------------------------------
            "qty_on_hand": qty_on_hand,
            "open_po": open_po,
            "position": position,
            "demand_per_day": _float(row["demand_per_day"]),
            "rop": rop,
            "max": max_qty,
            # Read from the sheet rather than recomputed as `position < rop`.
            # The two must agree, and the tie-out check below is what says so
            # — deriving it here instead would make that check tautological.
            "is_reorder": bool(row["is_reorder"]),
            # -- order conversion -------------------------------------------
            "order_qty_sales": _float(row["order_qty_sales"]),
            "buy_uom": row["buy_uom"],
            "pack_factor": pack_factor,
            "order_qty_buy": _float(row["order_qty_buy"]),
            # -- vendor and price -------------------------------------------
            "designated_vendor": row["designated_short"],
            "unit_price_ta": _float(row["unit_price_ta"]),
            "amount": _float(row["amount"]),
            "best_price_vendor": row["best_short"],
            "best_price": _float(row["best_price"]),
            "saving_vs_designated": _float(row["saving_vs_designated"]),
            "lead_time_days": _float(row["lead_time_days"]),
        }

        codes = exception_codes(line)
        line.update(
            {
                "ordered_sales_units": ordered_sales_units(line),
                "rounding_uplift": rounding_uplift(line),
                "saving_pct": saving_pct(line),
                # The requirement before the pack ceiling, so the grid can show
                # both figures the spec asks for side by side.
                "required_qty_sales": max(0.0, max_qty - position),
                "packs_required_exact": (
                    line["order_qty_sales"] / pack_factor if pack_factor > 0 else 0.0
                ),
                "has_alternate_vendor": bool(
                    line["best_price_vendor"]
                    and line["best_price_vendor"] != line["designated_vendor"]
                    and line["saving_vs_designated"] > 0
                ),
                "exception_codes": codes,
                "action_eligibility": action_eligibility(line, codes),
            }
        )
        lines.append(line)
    return lines


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()
    where, params = _scope_clause(scope, "i.vertical_id", "i.category_id")
    params["day"] = SNAPSHOT_DATE

    with get_engine().connect() as connection:
        rows = _rows(connection, LINES_SQL.format(where=where), params)

        # Every quote on file for the SKUs in scope. The line carries only the
        # designated and the best price; the inspector's vendor comparison
        # needs the candidates in between to show what the choice was between.
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

        # Agreement validity and currency, which the inspector states beside
        # the price. Read with a DISTINCT rather than assumed, and raising
        # rather than picking one: presenting a single SKU's terms as
        # everyone's is the position-dependent matching the spec warns about
        # (section 17, finding 3).
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
                "expected 1. Currency and validity have to move onto the quote "
                "rows before this board can show them per line."
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
        # The agent's own KPI sheet, per vertical. Nothing renders it; it is
        # what every figure above is reconciled against.
        reference = agent_reference(connection, AGENT_ID)

    # This sheet is SKU-grain with no store column (spec section 17, finding 1)
    # and it filters by vendor and buy UOM rather than by inventory state.
    # Offering either dropdown would be offering a control that cannot narrow
    # anything. The vendor and UOM options are derived from the rows.
    options.pop("stores", None)
    options.pop("states", None)

    return {
        **envelope(AGENT_ID, NOTE),
        "formulas": formulas(ENGINE_FORMULAS),
        "exception_codes": list(EXCEPTION_CODES),
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


__all__ = [
    "EXCEPTION_CODES",
    "SUPPORTED_FILTERS",
    "action_eligibility",
    "build",
    "build_lines",
    "exception_codes",
    "ordered_sales_units",
    "rounding_uplift",
    "saving_pct",
]
