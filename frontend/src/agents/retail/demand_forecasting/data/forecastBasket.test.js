import { describe, expect, it } from "vitest";

import {
  normalizeForecastBasket,
  serializeForecastBasketScope,
} from "./forecastBasket.js";

function row(overrides = {}) {
  return {
    store_id: "S001",
    store_name: "Grocery 01",
    sku_id: "GRC-001",
    item_name: "Rice",
    category_id: "GRC-C01",
    category: "Grocery",
    target: { value: 10, unit: "units/day", basis: "ads" },
    forecast_7d: 70,
    rop: 20,
    max: 35,
    position: 15,
    suggestion: 20,
    signal: ["below_rop"],
    route: "direct",
    lead_time_days: 2,
    eta: null,
    eta_status: "unavailable",
    perishable: false,
    vendor: "Vendor A",
    ...overrides,
  };
}

function response(rows = [row()]) {
  return {
    schema_version: 1,
    agent: "retail.demand_forecasting",
    as_of: "2026-07-01",
    scope: { legal_entity_id: "GRC", category_group: null, store_id: null, sku: null },
    grain: "sku_store",
    source: "retail.fact_inventory_daily.forecast_7d",
    row_count: rows.length,
    action_row_count: 1,
    dashboard_forecast_7d: 70,
    basket_forecast_7d: 70,
    reconciles: true,
    suggestion_units: 20,
    rows,
  };
}

describe("forecast basket contract", () => {
  it("serializes only supported scope filters and omits ALL", () => {
    const params = serializeForecastBasketScope({
      legal_entity_id: "GRC",
      category_group: "GRC-C01",
      store_id: "ALL",
      sku: " rice ",
      grain: "monthly",
      horizon_weeks: 16,
    });

    expect(Object.fromEntries(params.entries())).toEqual({
      legal_entity_id: "GRC",
      category_group: "GRC-C01",
      sku: "rice",
    });
  });

  it("preserves the backend fields and rejects duplicate Store × SKU rows", () => {
    expect(normalizeForecastBasket(response()).rows[0]).toMatchObject({
      sku_id: "GRC-001",
      target: { value: 10, unit: "units/day", basis: "ads" },
      eta: null,
      eta_status: "unavailable",
    });
    expect(() => normalizeForecastBasket(response([row(), row()]))).toThrow(/duplicate Store/);
  });

  it("rejects a response whose row count does not match its complete row payload", () => {
    expect(() => normalizeForecastBasket({ ...response(), row_count: 2 })).toThrow(/row_count/);
    expect(() => normalizeForecastBasket({ ...response(), grain: "chain" })).toThrow(/grain/);
    expect(() => normalizeForecastBasket({ ...response(), reconciles: "true" })).toThrow(/reconciles/);
  });
});
