"""Agent 1 · Demand Forecasting — the snapshot its chat and monitors read.

The forecast here is `ads * 7.45` (formula f08), a day-of-week weighted week
applied to a demand rate. It is a projection off one snapshot day, not a model
fitted to history, because there is no history: the workbook's 24-month series
repeats year one verbatim in year two, and `fact_sales_daily` is empty.

That constrains what this agent may honestly say, so the constraint travels in
the payload rather than only in the prompt. `accuracy_pct` is included because
the boards show it and a reader will ask, but it is flagged at every mention:
92.4% is a typed workbook constant identical across all eight verticals, not a
backtest. An agent that reports it as measured accuracy is wrong in a way no
downstream check would catch.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.retail.common import snapshot, warehouse
from src.llm.agents.retail.demand_forecasting.dashboard import (
    AGENT_ID,
    ENGINE_FORMULAS,
)

PER_STORE = f"{warehouse.SCHEMA}.fact_inventory_daily"
ITEM = f"{warehouse.SCHEMA}.dim_item"

# `Constants` B7: the day-of-week profile sums to this over a week, and f08
# multiplies a daily rate by it. Read from the formula catalogue rather than
# retyped would be better still, but f08 carries it inside its expression.
DOW_SUM = 7.45


def get_demand_forecast_snapshot(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
) -> dict[str, Any]:
    """Current 7-day demand forecast, trending SKUs, and demand-side risk.

    The standard portfolio view for Agent 1. Call this before answering
    anything about forecast volume, demand rates, seasonality, trending or
    viral items, or which SKUs demand is about to outrun. Use
    query_retail_demand only for a cut this does not already carry.

    Figures are measured over SKU x store rows. COUNTS ARE DISTINCT SKUs;
    forecast and ADS sum rows, which is correct because demand is additive
    across stores. `rows_at_store_grain` is the row count beside each SKU
    count -- never present one as the other.

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
                   -- DISTINCT SKUs throughout, matching A2's convention and
                   -- the board's cards. `count(*)` here would answer a
                   -- question about rows -- 20x larger -- to a question about
                   -- SKUs. Money and rates still sum rows, which is correct:
                   -- ADS is additive across stores.
                   count(DISTINCT c.item_key)                 AS skus,
                   count(*)                                   AS rows_at_store_grain,
                   round(sum(c.ads * :dow_sum), 0)            AS forecast_7d,
                   round(sum(c.ads), 1)                       AS ads_total,
                   round(avg(i.seasonality_index), 3)         AS avg_seasonality,
                   round(avg(i.growth_index), 3)              AS avg_growth,
                   -- Measured, not labelled: `state` no longer implies this.
                   -- Expiry outranks Stockout/Low in `f07`, so a perishable SKU
                   -- that is both below ROP and past shelf life reads "Expiry"
                   -- while still being below the reorder point. The chat config
                   -- already describes this card as "position below ROP".
                   count(DISTINCT CASE WHEN c.position_qty < c.rop_qty
                                       THEN c.item_key END)   AS stockout_risk_skus,
                   -- THE TRAP ON THIS BOARD. `is_viral` and `growth_index` are
                   -- dim_item attributes, replicated across all twenty of a
                   -- SKU's rows. Summed they read 20x and look plausible;
                   -- counted DISTINCT they are unchanged from chain grain,
                   -- which is the correct answer -- a SKU is viral or it is
                   -- not, and no store can make it more so.
                   count(DISTINCT CASE WHEN i.is_viral = 1
                                       THEN c.item_key END)   AS viral_skus,
                   count(DISTINCT CASE WHEN i.growth_index > 1
                                       THEN c.item_key END)   AS growing_skus,
                   -- Counted here, not from the length of the ranked list
                   -- below: that one is TOP-limited, so deriving a total from
                   -- it would report the page size as the population.
                   count(DISTINCT CASE WHEN c.ads * :dow_sum > c.position_qty
                                       THEN c.item_key END)
                                                              AS forecast_exceeds_position_skus
            FROM {PER_STORE} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            JOIN {warehouse.SCHEMA}.dim_vertical v ON v.vertical_id = i.vertical_id
            WHERE 1 = 1{clause}
            GROUP BY i.vertical_id, v.dashboard_label, v.sort_order
            ORDER BY v.sort_order
            """,
            {**params, "dow_sum": DOW_SUM},
        )

        # AGGREGATE THEN RANK, for all three lists below. Each ranks whole
        # SKUs, so a SKU's store rows are summed to one line before the
        # ordering runs. Ranking rows directly would fill every list with one
        # SKU's twenty branches -- `lowest_cover` worst of all, where TOP 12
        # over 16,000 rows returns the same two SKUs twelve times.
        #
        # `state` is deliberately absent from all three: it cannot be
        # aggregated, since a SKU is Stockout in some stores and Healthy in
        # others. `at_risk_stores` of `store_rows` says it without the fiction.
        per_item = f"""
            WITH per_item AS (
                SELECT c.item_key,
                       sum(c.ads)                            AS ads,
                       sum(c.position_qty)                   AS position_qty,
                       count(*)                              AS store_rows,
                       sum(CASE WHEN c.state <> 'Healthy' THEN 1 ELSE 0 END)
                                                             AS at_risk_stores,
                       -- Shortfall summed ONLY over the stores actually short,
                       -- never netted against stores holding surplus. This is
                       -- the population `skus_forecast_exceeds_position` counts
                       -- (a SKU short in ANY store), so the ranked list below
                       -- and the headline describe the same SKUs. Comparing
                       -- SKU-total forecast against SKU-total position instead
                       -- would silently reinstate chain-netting -- a SKU short
                       -- in three stores and long in seventeen would vanish,
                       -- which is the exact failure this migration removed.
                       sum(CASE WHEN c.ads * :dow_sum > c.position_qty
                                THEN c.ads * :dow_sum - c.position_qty
                                ELSE 0 END)                  AS shortfall_units,
                       sum(CASE WHEN c.ads * :dow_sum > c.position_qty
                                THEN 1 ELSE 0 END)           AS short_stores
                FROM {PER_STORE} c
                JOIN {ITEM} i ON i.item_id = c.item_key
                WHERE 1 = 1{clause}
                GROUP BY c.item_key
            )
        """

        # Demand-side stockout risk: what the next seven days want, against
        # what is actually in position. This is the A1 question, distinct from
        # A2's state classification, which compares position to ROP.
        outrunning = snapshot._rows(
            connection,
            per_item
            + """
            SELECT TOP (:top_n)
                   p.item_key,
                   i.name,
                   i.vertical_id,
                   i.category_name,
                   round(p.ads * :dow_sum, 0)                 AS forecast_7d,
                   round(p.position_qty, 0)                   AS position,
                   round(p.shortfall_units, 0)                AS shortfall_units,
                   -- f20 over the summed inputs; days of cover is a ratio and
                   -- cannot be summed or averaged across stores.
                   CASE WHEN p.ads > 0
                        THEN round(p.position_qty / p.ads, 2)
                        ELSE 0 END                            AS days_cover,
                   p.short_stores,
                   p.at_risk_stores,
                   p.store_rows
            FROM per_item p
            JOIN retail.dim_item i ON i.item_id = p.item_key
            WHERE p.shortfall_units > 0
            ORDER BY p.shortfall_units DESC
            """,
            {**params, "dow_sum": DOW_SUM, "top_n": snapshot.TOP_N},
        )

        trending = snapshot._rows(
            connection,
            per_item
            + """
            SELECT TOP (:top_n)
                   p.item_key,
                   i.name,
                   i.vertical_id,
                   i.is_viral,
                   round(i.growth_index, 3)                   AS growth_index,
                   round(i.seasonality_index, 3)              AS seasonality_index,
                   round(p.ads * :dow_sum, 0)                 AS forecast_7d,
                   CASE WHEN p.ads > 0
                        THEN round(p.position_qty / p.ads, 2)
                        ELSE 0 END                            AS days_cover,
                   p.at_risk_stores,
                   p.store_rows
            FROM per_item p
            JOIN retail.dim_item i ON i.item_id = p.item_key
            WHERE (i.is_viral = 1 OR i.growth_index > 1)
            ORDER BY i.is_viral DESC, i.growth_index DESC
            """,
            {**params, "dow_sum": DOW_SUM, "top_n": snapshot.TOP_N},
        )

        lowest_cover = snapshot._rows(
            connection,
            per_item
            + """
            SELECT TOP (:top_n)
                   p.item_key,
                   i.name,
                   i.vertical_id,
                   CASE WHEN p.ads > 0
                        THEN round(p.position_qty / p.ads, 2)
                        ELSE 0 END                            AS days_cover,
                   round(p.ads * :dow_sum, 0)                 AS forecast_7d,
                   round(p.position_qty, 0)                   AS position,
                   p.at_risk_stores,
                   p.store_rows
            FROM per_item p
            JOIN retail.dim_item i ON i.item_id = p.item_key
            WHERE p.ads > 0
            ORDER BY CASE WHEN p.ads > 0
                          THEN p.position_qty / p.ads ELSE 0 END ASC
            """,
            {**params, "dow_sum": DOW_SUM, "top_n": snapshot.TOP_N},
        )

        reference = snapshot.reference(connection, AGENT_ID)

    # Summing DISTINCT counts across verticals is safe here and only here: a
    # SKU belongs to exactly one vertical, so the groups partition the
    # population. It would NOT be safe across states or stores, where one SKU
    # appears in several groups -- see `inventory_data.py`, which runs a
    # separate one-pass query for its headline rather than adding rows up.
    totals = {
        "skus": sum(row["skus"] for row in by_vertical),
        "rows_at_store_grain": sum(
            row["rows_at_store_grain"] for row in by_vertical
        ),
        "forecast_7d": sum(row["forecast_7d"] or 0 for row in by_vertical),
        "ads_total": round(sum(row["ads_total"] or 0 for row in by_vertical), 1),
        "stockout_risk_skus": sum(
            row["stockout_risk_skus"] for row in by_vertical
        ),
        "viral_skus": sum(row["viral_skus"] for row in by_vertical),
        "growing_skus": sum(row["growing_skus"] for row in by_vertical),
        "skus_forecast_exceeds_position": sum(
            row["forecast_exceeds_position_skus"] for row in by_vertical
        ),
    }

    return {
        **snapshot.envelope(
            AGENT_ID,
            legal_entity_id=entity,
            category_group=category,
            formulas=ENGINE_FORMULAS,
        ),
        # Was "chain_net" -- untrue since this tool moved to ENGINE_STORE. The
        # model reads this to describe its own numbers.
        "grain": "store_sku",
        "method": (
            f"forecast_7d = ads * {DOW_SUM} (formula f08-forecast-7-days), a "
            "day-of-week weighted week applied to the current demand rate."
        ),
        "totals": totals,
        "by_vertical": by_vertical,
        "forecast_exceeds_position": outrunning,
        "forecast_exceeds_position_note": (
            "Demand-side risk: the next seven days want more than is in "
            "position. Distinct from Agent 2's state classification, which "
            "compares position to reorder point rather than to forecast. "
            "`shortfall_units` sums only the stores actually short and is "
            "never netted against stores holding surplus, so `short_stores` "
            "of `store_rows` says how widely a SKU is affected -- a SKU short "
            "in 3 of 20 stores is a real shortfall, not a rounding artefact."
        ),
        "trending_skus": trending,
        "lowest_days_cover": lowest_cover,
        "accuracy": {
            "accuracy_pct": 92.4,
            "is_measured": False,
            "warning": (
                "TYPED CONSTANT, NOT A BACKTEST. 92.4% is stated identically "
                "for all eight verticals in the workbook. There is no actuals "
                "series to measure against: fact_sales_daily is empty and the "
                "24-month series repeats year one in year two. Never present "
                "this as measured accuracy, a MAPE, or evidence the forecast "
                "is performing."
            ),
        },
        "reference_by_vertical": reference,
        "reference_note": (
            "The workbook's own published KPIs per vertical. Use them to check "
            "a computed headline; a material difference is either a finding or "
            "a mistake, and worth naming as one."
        ),
    }


TOOLS = {
    "get_demand_forecast_snapshot": get_demand_forecast_snapshot,
}


__all__ = ["TOOLS", "get_demand_forecast_snapshot"]
