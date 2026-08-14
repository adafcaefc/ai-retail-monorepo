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

CHAIN = f"{warehouse.SCHEMA}.fact_inventory_chain_daily"
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

    Figures are chain-net (one row per item, netted across stores).

    Args:
        legal_entity_id: Vertical to narrow to (GRC, GMR, FSH, HNB, ELC, HNL,
            DGT, OMN). Omit for the whole chain.
        category_group: Category id to narrow to. Omit for all categories.
    """
    entity, category = snapshot.scope_filters(legal_entity_id, category_group)
    clause, params = snapshot.where(
        entity,
        category,
        entity_column="i.vertical_id",
        category_column="i.category_id",
    )

    with snapshot._read_connection() as connection:
        by_vertical = snapshot._rows(
            connection,
            f"""
            SELECT i.vertical_id,
                   v.dashboard_label,
                   count(*)                                   AS skus,
                   round(sum(c.ads * :dow_sum), 0)      AS forecast_7d,
                   round(sum(c.ads), 1)              AS ads_total,
                   round(avg(i.seasonality_index), 3)         AS avg_seasonality,
                   round(avg(i.growth_index), 3)              AS avg_growth,
                   sum(CASE WHEN c.state IN ('Stockout', 'Low') THEN 1 ELSE 0 END)
                                                              AS stockout_risk_skus,
                   sum(CASE WHEN i.is_viral = 1 THEN 1 ELSE 0 END)         AS viral_skus,
                   sum(CASE WHEN i.growth_index > 1 THEN 1 ELSE 0 END) AS growing_skus,
                   -- Counted here, not from the length of the ranked list
                   -- below: that one is TOP-limited, so deriving a total from
                   -- it would report the page size as the population.
                   sum(CASE WHEN c.ads * :dow_sum > c.position_qty THEN 1 ELSE 0 END)
                                                              AS forecast_exceeds_position_skus
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            JOIN {warehouse.SCHEMA}.dim_vertical v ON v.vertical_id = i.vertical_id
            WHERE 1 = 1{clause}
            GROUP BY i.vertical_id, v.dashboard_label, v.sort_order
            ORDER BY v.sort_order
            """,
            {**params, "dow_sum": DOW_SUM},
        )

        # Demand-side stockout risk: what the next seven days want, against
        # what is actually in position. This is the A1 question, distinct from
        # A2's state classification, which compares position to ROP.
        outrunning = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   c.item_key,
                   i.name,
                   i.vertical_id,
                   i.category_name,
                   round(c.ads * :dow_sum, 0)      AS forecast_7d,
                   round(c.position_qty, 0)                   AS position,
                   round(c.ads * :dow_sum - c.position_qty, 0)
                                                           AS shortfall_units,
                   round(c.days_cover, 2)         AS days_cover,
                   c.state
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            WHERE c.ads * :dow_sum > c.position_qty{clause}
            ORDER BY (c.ads * :dow_sum - c.position_qty) DESC
            """,
            {**params, "dow_sum": DOW_SUM, "top_n": snapshot.TOP_N},
        )

        trending = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   c.item_key,
                   i.name,
                   i.vertical_id,
                   i.is_viral,
                   round(i.growth_index, 3)                AS growth_index,
                   round(i.seasonality_index, 3)           AS seasonality_index,
                   round(c.ads * :dow_sum, 0)      AS forecast_7d,
                   round(c.days_cover, 2)         AS days_cover,
                   c.state
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            WHERE (i.is_viral = 1 OR i.growth_index > 1){clause}
            ORDER BY i.is_viral DESC, i.growth_index DESC
            """,
            {**params, "dow_sum": DOW_SUM, "top_n": snapshot.TOP_N},
        )

        lowest_cover = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   c.item_key,
                   i.name,
                   i.vertical_id,
                   round(c.days_cover, 2)    AS days_cover,
                   round(c.ads * :dow_sum, 0) AS forecast_7d,
                   round(c.position_qty, 0)              AS position,
                   c.state
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            WHERE c.ads > 0{clause}
            ORDER BY c.days_cover ASC
            """,
            {**params, "dow_sum": DOW_SUM, "top_n": snapshot.TOP_N},
        )

        reference = snapshot.reference(connection, AGENT_ID)

    totals = {
        "skus": sum(row["skus"] for row in by_vertical),
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
        "grain": "chain_net",
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
            "compares position to reorder point rather than to forecast."
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
