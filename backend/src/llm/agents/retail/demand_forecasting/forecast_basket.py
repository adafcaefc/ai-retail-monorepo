"""Read-only Demand Forecasting forecast basket at Store x SKU grain.

The dashboard payload intentionally keeps its existing source split: the
unfiltered board uses chain-SKU rows while a selected Store uses
``fact_inventory_daily`` rows.  The basket is different by contract.  It is
always one row per Store x SKU, because Position, ROP, Max and the resulting
Suggestion are local replenishment decisions.

This module owns only the additive basket read contract.  It does not create
handoffs, mutate action state, write an order, or read synthetic demand/inbound
tables.
"""

from __future__ import annotations

from math import fsum, isclose, isfinite
from typing import Any

from src.formulas.expression import evaluate, parse
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    DOW_SUM,
    SCHEMA,
    SNAPSHOT_DATE,
    _rows,
    _scope_clause,
    formulas,
    get_engine,
)
from src.llm.agents.retail.replenishment.dashboard import route_for


AGENT_ID = "retail.demand_forecasting"
BASKET_SOURCE = f"{SCHEMA}.fact_inventory_daily.forecast_7d"
BASKET_GRAIN = "sku_store"
FORECAST_FORMULA_ID = "f08-forecast-7-days"
BASKET_FILTERS: tuple[str, ...] = (
    "legal_entity_id",
    "category_group",
    "store_id",
    "sku",
)
BASKET_QUERY_PARAMS = frozenset(BASKET_FILTERS)

# The dashboard builders and fixture comparison use a relative 1e-9 numeric
# tolerance.  The absolute floor only prevents tiny values from failing due to
# binary conversion when the sum itself is near zero.
RECONCILIATION_REL_TOL = 1e-9
RECONCILIATION_ABS_TOL = 1e-6


class ForecastBasketError(ValueError):
    """Base class for a basket that cannot safely be returned."""


class ForecastBasketIntegrityError(ForecastBasketError):
    """The source rows violate the Store x SKU or provenance contract."""


class ForecastBasketReconciliationError(ForecastBasketError):
    """The basket total does not reconcile to the Demand KPI."""


def _finite_number(value: Any, field: str, key: str | None = None) -> float:
    """Return a JSON-safe number or name the offending source field."""

    if isinstance(value, bool) or value is None:
        location = f" for {key}" if key else ""
        raise ForecastBasketIntegrityError(
            f"Forecast basket source field {field}{location} is not numeric"
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        location = f" for {key}" if key else ""
        raise ForecastBasketIntegrityError(
            f"Forecast basket source field {field}{location} is not numeric"
        ) from error
    if not isfinite(number):
        location = f" for {key}" if key else ""
        raise ForecastBasketIntegrityError(
            f"Forecast basket source field {field}{location} is not finite"
        )
    return number


def _as_bool(value: Any) -> bool:
    """Normalise Azure SQL BIT values and the workbook's Y/N flags."""

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _required_text(value: Any, field: str) -> str:
    if value is None or not str(value).strip():
        raise ForecastBasketIntegrityError(
            f"Forecast basket source field {field} is missing"
        )
    return str(value)


def _sku_filter(
    scope: DashboardScope,
    sku_column: str,
    name_column: str,
) -> tuple[str, dict[str, Any]]:
    """Build the existing case-insensitive ID/name substring predicate.

    The column names are module constants, while the search value is always a
    bound parameter.  This preserves the Demand dashboard's current
    ``SKU ID`` or item-name substring semantics without interpolating input.
    """

    if not scope.sku or not scope.sku.strip():
        return "", {}
    return (
        f" AND (LOWER({sku_column}) LIKE :sku_pattern "
        f"OR LOWER({name_column}) LIKE :sku_pattern)",
        {"sku_pattern": f"%{scope.sku.strip().lower()}%"},
    )


def _basket_query(scope: DashboardScope) -> tuple[str, dict[str, Any]]:
    where, params = _scope_clause(
        scope,
        "s.vertical_id",
        "i.category_id",
        "s.store_id",
    )
    sku_where, sku_params = _sku_filter(scope, "f.item_key", "i.name")
    params.update(sku_params)
    params["snapshot_date"] = SNAPSHOT_DATE

    return (
        f"""
        SELECT
            f.store_key AS store_id,
            s.name AS store_name,
            f.item_key AS sku_id,
            i.name AS item_name,
            i.category_id AS category_id,
            i.category_name AS category,
            f.ads AS ads,
            f.forecast_7d AS forecast_7d,
            f.rop_qty AS rop,
            f.max_qty AS max_qty,
            f.position_qty AS position,
            i.lead_time_days AS lead_time_days,
            i.is_perishable AS perishable,
            i.is_promo_eligible AS promo,
            i.is_viral AS viral,
            i.growth_index AS growth_index,
            COALESCE(v.vendor_short, v.vendor_name, i.vendor_account) AS vendor,
            f.import_batch_id AS import_batch_id,
            f.cal_date AS snapshot_date
        FROM {SCHEMA}.fact_inventory_daily AS f
        JOIN {SCHEMA}.dim_store AS s
          ON s.store_id = f.store_key
        JOIN {SCHEMA}.dim_item AS i
          ON i.item_id = f.item_key
        LEFT JOIN {SCHEMA}.dim_vendor AS v
          ON v.vendor_account = i.vendor_account
        WHERE f.cal_date = :snapshot_date{where}{sku_where}
        ORDER BY f.store_key, f.item_key
        """,
        params,
    )


def _dashboard_forecast_query(scope: DashboardScope) -> tuple[str, dict[str, Any]]:
    """Use the same source branch that feeds the current Demand KPI.

    The existing dashboard exposes chain-SKU rows for All Stores and
    Store-SKU rows for a selected Store.  This query only reads their ``ads``
    inputs; Python evaluates the live f08 catalogue expression below.  It
    never supplies Position, ROP, Max or Suggestion.
    """

    params: dict[str, Any] = {"snapshot_date": SNAPSHOT_DATE}
    if scope.store_id:
        where, scope_params = _scope_clause(
            scope,
            "s.vertical_id",
            "i.category_id",
            "s.store_id",
        )
        sku_where, sku_params = _sku_filter(scope, "f.item_key", "i.name")
        source = f"""
            SELECT f.ads AS ads
            FROM {SCHEMA}.fact_inventory_daily AS f
            JOIN {SCHEMA}.dim_store AS s
              ON s.store_id = f.store_key
            JOIN {SCHEMA}.dim_item AS i
              ON i.item_id = f.item_key
            WHERE f.cal_date = :snapshot_date{where}{sku_where}
        """
    else:
        where, scope_params = _scope_clause(
            scope,
            "i.vertical_id",
            "i.category_id",
        )
        sku_where, sku_params = _sku_filter(scope, "c.item_key", "i.name")
        source = f"""
            SELECT c.ads AS ads
            FROM {SCHEMA}.fact_inventory_chain_daily AS c
            JOIN {SCHEMA}.dim_item AS i
              ON i.item_id = c.item_key
            WHERE c.cal_date = :snapshot_date{where}{sku_where}
        """

    params.update(scope_params)
    params.update(sku_params)
    return source, params


def _source_batch_id(rows: list[dict]) -> int | None:
    """Return one batch id, rejecting a response mixed across imports."""

    batch_ids = {
        row.get("import_batch_id")
        for row in rows
        if row.get("import_batch_id") is not None
    }
    if len(batch_ids) > 1:
        values = ", ".join(sorted(str(value) for value in batch_ids))
        raise ForecastBasketIntegrityError(
            f"Forecast basket source spans multiple import batches: {values}"
        )
    if not batch_ids:
        return None
    value = next(iter(batch_ids))
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ForecastBasketIntegrityError(
            f"Forecast basket import batch id is invalid: {value!r}"
        ) from error


def _signals(row: dict, below_rop: bool) -> list[str]:
    """Use the existing Demand badges plus the numeric reorder predicate."""

    signals: list[str] = []
    if below_rop:
        signals.append("below_rop")
    if _as_bool(row.get("viral")):
        signals.append("viral")
    if _as_bool(row.get("promo")):
        signals.append("promo")
    raw_growth = row.get("growth_index")
    growth = (
        0.0
        if raw_growth is None
        else _finite_number(raw_growth, "growth_index")
    )
    if growth > 1:
        signals.append("growth")
    return signals


def _basket_row(row: dict) -> dict[str, Any]:
    """Convert one live fact row to the public basket row contract."""

    store_id = _required_text(row.get("store_id"), "store_id")
    sku_id = _required_text(row.get("sku_id"), "sku_id")
    position = _finite_number(row.get("position"), "position", sku_id)
    rop = _finite_number(row.get("rop"), "rop", sku_id)
    maximum = _finite_number(row.get("max_qty"), "max", sku_id)
    forecast = _finite_number(row.get("forecast_7d"), "forecast_7d", sku_id)
    ads = _finite_number(row.get("ads"), "ads", sku_id)
    lead_time_days = _finite_number(
        row.get("lead_time_days"), "lead_time_days", sku_id
    )

    below_rop = position < rop
    suggestion = max(0.0, maximum - position) if below_rop else 0.0

    return {
        "store_id": store_id,
        "store_name": _required_text(row.get("store_name"), "store_name"),
        "sku_id": sku_id,
        "item_name": _required_text(row.get("item_name"), "item_name"),
        "category_id": row.get("category_id"),
        "category": row.get("category"),
        "target": {
            "value": ads,
            "unit": "units/day",
            "basis": "ads",
        },
        "forecast_7d": forecast,
        "rop": rop,
        "max": maximum,
        "position": position,
        "suggestion": suggestion,
        "signal": _signals(row, below_rop),
        "route": route_for(lead_time_days),
        "lead_time_days": lead_time_days,
        "eta": None,
        "eta_status": "unavailable",
        "perishable": _as_bool(row.get("perishable")),
        "vendor": row.get("vendor"),
    }


def _validate_unique(rows: list[dict[str, Any]]) -> None:
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["store_id"], row["sku_id"])
        if key in seen:
            store_id, sku_id = key
            raise ForecastBasketIntegrityError(
                "Duplicate Store x SKU rows in forecast basket source: "
                f"{store_id} + {sku_id}"
            )
        seen.add(key)


def _forecast_kpi(ads_rows: list[dict], forecast_ast: tuple) -> float:
    values: list[float] = []
    for row in ads_rows:
        ads = _finite_number(row.get("ads"), "ads")
        value = evaluate(
            forecast_ast,
            {"ads": ads, "week_factor": DOW_SUM},
        )
        values.append(_finite_number(value, FORECAST_FORMULA_ID))
    return fsum(values)


def _scope_payload(scope: DashboardScope) -> dict[str, str | None]:
    return {
        name: (
            getattr(scope, name).strip()
            if isinstance(getattr(scope, name), str)
            and getattr(scope, name).strip()
            else None
        )
        for name in BASKET_FILTERS
    }


def _build_with_connection(
    connection: Any,
    scope: DashboardScope,
) -> dict[str, Any]:
    basket_sql, basket_params = _basket_query(scope)
    source_rows = _rows(connection, basket_sql, basket_params)
    rows = [_basket_row(row) for row in source_rows]
    _validate_unique(rows)

    batch_id = _source_batch_id(source_rows)
    dashboard_sql, dashboard_params = _dashboard_forecast_query(scope)
    dashboard_rows = _rows(connection, dashboard_sql, dashboard_params)

    catalogue = formulas((FORECAST_FORMULA_ID,))
    try:
        forecast_ast = parse(catalogue[FORECAST_FORMULA_ID])
    except KeyError as error:
        raise ForecastBasketIntegrityError(
            f"retail.formula is missing {FORECAST_FORMULA_ID}"
        ) from error

    basket_forecast = fsum(row["forecast_7d"] for row in rows)
    dashboard_forecast = _forecast_kpi(dashboard_rows, forecast_ast)
    reconciles = isclose(
        basket_forecast,
        dashboard_forecast,
        rel_tol=RECONCILIATION_REL_TOL,
        abs_tol=RECONCILIATION_ABS_TOL,
    )
    if not reconciles:
        raise ForecastBasketReconciliationError(
            "Forecast basket does not reconcile to Demand Forecasting "
            f"Forecast Next 7 Days KPI for scope {_scope_payload(scope)}: "
            f"basket={basket_forecast}, dashboard={dashboard_forecast}"
        )

    suggestion_units = fsum(row["suggestion"] for row in rows)
    action_row_count = sum(row["suggestion"] > 0 for row in rows)

    return {
        "schema_version": 1,
        "agent": AGENT_ID,
        "as_of": SNAPSHOT_DATE,
        "scope": _scope_payload(scope),
        "grain": BASKET_GRAIN,
        "source": BASKET_SOURCE,
        "source_import_batch_id": batch_id,
        "row_count": len(rows),
        "action_row_count": action_row_count,
        "dashboard_forecast_7d": dashboard_forecast,
        "basket_forecast_7d": basket_forecast,
        "reconciles": True,
        "suggestion_units": suggestion_units,
        "rows": rows,
    }


def build_forecast_basket(
    scope: DashboardScope | None = None,
    *,
    connection: Any | None = None,
) -> dict[str, Any]:
    """Build one complete, baseline Store x SKU forecast basket.

    ``connection`` is injectable for focused backend tests.  Production calls
    use the shared read-only SQLAlchemy engine and execute no writes.
    """

    scope = scope or DashboardScope()
    if connection is not None:
        return _build_with_connection(connection, scope)
    with get_engine().connect() as live_connection:
        return _build_with_connection(live_connection, scope)


__all__ = [
    "AGENT_ID",
    "BASKET_FILTERS",
    "BASKET_GRAIN",
    "BASKET_QUERY_PARAMS",
    "BASKET_SOURCE",
    "ForecastBasketError",
    "ForecastBasketIntegrityError",
    "ForecastBasketReconciliationError",
    "RECONCILIATION_ABS_TOL",
    "RECONCILIATION_REL_TOL",
    "_basket_row",
    "_basket_query",
    "_dashboard_forecast_query",
    "_forecast_kpi",
    "_validate_unique",
    "build_forecast_basket",
]
