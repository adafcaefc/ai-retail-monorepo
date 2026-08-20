"""Agent 1 · Demand Forecasting — the rows and live Trend aggregate.

Returns the same row shape `scripts/build_demand_forecasting_fixture.py` writes,
plus the SQL-calculated Demand Trend aggregate consumed by the live board.

WHAT THE WORKBOOK ACTUALLY COMPUTES HERE: ONE THING
---------------------------------------------------
The legacy `A1 Demand Forecasting` sheet has six columns and five of them were
typed constants:

    Forecast 7d      =SUMIFS(ENGINE_STORE!U, vertical)   <- measured
    Accuracy %       92.4 for all eight verticals        <- typed
    Trend %          5.6, 8.7, 6.9, ...                  <- superseded for card
    Stockout-risk    46, 31, 39, ...                     <- typed
    Trending SKUs    47, 39, 44, ...                     <- typed
    Seasonality idx  114, 100, 98, ...                   <- typed

`derivation` carries that distinction through to the remaining legacy tiles.
Demand Trend is now calculated from `synthetic.demand_store_sku_32w` at the
requested SKU × Store scope.

Seasonality idx is now calculated from the current v8.5 `ENGINE_STORE.Seas`
rows at SKU × Store grain. The backend applies the requested scope and returns
`AVG(Seas) × 100`; the monthly GMV curve remains a separate chart/model input.

AND `time_series_24mo` IS NOT HISTORY
------------------------------------
Its second year is byte-identical to its first in all eight verticals, so
year-on-year growth is exactly zero by construction. It is one seasonal profile
written twice. Used here as what it is — twelve classical seasonal indices per
vertical — and never drawn as an actuals line.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text

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
# Demand Trend intentionally remains on the validated 32W source for this
# slice. The two chart center lines use the additive 104W table below.
SYNTHETIC_DEMAND_TABLE = "synthetic.demand_store_sku_32w"
SYNTHETIC_DEMAND_CHART_TABLE = "synthetic.demand_store_sku_104w"
CHART_ACTUAL_WEEKS = tuple(range(52, 0, -1))
CHART_FORECAST_WEEKS = tuple(range(1, 53))

# This is the one Retail dashboard whose forecast source has both a chain-grain
# and a store-grain fact.  The chain branch remains the default so the existing
# All Stores KPI keeps its workbook/chain-net meaning; the store branch below
# can honour the same canonical `store_id` request against ENGINE_STORE rows.
SUPPORTED_FILTERS: frozenset[str] = frozenset(
    {"legal_entity_id", "category_group", "store_id", "sku"}
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
    "demand_trend": "calculated",
    "seasonality_index": "calculated-from-engine-store-seas",
    "seasonality_curve": "derived-from-gmv-profile",
    "history": "unavailable",
}

ENGINE_STORE_SEASONALITY_SOURCE = f"{SCHEMA}.temp_engine_store.[Seas]"

STORE_SCOPE_LIMITATIONS = (
    "Historical actual demand is unavailable: the loaded sales-history source "
    "has no rows, so forecast series actuals remain null. Demand Trend uses the "
    "separate synthetic SKU × Store POC table.",
    "Forecast accuracy/MAPE remains a vertical-level workbook constant; Demand "
    "Trend is calculated from the synthetic SKU × Store quantities.",
    "The Seasonality Index KPI is calculated from SKU × Store Seas rows. The "
    "separate twelve-month chart remains vertical-level because fact_gmv_monthly "
    "has no store key.",
)


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def calculate_demand_trend_pct(
    actual_4w_total: Any,
    forecast_4w_total: Any,
) -> float | None:
    """Calculate aggregate Demand Trend, returning None for no denominator."""

    actual = Decimal(str(actual_4w_total or 0))
    forecast = Decimal(str(forecast_4w_total or 0))
    if actual <= 0:
        return None
    return float((forecast / actual - Decimal("1")) * Decimal("100"))


def engine_store_seasonality_index(
    connection: Any,
    scope: DashboardScope,
) -> dict[str, Any]:
    """Calculate the header KPI from the v8.5 ENGINE_STORE Seas column.

    ``temp_engine_store`` is the SQL representation whose columns and rows
    mirror the workbook's ``ENGINE_STORE`` sheet.  ``dim_item.seasonality_index``
    contains the same values at SKU grain, but it cannot by itself honour a
    Store filter.  The header therefore reads the exact SKU × Store source and
    averages only rows in the requested scope.

    SKU search keeps the dashboard's existing ID-or-name semantics.  The name
    lookup is only needed for a non-empty search because ENGINE_STORE carries
    the workbook's SKU ID but not the item name.
    """

    clauses = ["t.[Seas] IS NOT NULL"]
    params: dict[str, Any] = {}

    if scope.legal_entity_id:
        clauses.append("t.[Vertical] = :legal_entity_id")
        params["legal_entity_id"] = scope.legal_entity_id
    if scope.category_group:
        clauses.append("t.[Cat] = :category_group")
        params["category_group"] = scope.category_group
    if scope.store_id:
        clauses.append("t.[Store] = :store_id")
        params["store_id"] = scope.store_id

    item_join = ""
    if scope.sku and scope.sku.strip():
        item_join = f"JOIN {SCHEMA}.dim_item i ON i.item_id = t.[SKU ID]"
        clauses.append(
            "(LOWER(t.[SKU ID]) LIKE :sku_pattern "
            "OR LOWER(i.name) LIKE :sku_pattern)"
        )
        params["sku_pattern"] = f"%{scope.sku.strip().lower()}%"

    row = _rows(
        connection,
        f"""
        SELECT COUNT_BIG(*) AS row_count,
               AVG(CAST(t.[Seas] AS DECIMAL(38, 12))) AS average_seas
        FROM {SCHEMA}.temp_engine_store AS t
        {item_join}
        WHERE {' AND '.join(clauses)}
        """,
        params,
    )[0]

    average = row["average_seas"]
    average_value = float(average) if average is not None else None
    return {
        "value": average_value * 100 if average_value is not None else None,
        "average_seas": average_value,
        "row_count": int(row["row_count"] or 0),
        "source": ENGINE_STORE_SEASONALITY_SOURCE,
        "grain": "sku_store",
        "aggregation": "AVG(Seas) * 100",
    }


def _sku_scope_clause(
    scope: DashboardScope,
    sku_column: str,
    name_column: str,
) -> tuple[str, dict[str, Any]]:
    """Preserve the dashboard's SKU-ID-or-name substring search semantics."""

    if not scope.sku or not scope.sku.strip():
        return "", {}
    return (
        f" AND (LOWER({sku_column}) LIKE :sku_pattern "
        f"OR LOWER({name_column}) LIKE :sku_pattern)",
        {"sku_pattern": f"%{scope.sku.strip().lower()}%"},
    )


def _demand_trend(
    connection: Any,
    scope: DashboardScope,
) -> dict[str, Any]:
    """Read Trend and its fixed actual/forecast eight-point series from SQL."""

    clauses = ["1 = 1"]
    params: dict[str, Any] = {}
    if scope.legal_entity_id:
        clauses.append("s.vertical_id = :legal_entity_id")
        params["legal_entity_id"] = scope.legal_entity_id
    if scope.category_group:
        clauses.append("d.cat = :category_group")
        params["category_group"] = scope.category_group
    if scope.store_id:
        clauses.append("d.store_id = :store_id")
        params["store_id"] = scope.store_id

    item_join = ""
    if scope.sku and scope.sku.strip():
        item_join = "JOIN retail.dim_item i ON i.item_id = d.sku_id"
        sku_where, sku_params = _sku_scope_clause(scope, "d.sku_id", "i.name")
        clauses.append(sku_where.removeprefix(" AND ").strip())
        params.update(sku_params)

    row = connection.execute(
        text(
            f"""
            SELECT
                COUNT_BIG(*) AS row_count,
                COALESCE(SUM(CAST(d.actual_w4 AS DECIMAL(38,6))), 0) AS actual_w4_total,
                COALESCE(SUM(CAST(d.actual_w3 AS DECIMAL(38,6))), 0) AS actual_w3_total,
                COALESCE(SUM(CAST(d.actual_w2 AS DECIMAL(38,6))), 0) AS actual_w2_total,
                COALESCE(SUM(CAST(d.actual_w1 AS DECIMAL(38,6))), 0) AS actual_w1_total,
                COALESCE(SUM(CAST(d.forecast_w1 AS DECIMAL(38,6))), 0) AS forecast_w1_total,
                COALESCE(SUM(CAST(d.forecast_w2 AS DECIMAL(38,6))), 0) AS forecast_w2_total,
                COALESCE(SUM(CAST(d.forecast_w3 AS DECIMAL(38,6))), 0) AS forecast_w3_total,
                COALESCE(SUM(CAST(d.forecast_w4 AS DECIMAL(38,6))), 0) AS forecast_w4_total
            FROM {SYNTHETIC_DEMAND_TABLE} AS d
            JOIN retail.dim_store AS s ON s.store_id = d.store_id
            {item_join}
            WHERE {' AND '.join(clauses)}
            """
        ),
        params,
    ).mappings().one()

    actual_series = [
        row[f"actual_w{week}_total"] or Decimal("0")
        for week in (4, 3, 2, 1)
    ]
    forecast_series = [
        row[f"forecast_w{week}_total"] or Decimal("0")
        for week in (1, 2, 3, 4)
    ]
    actual_total = sum(actual_series, Decimal("0"))
    forecast_total = sum(forecast_series, Decimal("0"))
    return {
        "trend_pct": calculate_demand_trend_pct(actual_total, forecast_total),
        "actual_4w_total": _float(actual_total),
        "forecast_4w_total": _float(forecast_total),
        "row_count": int(row["row_count"] or 0),
        "source": SYNTHETIC_DEMAND_TABLE,
        "horizon_independent": True,
        # Ordered actual W-4..W-1 followed by forecast W+1..W+4. These are
        # aggregate quantities, not row-level percentages or workbook trend.
        "sparkline": [_float(value) for value in (*actual_series, *forecast_series)],
    }


def _demand_forecast_series(
    connection: Any,
    scope: DashboardScope,
) -> dict[str, Any]:
    """Aggregate the approved 104W chart source at the selected scope.

    This is deliberately separate from ``_demand_trend``: the live Trend KPI
    remains on the currently deployed 32W source until its own migration
    slice. The chart receives all 52 actual and 52 forecast weekly quantities,
    after SQL has applied the same legal-entity/category/store/SKU filters.
    """

    clauses = ["1 = 1"]
    params: dict[str, Any] = {}
    if scope.legal_entity_id:
        clauses.append("s.vertical_id = :legal_entity_id")
        params["legal_entity_id"] = scope.legal_entity_id
    if scope.category_group:
        clauses.append("d.cat = :category_group")
        params["category_group"] = scope.category_group
    if scope.store_id:
        clauses.append("d.store_id = :store_id")
        params["store_id"] = scope.store_id

    item_join = ""
    if scope.sku and scope.sku.strip():
        item_join = "JOIN retail.dim_item i ON i.item_id = d.sku_id"
        sku_where, sku_params = _sku_scope_clause(scope, "d.sku_id", "i.name")
        clauses.append(sku_where.removeprefix(" AND ").strip())
        params.update(sku_params)

    totals = [
        "COUNT_BIG(*) AS row_count",
        *(
            f"COALESCE(SUM(CAST(d.actual_w{week} AS DECIMAL(38,6))), 0) "
            f"AS actual_w{week}_total"
            for week in CHART_ACTUAL_WEEKS
        ),
        *(
            f"COALESCE(SUM(CAST(d.forecast_w{week} AS DECIMAL(38,6))), 0) "
            f"AS forecast_w{week}_total"
            for week in CHART_FORECAST_WEEKS
        ),
    ]
    row = connection.execute(
        text(
            f"""
            SELECT {', '.join(totals)}
            FROM {SYNTHETIC_DEMAND_CHART_TABLE} AS d
            JOIN retail.dim_store AS s ON s.store_id = d.store_id
            {item_join}
            WHERE {' AND '.join(clauses)}
            """
        ),
        params,
    ).mappings().one()

    result: dict[str, Any] = {
        "source": SYNTHETIC_DEMAND_CHART_TABLE,
        "grain": "sku_store",
        "row_count": int(row["row_count"] or 0),
    }
    for column in (
        *(f"actual_w{week}" for week in CHART_ACTUAL_WEEKS),
        *(f"forecast_w{week}" for week in CHART_FORECAST_WEEKS),
    ):
        result[column] = _float(row[f"{column}_total"])
    return result


def _arch_horizon_factor(
    ads: float, base_ads: float, seasonality: float, store_size: float
) -> float:
    """Recover f01's archetype/horizon factor from the row it was applied to.

    Same recovery `inventory_risk/dashboard.py` uses, and for the same reason:
    the warehouse stores the finished `ads` and the three inputs beside it, but
    not the factor between them, so the What-If engine (which re-runs f01 from
    scratch on every lever move) has nothing to read it from unless this row
    hands it back the division.

    A zero denominator means the row carries no usable inputs; 1.0 keeps it
    arithmetically neutral rather than emitting a NaN the moment a lever moves.
    """
    denominator = base_ads * seasonality * store_size
    return ads / denominator if denominator else 1.0


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

        demand_trend = _demand_trend(connection, scope)
        demand_forecast_series = _demand_forecast_series(connection, scope)
        seasonality_index = engine_store_seasonality_index(connection, scope)

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
            "arch_horizon_factor": _arch_horizon_factor(
                ads,
                _float(row["base_ads"]),
                _float(row["seasonality_index"]),
                _float(row.get("store_size", store_size[row["vertical_id"]])),
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
        "seasonality_index": seasonality_index,
        "reference_by_vertical": reference,
        "demand_trend": demand_trend,
        "demand_forecast_series": demand_forecast_series,
    }


__all__ = [
    "SUPPORTED_FILTERS",
    "SYNTHETIC_DEMAND_TABLE",
    "SYNTHETIC_DEMAND_CHART_TABLE",
    "ENGINE_STORE_SEASONALITY_SOURCE",
    "_demand_forecast_series",
    "build",
    "calculate_demand_trend_pct",
    "engine_store_seasonality_index",
]
