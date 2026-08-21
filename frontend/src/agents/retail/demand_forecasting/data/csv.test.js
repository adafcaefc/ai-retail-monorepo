import { describe, expect, it } from "vitest";

import {
  buildForecastBasketCsv,
  forecastBasketFilename,
} from "./csv.js";

describe("Demand forecast basket CSV", () => {
  it("uses business column order and raw numeric backend values", () => {
    const csv = buildForecastBasketCsv([{
      store_name: "Store, One",
      sku_id: "SKU-001",
      item_name: "Rice 5kg",
      category: "Grocery",
      target: { value: 12.3, unit: "units/day", basis: "ads" },
      forecast_7d: 86.1,
      rop: 20,
      max: 35,
      position: 14,
      suggestion: 21,
      signal: ["below_rop", "promo"],
      route: "direct",
      eta: null,
    }]);

    const lines = csv.trimEnd().split("\r\n");
    expect(lines[0]).toBe("Store,SKU,Item,Category,Target,Forecast 7d,ROP,Max,Position,Suggestion,Signal,Route,ETA");
    expect(lines[1]).toContain('"Store, One"');
    expect(lines[1]).toContain("12.3");
    expect(lines[1]).toContain("86.1");
    expect(lines[1]).toContain("below_rop | promo");
    expect(lines[1]).toContain("Unavailable");
    expect(lines[1]).not.toContain("units/day");
  });

  it("defuses spreadsheet formulas, quotes embedded quotes, and names the mode/scope/date", () => {
    const csv = buildForecastBasketCsv([{
      store_name: "=HYPERLINK(\"https://example.com\")",
      sku_id: "SKU-001",
      item_name: 'Rice, 5kg "premium"',
      category: "Grocery",
      target: { value: 1, unit: "units/day", basis: "ads" },
      forecast_7d: -2.5,
      rop: 0,
      max: 1,
      position: 0,
      suggestion: 0,
      signal: [],
      route: "cross",
      eta: null,
    }]);

    expect(csv).toContain("'=HYPERLINK");
    expect(csv).toContain('"Rice, 5kg ""premium"""');
    expect(csv).toContain("-2.5");
    expect(forecastBasketFilename(
      { legal_entity_id: "GRC", category_group: "GRC-C01", store_id: null, sku: "" },
      "2026-07-01T00:00:00Z",
      "all",
    )).toBe("demand_forecast_basket_all-stores_GRC_GRC-C01_2026-07-01_all.csv");
  });
});
