import { describe, expect, it } from "vitest";

import { DEFAULT_DEMAND_QUERY } from "./contract.js";
import { getMockDemandForecastingDashboard } from "./mockDashboard.js";

describe("Demand Forecasting mock provider", () => {
  it("reproduces the approved unfiltered reference baseline", async () => {
    const dashboard = await getMockDemandForecastingDashboard();
    const values = Object.fromEntries(dashboard.kpis.map((kpi) => [kpi.id, kpi.value]));

    expect(values).toEqual({
      forecast_next_7d: 1656179,
      forecast_accuracy: 93,
      demand_trend: 4.8,
      stockout_risk_skus: 302,
      predicted_to_trend: 355,
      seasonality_index: 114,
    });
    expect(dashboard.forecast.summary.find((item) => item.id === "peak")?.value)
      .toBe("Saturday ×1.35");
    expect(dashboard.details.total).toBe(400);
    expect(dashboard.details.rows).toHaveLength(100);
  });

  it("is deterministic and applies filters to all dashboard sections", async () => {
    const query = {
      ...DEFAULT_DEMAND_QUERY,
      legal_entity_id: "GRC",
      category_group: "GRC-C01",
      horizon_weeks: 4,
    };
    const first = await getMockDemandForecastingDashboard(query);
    const second = await getMockDemandForecastingDashboard(query);

    expect(second).toEqual(first);
    expect(first.scope).toMatchObject(query);
    expect(first.details.total).toBeGreaterThan(0);
    expect(first.details.total).toBeLessThan(400);
    expect(first.details.rows.every((row) => row.category_id === "GRC-C01")).toBe(true);
    expect(first.kpis[0].value).toBeLessThan(1656179);
  });

  it("changes horizon and grain deterministically", async () => {
    const fourWeeks = await getMockDemandForecastingDashboard({ horizon_weeks: 4 });
    const sixteenWeeks = await getMockDemandForecastingDashboard({ horizon_weeks: 16 });
    const daily = await getMockDemandForecastingDashboard({ grain: "daily", horizon_weeks: 4 });

    expect(fourWeeks.confidence.points).toHaveLength(12 + 4);
    expect(sixteenWeeks.confidence.points).toHaveLength(12 + 16);
    expect(sixteenWeeks.kpis.find((kpi) => kpi.id === "forecast_accuracy").value)
      .toBeLessThan(fourWeeks.kpis.find((kpi) => kpi.id === "forecast_accuracy").value);
    expect(daily.forecast.grain).toBe("daily");
    expect(daily.forecast.points).toHaveLength(28 + 28);
  });

  it("always brackets forecasts with confidence bounds", async () => {
    const dashboard = await getMockDemandForecastingDashboard({ horizon_weeks: 16 });
    const forecastPoints = dashboard.confidence.points.filter((point) => point.forecast != null);

    expect(forecastPoints).toHaveLength(16);
    for (const point of forecastPoints) {
      expect(point.confidence_low).toBeLessThanOrEqual(point.forecast);
      expect(point.confidence_high).toBeGreaterThanOrEqual(point.forecast);
    }
  });

  it("searches by SKU and produces a valid zero-result state", async () => {
    const one = await getMockDemandForecastingDashboard({ sku: "GRC-001" });
    const none = await getMockDemandForecastingDashboard({ sku: "DOES-NOT-EXIST" });

    expect(one.details.total).toBe(1);
    expect(one.details.rows[0].sku_id).toBe("GRC-001");
    expect(none.details.total).toBe(0);
    expect(none.details.rows).toEqual([]);
    expect(none.trending_items).toEqual([]);
  });
});

