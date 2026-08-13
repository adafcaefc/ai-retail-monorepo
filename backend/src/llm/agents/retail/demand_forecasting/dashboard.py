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

AGENT_ID = "retail.demand_forecasting"

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

MONTH_LABELS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# Monday first, summing to exactly 7.45 — which is `Constants` B7 and what f08
# multiplies a daily rate by. A modelled allocation of a measured total.
DOW_PROFILE = (0.85, 0.90, 0.95, 1.00, 1.15, 1.35, 1.25)

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
    "predicted_to_trend": "measured-count-modelled-membership",
    "forecast_accuracy": "typed-constant",
    "demand_trend": "typed-constant",
    "seasonality_index": "typed-constant",
    "seasonality_curve": "derived-from-gmv-profile",
    "history": "unavailable",
}


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def seasonal_indices(gmv_by_month: dict[int, float]) -> list[float]:
    """Twelve classical indices: month GMV over the series mean, times 100.

    Rounded to four places because that is what the fixture carries and what
    the chart draws; the extra digits describe a profile written twice, not a
    measurement worth more precision.
    """
    values = [gmv_by_month.get(month, 0.0) for month in range(12)]
    mean = sum(values) / len(values) if values else 0.0
    if not mean:
        return [100.0] * 12
    return [round(value / mean * 100, 4) for value in values]


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


def allocate_trending(items: list[dict], counts: dict[str, int]) -> None:
    """Mark the top N by growth in each vertical, N from the A1 sheet.

    The sheet states how many SKUs are trending per vertical but never which
    ones, so membership is modelled: rank by `growth_index` and take the count
    the workbook gives. The totals reconcile exactly; the selection is a stated
    method, and `derivation` says so.
    """
    by_vertical: dict[str, list[dict]] = {}
    for item in items:
        by_vertical.setdefault(item["vertical_id"], []).append(item)

    for vertical_id, group in by_vertical.items():
        wanted = counts.get(vertical_id, 0)
        ranked = sorted(group, key=lambda item: item["growth"], reverse=True)
        for item in ranked[:wanted]:
            item["is_trending"] = True


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()
    where, params = _scope_clause(scope, "i.vertical_id", "i.category_id")
    params["day"] = SNAPSHOT_DATE

    with get_engine().connect() as connection:
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

        store_where, store_params = _scope_clause(scope, "s.vertical_id", None)
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

        gmv = _rows(
            connection,
            f"""
            SELECT vertical_id, month_index, avg(gmv) AS gmv
            FROM {SCHEMA}.fact_gmv_monthly
            GROUP BY vertical_id, month_index
            ORDER BY vertical_id, month_index
            """,
        )

        # The A1 sheet's own KPI row per vertical, and the source of the
        # trending counts below.
        reference = agent_reference(connection, AGENT_ID)

        options = filter_options(connection)
        store_size = chain_store_size(connection)

    # How many SKUs each vertical says are trending. The sheet states the
    # count but never which ones, so membership is modelled below.
    trending_counts = {
        entry["legal_entity_id"]: int(entry.get("trending_skus", 0))
        for entry in reference
    }

    items = []
    for row in chain:
        ads = _float(row["ads"])
        items.append(
            {
                "sku_id": row["item_key"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "category_id": row["category_id"],
                "category_label": row["category_name"],
                "ads": ads,
                # f08 exactly: a week is 7.45 average days.
                "forecast_7d": ads * 7.45,
                "on_hand": _float(row["on_hand_qty"]),
                "open_po": _float(row["open_po_qty"]),
                "position": _float(row["position_qty"]),
                "rop": _float(row["rop_qty"]),
                "state": row["state"],
                "price": _float(row["unit_price"]),
                "growth": _float(row["growth_index"]),
                "is_stockout_risk": _float(row["position_qty"]) < _float(row["rop_qty"]),
                "is_trending": False,
                "signals": build_signals(row),
                "shelf_life_days": row["shelf_life_days"],
                "perishable": "Y" if row["is_perishable"] else "N",
                "base_ads": _float(row["base_ads"]),
                "seasonality": _float(row["seasonality_index"]),
                "store_size": store_size[row["vertical_id"]],
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_depth": _float(row["cannibalisation_pct"]),
                "lead_days": _float(row["lead_time_days"]),
                "safety_days": _float(row["safety_days"]),
            }
        )
    allocate_trending(items, trending_counts)

    gmv_by_vertical: dict[str, dict[int, float]] = {}
    for row in gmv:
        gmv_by_vertical.setdefault(row["vertical_id"], {})[
            int(row["month_index"])
        ] = _float(row["gmv"])

    forecast_by_store = {
        row["store_id"]: _float(row["forecast_7d"]) for row in stores
    }

    return {
        **envelope(AGENT_ID, NOTE),
        "constants": {
            "dow_sum": 7.45,
            "month_index": 6,
            "dow_profile": list(DOW_PROFILE),
            "interval_z": INTERVAL_Z,
        },
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
        "seasonality": {
            "month_labels": list(MONTH_LABELS),
            "current_month_index": 6,
            "by_legal_entity": {
                vertical_id: seasonal_indices(months)
                for vertical_id, months in sorted(gmv_by_vertical.items())
            },
        },
        "reference_by_vertical": reference,
    }


__all__ = ["SUPPORTED_FILTERS", "build"]
