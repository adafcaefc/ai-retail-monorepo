import { describe, expect, it } from "vitest";

import {
  DEFAULT_FORECAST_DETAIL_SORT,
  sortForecastDetailRows,
  toggleForecastDetailSort,
} from "./forecastDetailSorting.js";

function row(overrides = {}) {
  return {
    sku_id: "SKU-001",
    sku_name: "Item 1",
    category_label: "Bakery",
    ads_units_per_day: 100,
    forecast_units: 700,
    forecast_7d_units: 745,
    trend_pct: 10,
    signals: ["growth"],
    supply_state: "Healthy",
    ...overrides,
  };
}

describe("Forecast Detail sorting", () => {
  it("starts with weekly forecast descending and toggles inactive columns from ascending", () => {
    expect(DEFAULT_FORECAST_DETAIL_SORT).toEqual({ column: "forecast", direction: "desc" });
    expect(toggleForecastDetailSort(DEFAULT_FORECAST_DETAIL_SORT, "ads")).toEqual({
      column: "ads",
      direction: "asc",
    });
    expect(toggleForecastDetailSort({ column: "ads", direction: "asc" }, "ads")).toEqual({
      column: "ads",
      direction: "desc",
    });
  });

  it("sorts numeric ADS, forecast, and trend values numerically", () => {
    const rows = [
      row({ sku_id: "SKU-271", ads_units_per_day: 271.9, forecast_units: 1903, trend_pct: 14 }),
      row({ sku_id: "SKU-268", ads_units_per_day: 268.6, forecast_units: 1880, trend_pct: -8.9 }),
      row({ sku_id: "SKU-265", ads_units_per_day: 265.3, forecast_units: 1857, trend_pct: 30.9 }),
    ];

    expect(sortForecastDetailRows(rows, { column: "ads", direction: "asc" }).map((item) => item.sku_id))
      .toEqual(["SKU-265", "SKU-268", "SKU-271"]);
    expect(sortForecastDetailRows(rows, { column: "forecast", direction: "desc" }).map((item) => item.sku_id))
      .toEqual(["SKU-271", "SKU-268", "SKU-265"]);
    expect(sortForecastDetailRows(rows, { column: "trend", direction: "asc" }).map((item) => item.sku_id))
      .toEqual(["SKU-268", "SKU-271", "SKU-265"]);
  });

  it("sorts text columns case-insensitively and uses SKU as a deterministic tie-breaker", () => {
    const rows = [
      row({ sku_id: "SKU-010", sku_name: "item 10", category_label: "zebra", signals: ["Promo", "Growth"], supply_state: "Low" }),
      row({ sku_id: "SKU-002", sku_name: "Item 2", category_label: "Bakery", signals: ["promo", "growth"], supply_state: "Healthy" }),
      row({ sku_id: "SKU-001", sku_name: "Item 1", category_label: "bakery", signals: ["Growth", "Promo"], supply_state: "Expiry" }),
    ];

    expect(sortForecastDetailRows(rows, { column: "sku", direction: "asc" }).map((item) => item.sku_id))
      .toEqual(["SKU-001", "SKU-002", "SKU-010"]);
    expect(sortForecastDetailRows(rows, { column: "category", direction: "asc" }).map((item) => item.sku_id))
      .toEqual(["SKU-001", "SKU-002", "SKU-010"]);
    expect(sortForecastDetailRows(rows, { column: "signals", direction: "asc" }).map((item) => item.sku_id))
      .toEqual(["SKU-001", "SKU-002", "SKU-010"]);
    expect(sortForecastDetailRows(rows, { column: "supply_state", direction: "asc" }).map((item) => item.sku_id))
      .toEqual(["SKU-001", "SKU-002", "SKU-010"]);
  });

  it("keeps null and empty values at the bottom in both directions", () => {
    const rows = [
      row({ sku_id: "SKU-002", ads_units_per_day: null }),
      row({ sku_id: "SKU-001", ads_units_per_day: 10 }),
      row({ sku_id: "SKU-003", ads_units_per_day: undefined }),
    ];

    expect(sortForecastDetailRows(rows, { column: "ads", direction: "asc" }).map((item) => item.sku_id))
      .toEqual(["SKU-001", "SKU-002", "SKU-003"]);
    expect(sortForecastDetailRows(rows, { column: "ads", direction: "desc" }).map((item) => item.sku_id))
      .toEqual(["SKU-001", "SKU-002", "SKU-003"]);
  });
});
