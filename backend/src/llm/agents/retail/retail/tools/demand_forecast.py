"""Retail demand-forecast tool — hits D365 F&O live."""

from __future__ import annotations

from typing import Any

import requests

from src.integrations.d365.forecast_client import (
    get_demand_forecast,
    summarize_forecast,
)


def query_demand_forecast(
    sku: str = "*",
    signal: str = "REORDER,viral",
    limit: int = 100,
) -> dict[str, Any]:
    """
    Fetch demand forecast from D365 F&O (live).

    Params:
      sku    : SKU range. Default "*" returns the full dataset.
               Example "BAK*,MEA*" limits to Bakery and Meat only.
      signal : signal filter, e.g. "REORDER,viral".
      limit  : maximum rows (default 100).

    Return:
      On success: {"rows": [...], "summary": {...}}
        rows    : list of SKUs with fields SKUID, Item, Category, ADSDay,
                  Forecast7d, Seasonality, Position, ROP, DaysCover, Signal.
        summary : aggregates (total_sku, possibly_truncated, reorder_count,
                  viral_count, reorder_skus). Reorder = Position < ROP.
      On failure: {"error": "...", "rows": [], "summary": {}}
    """
    try:
        rows = get_demand_forecast(
            sku_id_range=sku,
            signal_range=signal,
            max_records=limit,
        )
    except requests.exceptions.RequestException as error:
        return {
            "error": f"Could not reach the D365 forecast service: {error}",
            "rows": [],
            "summary": {},
        }

    return {
        "rows": rows,
        "summary": summarize_forecast(rows, max_records=limit),
    }


TOOLS = {
    "query_demand_forecast": query_demand_forecast,
}


__all__ = ["TOOLS", "query_demand_forecast"]