"""Agent 1 · Demand Forecasting — the rows, read from Postgres.

Returns the same shape `scripts/build_demand_forecasting_fixture.py` writes, so
the board's selectors run over it unchanged.

WHAT THE WORKBOOK ACTUALLY COMPUTES HERE: ONE THING
---------------------------------------------------
The `A1 Demand Forecasting` sheet has six columns and five of them are typed
constants:

    Forecast 7d      =SUMIFS(ENGINE_STORE!U, vertical)   <- measured
    Accuracy %       92.4 for all eight verticals        <- typed
    Trend %          5.6, 8.7, 6.9, ...                  <- typed
    Stockout-risk    46, 31, 39, ...                     <- typed
    Trending SKUs    47, 39, 44, ...                     <- typed
    Seasonality idx  114, 100, 98, ...                   <- typed

`derivation` carries that distinction through to the tiles, so a reader can
tell a backtest from a demo constant. Accuracy in particular is 92.4 in every
vertical, which no real measurement ever is.

Seasonality idx is the one exception: this board reports the derived figure
(`warehouse.seasonality()`, catalogue formula `fc01-seasonal-index`), not the
sheet's typed 114/100/98/... — see `docs/RETAIL_FORMULA_SOURCES.md` for both
numbers side by side.

AND `time_series_24mo` IS NOT HISTORY
------------------------------------
Its second year is byte-identical to its first in all eight verticals, so
year-on-year growth is exactly zero by construction. It is one seasonal profile
written twice. Used here as what it is — twelve classical seasonal indices per
vertical — and never drawn as an actuals line.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    SCHEMA,
    SNAPSHOT_DATE,
    _rows,
    _scope_clause,
    agent_reference,
    chain_store_size,
    constants,
    envelope,
    filter_options,
    formulas,
    get_engine,
    seasonality,
)

AGENT_ID = "retail.demand_forecasting"

# This is the one Retail dashboard whose forecast source has both a chain-grain
# and a store-grain fact.  The chain branch remains the default so the existing
# All Stores KPI keeps its workbook/chain-net meaning; the store branch below
# can honour the same canonical `store_id` request against ENGINE_STORE rows.
SUPPORTED_FILTERS: frozenset[str] = frozenset(
    {"legal_entity_id", "category_group", "store_id"}
)

ENGINE_FORMULAS = (
    "f01-ads-per-store",
    "f03-open-po-per-store",
    "f04-position",
    "f05-rop",
    "f06-maximum-inventory",
    "f07-inventory-state",
    "f08-forecast-7-days",
    "f20-days-of-supply",
)

# 90% two-sided normal quantile. With the workbook's 92.4% accuracy this puts
# the one-day band at +/-12.5%, which is where the A1 spec's flat "+/-12%"
# comes from — stated this way it widens with horizon, as an interval must.
INTERVAL_Z = 1.645

NOTE = (
    "Workbook demonstration data, not a live ERP position. The workbook holds "
    "no sales history, so the forecast starts at today rather than back-casting "
    "a line that would read as measurement."
)

# What each headline figure actually is. The board prints these on the tiles,
# so a reader can tell a computed number from one somebody keyed into a cell.
DERIVATION = {
    "forecast_next_7d": "measured",
    "stockout_risk_skus": "measured",
    "predicted_to_trend": "measured-formula",
    "forecast_accuracy": "typed-constant",
    "demand_trend": "typed-constant",
    "seasonality_index": "derived-from-gmv-profile",
    "seasonality_curve": "derived-from-gmv-profile",
    "history": "unavailable",
}

STORE_SCOPE_LIMITATIONS = (
    "Historical actual demand is unavailable: the loaded sales-history source "
    "has no rows, so forecast series actuals remain null.",
    "Forecast accuracy/MAPE and demand trend remain vertical-level workbook "
    "constants; no Store-grain backtest source is loaded.",
    "Seasonality remains vertical-level: fact_gmv_monthly has no store key, "
    "so the selected Store uses its owning vertical's curve.",
)


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def build_signals(row: dict) -> list[str]:
    """The badges A1 puts on a SKU.

    Ordered viral, promo, growth — loudest first. Growth is the commonest by
    far (355 SKUs carry it alone), so leading with it would bury the two that
    single a product out.
    """
    signals = []
    if row["is_viral"]:
        signals.append("viral")
    if row["is_promo_eligible"]:
        signals.append("promo")
    if _float(row["growth_index"]) > 1:
        signals.append("growth")
    return signals


def is_trending(is_viral: bool, growth_index: float) -> bool:
    """The A1 spec's own test: `count(viral OR growth>1.25)`.

    A per-row predicate, not a rank+quota allocation against the sheet's
    vertical-wide `Trending SKUs` count -- it composes correctly under any
    scope filter (category, store, vertical) because it never depends on how
    many other rows are in the result set. It still reconciles exactly to
    the workbook's typed count at vertical grain (see
    `scripts/build_demand_forecasting_fixture.py`'s `reconcile()`); it is no
    longer *forced* to.
    """
    return bool(is_viral) or growth_index > 1.25


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()

    with get_engine().connect() as connection:
        if scope.store_id:
            # ENGINE_STORE is the real store x SKU source.  It carries the
            # workbook's own f08 forecast_7d, inventory position and inbound
            # quantities at the same grain, so all downstream calculations run
            # over the selected Store's inputs rather than a filtered response.
            where, params = _scope_clause(
                scope, "s.vertical_id", "i.category_id", "s.store_id"
            )
            params["day"] = SNAPSHOT_DATE
            chain = _rows(
                connection,
                f"""
                SELECT f.item_key, f.ads, f.forecast_7d,
                       f.on_hand_qty, f.open_po_qty, f.position_qty, f.rop_qty,
                       f.state, i.price AS unit_price,
                       i.name, i.vertical_id, i.category_id, i.category_name,
                       i.is_perishable, i.shelf_life_days, i.base_ads,
                       i.seasonality_index, i.lead_time_days, i.safety_days,
                       i.growth_index, i.is_promo_eligible, i.cannibalisation_pct,
                       i.is_viral, s.store_id, s.size_index AS store_size
                FROM {SCHEMA}.fact_inventory_daily f
                JOIN {SCHEMA}.dim_store s ON s.store_id = f.store_key
                JOIN {SCHEMA}.dim_item i ON i.item_id = f.item_key
                JOIN {SCHEMA}.dim_vertical vt ON vt.vertical_id = i.vertical_id
                WHERE f.cal_date = :day{where}
                -- The workbook's own order: vertical first, SKU within it.
                ORDER BY vt.sort_order, f.item_key
                """,
                params,
            )
        else:
            where, params = _scope_clause(scope, "i.vertical_id", "i.category_id")
            params["day"] = SNAPSHOT_DATE
            chain = _rows(
                connection,
                f"""
                SELECT c.item_key, c.ads, c.on_hand_qty, c.open_po_qty,
                       c.position_qty, c.rop_qty, c.state, c.unit_price,
                       i.name, i.vertical_id, i.category_id, i.category_name,
                       i.is_perishable, i.shelf_life_days, i.base_ads,
                       i.seasonality_index, i.lead_time_days, i.safety_days,
                       i.growth_index, i.is_promo_eligible, i.cannibalisation_pct,
                       i.is_viral
                FROM {SCHEMA}.fact_inventory_chain_daily c
                JOIN {SCHEMA}.dim_item i ON i.item_id = c.item_key
                JOIN {SCHEMA}.dim_vertical vt ON vt.vertical_id = i.vertical_id
                WHERE c.cal_date = :day{where}
                -- The workbook's own order: vertical first, SKU within it.
                -- Alphabetical would open every board on Digital.
                ORDER BY vt.sort_order, c.item_key
                """,
                params,
            )

        store_where, store_params = _scope_clause(
            scope, "s.vertical_id", None, "s.store_id"
        )
        store_params["day"] = SNAPSHOT_DATE
        stores = _rows(
            connection,
            f"""
            SELECT s.store_id, s.name, s.vertical_id, s.cluster, s.channel,
                   count(*)                                AS sku_count,
                   -- ENGINE_STORE's own f08 column, read rather than derived.
                   coalesce(sum(f.forecast_7d), 0)         AS forecast_7d
            FROM {SCHEMA}.fact_inventory_daily f
            JOIN {SCHEMA}.dim_store s ON s.store_id = f.store_key
            WHERE f.cal_date = :day{store_where}
            GROUP BY s.store_id, s.name, s.vertical_id, s.cluster, s.channel
            ORDER BY s.store_id
            """,
            store_params,
        )

        # Shared with Inventory Risk's projection so the two boards cannot
        # disagree about what next month looks like.
        seasonal = seasonality(connection)

        # The A1 sheet's own KPI row per vertical. `trending_skus` is still
        # surfaced to the frontend for its tooltip/comparison label, but no
        # longer used to compute membership -- see `is_trending()`.
        reference = agent_reference(connection, AGENT_ID)

        options = filter_options(connection)
        store_size = chain_store_size(connection)

    items = []
    for row in chain:
        ads = _float(row["ads"])
        item = {
            "sku_id": row["item_key"],
            "name": row["name"],
            "vertical_id": row["vertical_id"],
            "category_id": row["category_id"],
            "category_label": row["category_name"],
            "ads": ads,
            # All Stores uses the chain-net f08 equivalent already used by
            # the existing board.  Store scope reads ENGINE_STORE's own
            # f08 value, whose grain is store x SKU.
            "forecast_7d": _float(row.get("forecast_7d", ads * 7.45)),
            "on_hand": _float(row["on_hand_qty"]),
            "open_po": _float(row["open_po_qty"]),
            "position": _float(row["position_qty"]),
            "rop": _float(row["rop_qty"]),
            "state": row["state"],
            "price": _float(row["unit_price"]),
            "growth": _float(row["growth_index"]),
            "is_stockout_risk": _float(row["position_qty"]) < _float(row["rop_qty"]),
            "is_trending": is_trending(row["is_viral"], _float(row["growth_index"])),
            "signals": build_signals(row),
            "shelf_life_days": row["shelf_life_days"],
            "perishable": "Y" if row["is_perishable"] else "N",
            "base_ads": _float(row["base_ads"]),
            "seasonality": _float(row["seasonality_index"]),
            "store_size": _float(
                row.get("store_size", store_size[row["vertical_id"]])
            ),
            "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
            "promo_depth": _float(row["cannibalisation_pct"]),
            "lead_days": _float(row["lead_time_days"]),
            "safety_days": _float(row["safety_days"]),
        }
        if row.get("store_id"):
            item["store_id"] = row["store_id"]
        items.append(item)

    forecast_by_store = {
        row["store_id"]: _float(row["forecast_7d"]) for row in stores
    }

    return {
        **envelope(AGENT_ID, NOTE),
        "scope": scope.as_query(),
        "scope_limitations": list(STORE_SCOPE_LIMITATIONS) if scope.store_id else [],
        "constants": {**constants(), "interval_z": INTERVAL_Z},
        "derivation": DERIVATION,
        "formulas": formulas(ENGINE_FORMULAS),
        "filter_options": {
            key: options[key] for key in ("legal_entities", "categories", "stores")
        },
        "items": items,
        "stores": [
            {
                "store_id": row["store_id"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "cluster": row["cluster"],
                "channel": row["channel"],
                "sku_count": row["sku_count"],
                "forecast_7d": forecast_by_store[row["store_id"]],
            }
            for row in stores
        ],
        "seasonality": seasonal,
        "reference_by_vertical": reference,
    }


__all__ = ["SUPPORTED_FILTERS", "build"]
