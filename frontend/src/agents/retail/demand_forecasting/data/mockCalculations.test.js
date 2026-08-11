import { describe, expect, it } from "vitest";

import {
  DEFAULT_DEMAND_QUERY,
  demandScenarioContext,
  isDemandScenarioCompatible,
} from "./contract.js";
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
      seasonality_index: 104,
    });
    expect(dashboard.forecast.summary.find((item) => item.id === "peak")?.value)
      .toBe("Saturday ×1.35");
    expect(dashboard.details.total).toBe(400);
    expect(dashboard.details.rows).toHaveLength(100);
    expect(dashboard.dimensions.seasonality).toHaveLength(12);
    expect(dashboard.dimensions.seasonality.find((point) => point.current)?.month).toBe("Jul");
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

  it("reconciles every Demand dimension and full detail result to the forecast KPI", async () => {
    const dashboard = await getMockDemandForecastingDashboard();
    const forecast = dashboard.kpis.find((kpi) => kpi.id === "forecast_next_7d").value;
    const sum = (rows) => rows.reduce((total, row) => total + row.forecast_units, 0);

    expect(dashboard.dimensions.chain_total).toBe(forecast);
    expect(sum(dashboard.dimensions.categories)).toBe(forecast);
    expect(sum(dashboard.dimensions.stores)).toBe(forecast);
    expect(sum(dashboard.dimensions.clusters)).toBe(forecast);
    expect(sum(dashboard.dimensions.legal_entities)).toBe(forecast);
    expect(dashboard.details.forecast_total_units).toBe(forecast);
    expect(dashboard.dimensions.clusters.map((row) => row.id)).toEqual([
      "Flagship", "Mall", "Community", "Express",
    ]);
  });

  it("applies deterministic levers to the whole normalized dashboard", async () => {
    const levers = { demand: 20, promo: 30, markdown: 35, inbound: 20, lead: 2, safety: 1 };
    const first = await getMockDemandForecastingDashboard({}, levers);
    const second = await getMockDemandForecastingDashboard({}, levers);
    const forecast = first.simulation.scenario.forecast_next_7d;
    const sum = (rows) => rows.reduce((total, row) => total + row.forecast_units, 0);

    expect(second).toEqual(first);
    expect(first.simulation.applied).toBe(true);
    expect(forecast).toBeGreaterThan(first.simulation.baseline.forecast_next_7d);
    expect(first.simulation.scenario.stockout_risk_skus)
      .not.toBe(first.simulation.baseline.stockout_risk_skus);
    expect(first.kpis[0].value).toBe(forecast);
    expect(sum(first.dimensions.categories)).toBe(forecast);
    expect(sum(first.dimensions.stores)).toBe(forecast);
    expect(sum(first.dimensions.clusters)).toBe(forecast);
    expect(sum(first.dimensions.legal_entities)).toBe(forecast);
    expect(first.details.forecast_total_units).toBe(forecast);
  });

  it("keeps historical Actuals invariant while scenario forecasts and bounds change", async () => {
    const baseline = await getMockDemandForecastingDashboard();
    const demandScenario = await getMockDemandForecastingDashboard({}, { demand: 20 });
    const combinedScenario = await getMockDemandForecastingDashboard({}, {
      demand: 20,
      promo: 30,
      markdown: 35,
      inbound: 20,
      lead: 2,
      safety: 1,
    });
    const history = (series) => series.points
      .filter((point) => point.actual != null)
      .map((point) => point.actual);
    const future = (series) => series.points
      .filter((point) => point.forecast != null);

    expect(history(demandScenario.forecast)[0]).toBe(history(baseline.forecast)[0]);
    expect(history(combinedScenario.forecast)).toEqual(history(baseline.forecast));
    expect(history(combinedScenario.confidence)).toEqual(history(baseline.confidence));
    expect(future(demandScenario.forecast).map((point) => point.forecast))
      .not.toEqual(future(baseline.forecast).map((point) => point.forecast));
    expect(future(combinedScenario.confidence).map((point) => [
      point.forecast,
      point.confidence_low,
      point.confidence_high,
    ])).not.toEqual(future(baseline.confidence).map((point) => [
      point.forecast,
      point.confidence_low,
      point.confidence_high,
    ]));
    expect(await getMockDemandForecastingDashboard()).toEqual(baseline);
  });

  it("uses the highlighted scoped curve point as the single seasonality KPI source", async () => {
    for (const legalEntity of ["ALL", "GRC", "FSH", "HBA", "HME"]) {
      const first = await getMockDemandForecastingDashboard({
        legal_entity_id: legalEntity,
      });
      const second = await getMockDemandForecastingDashboard({
        legal_entity_id: legalEntity,
      });
      const seasonalityKpi = first.kpis.find((kpi) => kpi.id === "seasonality_index").value;
      const highlighted = first.dimensions.seasonality.find((point) => point.current);

      expect(first.dimensions.seasonality).toHaveLength(12);
      expect(highlighted.month).toBe("Jul");
      expect(seasonalityKpi).toBe(highlighted.index);
      expect(second.dimensions.seasonality).toEqual(first.dimensions.seasonality);
    }
  });

  it("keeps the forecast basket on a true seven-day basis across detail grains", async () => {
    const results = await Promise.all(
      ["daily", "weekly", "monthly", "quarterly", "yearly"].map((grain) =>
        getMockDemandForecastingDashboard({ sku: "GRC-001", grain })),
    );
    const basketValues = results.map(
      (dashboard) => dashboard.suggested_actions.plan_preview.rows[0].forecast_7d_units,
    );
    const detailValues = results.map((dashboard) => dashboard.details.rows[0].forecast_units);

    expect(new Set(basketValues).size).toBe(1);
    expect(new Set(detailValues).size).toBe(5);
    expect(basketValues[0]).toBe(detailValues[1]);
  });

  it("requires every saved scenario scope and period field to match", () => {
    const scenario = { context: demandScenarioContext(DEFAULT_DEMAND_QUERY) };
    expect(isDemandScenarioCompatible(scenario, DEFAULT_DEMAND_QUERY)).toBe(true);

    for (const patch of [
      { legal_entity_id: "GRC" },
      { category_group: "GRC-C01" },
      { store_id: "GRC-S1" },
      { sku: "GRC-001" },
      { grain: "monthly" },
      { horizon_weeks: 12 },
    ]) {
      expect(isDemandScenarioCompatible(scenario, {
        ...DEFAULT_DEMAND_QUERY,
        ...patch,
      })).toBe(false);
    }
  });
});
