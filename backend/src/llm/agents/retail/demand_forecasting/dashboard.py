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

from src.formulas.expression import evaluate, parse
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    DOW_SUM,
    REPLENISH_STATES,
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
    "fc10-trending-sku",
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


def build_item(row: dict, vertical_size: float, asts: dict[str, tuple]) -> dict:
    """One SKU row, every derived figure evaluated from the catalogue.

    NOTHING DERIVED HERE IS TYPED HERE. `ads`, `forecast_7d`, `position`,
    `rop`, `dos`, `state`, `is_stockout_risk` and `is_trending` are each the
    answer of a `retail.formula` expression, run through
    `src.formulas.expression` in the order the rules consume one another --
    the same order, from the same catalogue, that `data/engine.js` runs in the
    browser when a What-If lever moves. This function supplies parameters and
    decides that order; it resolves no rule.

    It used to read the stored answers instead: `ads`, `position_qty`,
    `rop_qty` and `state` came straight off the fact table, `forecast_7d` was
    the literal `ads * 7.45` (f08's arithmetic retyped, and on the chain
    branch the stored column does not even exist), `is_stockout_risk` was a
    `position < rop` comparison, and `is_trending` was `viral or growth >
    1.25`. Those answers are the workbook's own and they still agree with the
    catalogue exactly -- the fixture builder's `verify_engine_chain()` proves
    it over all 800 rows -- so this moves no number on screen. What it changes
    is what happens after someone edits a rule: `retail.formula` is read live
    and uncached precisely so a correction takes effect at once, and that
    promise previously held only for the What-If path. Editing f08 and
    watching the baseline tile keep the old figure until a lever moved -- then
    jump -- is the bug this ends.

    THE STOCKOUT FLAG FOLLOWS f07, NOT A SECOND COMPARISON. f07 assigns
    `Stockout` below `0.6 x ROP` and `Low` below ROP, so those two states ARE
    the rows below the reorder point, by construction. Reading them off the
    state cannot drift from f07; a separate `position < rop` can. Both give
    345 of 800 on the current dataset, with no row disagreeing.
    """
    base_ads = _float(row["base_ads"])
    seasonality_index = _float(row["seasonality_index"])
    store_size = _float(row.get("store_size", vertical_size))
    promo_eligible = "Y" if row["is_promo_eligible"] else "N"
    perishable = "Y" if row["is_perishable"] else "N"
    growth = _float(row["growth_index"])

    # f01's archetype/horizon multiplier, preferred from `dim_item` and
    # recovered from the stored `ads` only where that column is still NULL.
    # NOT a 1.0 fallback: 1.0 is f01's arithmetic identity, so it looks
    # harmless while quietly reinstating the pre-v8.5 dataset.
    stored_factor = row.get("arch_horizon_factor")
    arch_horizon_factor = (
        _float(stored_factor)
        if stored_factor is not None
        else _arch_horizon_factor(
            _float(row["ads"]), base_ads, seasonality_index, store_size
        )
    )

    def run(formula_id: str, values: dict[str, Any]) -> Any:
        return evaluate(asts[formula_id], values)

    # -- the chain, in dependency order ----------------------------------
    # Levers sit at zero throughout: this is the baseline board, and zero is
    # the setting the workbook itself was calculated at. The browser re-runs
    # these same expressions off the parameters carried below when a lever
    # actually moves.
    ads = run(
        "f01-ads-per-store",
        {
            "base_ads": base_ads,
            "seasonality": seasonality_index,
            "arch_horizon_factor": arch_horizon_factor,
            "store_size": store_size,
            "demand_lever": 0,
            "promo_eligible": promo_eligible,
            "promo_lever": 0,
            "promo_depth": _float(row["cannibalisation_pct"]),
        },
    )

    # The stored open-PO quantity is already at this row's own grain -- chain
    # net on the default board, one store's share under a Store scope -- so
    # f03's allocation ratio is one and the expression returns it unchanged.
    # It runs anyway rather than being short-circuited: the ratio being one is
    # a property of the grain, not a licence to skip the rule.
    open_po = run(
        "f03-open-po-per-store",
        {
            "open_po_total": _float(row["open_po_qty"]),
            "store_size": store_size,
            "total_store_size": store_size,
            "inbound_lever": 0,
        },
    )

    on_hand = _float(row["on_hand_qty"])
    position = run("f04-position", {"on_hand": on_hand, "open_po": open_po})

    rop = run(
        "f05-rop",
        {
            "ads": ads,
            "lead_time_days": _float(row["lead_time_days"]),
            "lead_time_adjust": 0,
            "safety_days": _float(row["safety_days"]),
            "safety_adjust": 0,
        },
    )

    dos = run("f20-days-of-supply", {"ads": ads, "position": position})
    state = run(
        "f07-inventory-state",
        {
            "position": position,
            "rop": rop,
            "days_of_supply": dos,
            "perishable": perishable,
            "shelf_life_days": row["shelf_life_days"] or 0,
            "velocity": growth,
        },
    )

    item = {
        "sku_id": row["item_key"],
        "name": row["name"],
        "vertical_id": row["vertical_id"],
        "category_id": row["category_id"],
        "category_label": row["category_name"],
        "ads": ads,
        "forecast_7d": run(
            "f08-forecast-7-days", {"ads": ads, "week_factor": DOW_SUM}
        ),
        "on_hand": on_hand,
        "open_po": open_po,
        "position": position,
        "rop": rop,
        "state": state,
        "price": _float(row["unit_price"]),
        "growth": growth,
        "is_stockout_risk": state in REPLENISH_STATES,
        "is_trending": bool(
            run(
                "fc10-trending-sku",
                {
                    "is_viral": "Y" if row["is_viral"] else "N",
                    "growth_index": growth,
                },
            )
        ),
        "signals": build_signals(row),
        "shelf_life_days": row["shelf_life_days"],
        "perishable": perishable,
        "base_ads": base_ads,
        "seasonality": seasonality_index,
        "store_size": store_size,
        "arch_horizon_factor": arch_horizon_factor,
        "promo_eligible": promo_eligible,
        "promo_depth": _float(row["cannibalisation_pct"]),
        "lead_days": _float(row["lead_time_days"]),
        "safety_days": _float(row["safety_days"]),
    }
    if row.get("store_id"):
        item["store_id"] = row["store_id"]
    return item


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
                       i.seasonality_index, i.arch_horizon_factor,
                       i.lead_time_days, i.safety_days,
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
                       i.seasonality_index, i.arch_horizon_factor,
                       i.lead_time_days, i.safety_days,
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

    catalogue = formulas(ENGINE_FORMULAS)
    # Parsed once for all 800 rows rather than per row: `build_item` walks the
    # whole chain per SKU, and re-parsing nine expressions each time would be
    # thousands of parses for one dashboard load.
    asts = {name: parse(expression) for name, expression in catalogue.items()}

    items = [
        build_item(row, store_size[row["vertical_id"]], asts) for row in chain
    ]

    forecast_by_store = {
        row["store_id"]: _float(row["forecast_7d"]) for row in stores
    }

    return {
        **envelope(AGENT_ID, NOTE),
        "scope": scope.as_query(),
        "scope_limitations": list(STORE_SCOPE_LIMITATIONS) if scope.store_id else [],
        "constants": {**constants(), "interval_z": INTERVAL_Z},
        "derivation": DERIVATION,
        "formulas": catalogue,
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
