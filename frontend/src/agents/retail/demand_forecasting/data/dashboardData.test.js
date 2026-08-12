/*
 * The gateway, and the reconciliation behind it.
 *
 * These used to assert against `mockDashboard.js` — a payload checked against
 * the thing that produced it, which could only ever pass. The comparisons here
 * are against `a1_demand_forecasting`, the workbook's own sheet, carried into
 * the fixture as `reference_by_vertical`.
 *
 * The API branch is not exercised: `DATA_SOURCE` is a module constant rather
 * than an environment flag (see `dashboardData.js` for why), so there is
 * nothing to stub. Inventory Risk makes the same trade. When the backend
 * builder lands, that branch gets a test against a real response.
 */

import { describe, expect, it } from "vitest";

import { DEMAND_AGENT_ID, DEFAULT_DEMAND_LEVERS } from "./contract.js";
import {
  demandForecastingDataSource,
  loadDemandForecastingDashboard,
  loadDemandForecastingScenario,
} from "./dashboardData.js";
import fixture from "./fixture.json";

const grocery = fixture.reference_by_vertical.find(
  (row) => row.legal_entity_id === "GRC",
);

describe("the Demand Forecasting gateway", () => {
  it("reads the workbook fixture, not an invented dataset", async () => {
    expect(demandForecastingDataSource()).toBe("fixture");

    const dashboard = await loadDemandForecastingDashboard();

    expect(dashboard.agent).toBe(DEMAND_AGENT_ID);
    expect(dashboard.is_mock).toBe(true);
    expect(dashboard.note).toMatch(/typed into the A1 sheet/);
  });

  it("carries the real eight verticals, not the four that were made up", async () => {
    const dashboard = await loadDemandForecastingDashboard();
    const ids = dashboard.filter_options.legal_entities.map((row) => row.value);

    expect(ids).toHaveLength(8);
    expect(ids).toContain("GRC");
    expect(ids).toContain("HNB");
    // HBA and HME were invented and do not exist in the dataset.
    expect(ids).not.toContain("HBA");
    expect(ids).not.toContain("HME");
  });

  it("matches the A1 sheet on the two figures the workbook actually computes", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
    });
    const byId = Object.fromEntries(
      dashboard.kpis.map((kpi) => [kpi.id, kpi.value]),
    );

    expect(byId.forecast_next_7d).toBeCloseTo(grocery.forecast_7d, 3);
    expect(byId.stockout_risk_skus).toBe(grocery.stockout_risk_skus);
    expect(byId.predicted_to_trend).toBe(grocery.trending_skus);
  });

  it("passes the typed constants through untouched, and labels them", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
    });
    const kpi = (id) => dashboard.kpis.find((row) => row.id === id);

    expect(kpi("forecast_accuracy").value).toBeCloseTo(grocery.accuracy_pct, 6);
    expect(kpi("demand_trend").value).toBeCloseTo(grocery.trend_pct, 6);
    expect(kpi("seasonality_index").value).toBeCloseTo(grocery.seasonality_idx, 6);

    // The tile says where its number came from rather than implying it was
    // calculated. Four of the six were keyed in by hand.
    expect(kpi("forecast_accuracy").comparison_label).toBe("Workbook constant");
    expect(kpi("forecast_next_7d").comparison_label).toBe("Calculated");
  });

  it("totals the chain to the sum of its verticals", async () => {
    const dashboard = await loadDemandForecastingDashboard();
    const expected = fixture.reference_by_vertical.reduce(
      (running, row) => running + row.forecast_7d,
      0,
    );
    const forecast = dashboard.kpis.find((kpi) => kpi.id === "forecast_next_7d");

    expect(forecast.value).toBeCloseTo(expected, 3);
    expect(dashboard.details.total).toBe(800);
  });

  it("emits a forecast series with a widening interval and no actuals", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      horizon_weeks: 8,
      grain: "weekly",
    });
    const { points } = dashboard.forecast;

    expect(points).toHaveLength(8);
    // No sales history exists at any grain, so nothing claims to be measured.
    expect(points.every((point) => point.actual === null)).toBe(true);

    const width = (point) => point.confidence_high - point.confidence_low;
    const relative = points.map((point) => width(point) / point.forecast);
    // sqrt(h) growth: the band is wider at the far end than the near one.
    expect(relative.at(-1)).toBeGreaterThan(relative[0]);
    // And the first period lands on the ±12% the A1 spec asserts flatly.
    expect(relative[0] / 2).toBeCloseTo(0.125, 2);
  });

  it("keeps the board on the workbook until a lever is moved", async () => {
    const rest = await loadDemandForecastingDashboard({}, DEFAULT_DEMAND_LEVERS);
    expect(rest.simulation.applied).toBe(false);
    expect(rest.simulation.scenario).toEqual(rest.simulation.baseline);
  });

  it("moves what the formulas reach, and nothing else", async () => {
    const dashboard = await loadDemandForecastingDashboard(
      {},
      { ...DEFAULT_DEMAND_LEVERS, demand: 30 },
    );
    const { baseline, scenario } = dashboard.simulation;

    // f01 scales ADS, so the forecast and the reorder zone both move.
    expect(scenario.forecast_next_7d).toBeGreaterThan(baseline.forecast_next_7d);
    expect(scenario.stockout_risk_skus).toBeGreaterThan(baseline.stockout_risk_skus);
    /*
     * Accuracy and trending are typed constants with no lever anywhere near
     * them, and the payload names them so the panel can say so.
     *
     * Accuracy is compared approximately rather than exactly: it is blended
     * across the scope's verticals weighted by forecast, so a scenario that
     * changes volumes changes the weights. The workbook types 92.4 for all
     * eight, so the blend is 92.4 either way and the difference is 1e-13 of
     * floating point, not a lever taking effect.
     */
    expect(scenario.forecast_accuracy_pct).toBeCloseTo(
      baseline.forecast_accuracy_pct,
      9,
    );
    expect(scenario.predicted_to_trend).toBe(baseline.predicted_to_trend);
    expect(dashboard.simulation.unmodelled).toContain("forecast_accuracy_pct");
  });

  it("previews a scenario without applying it to the board", async () => {
    const preview = await loadDemandForecastingScenario(
      {},
      { ...DEFAULT_DEMAND_LEVERS, demand: 20 },
    );
    expect(preview.simulation.applied).toBe(true);
    expect(preview.forecast.points.length).toBeGreaterThan(0);
  });
});

describe("dimensions", () => {
  it("reconciles every breakdown to the chain total", async () => {
    const dashboard = await loadDemandForecastingDashboard();
    const { dimensions } = dashboard;
    const total = dimensions.chain_total;

    for (const key of ["categories", "stores", "clusters", "legal_entities"]) {
      const summed = dimensions[key].reduce(
        (running, row) => running + row.forecast_units,
        0,
      );
      expect(summed).toBeCloseTo(total, 3);
    }

    expect(dimensions.categories).toHaveLength(160);
    expect(dimensions.stores).toHaveLength(160);
    expect(dimensions.legal_entities).toHaveLength(8);
  });

  it("derives the seasonality curve from the monthly profile", async () => {
    const dashboard = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
    });
    const { seasonality } = dashboard.dimensions;

    expect(seasonality).toHaveLength(12);
    // `Constants` B6 says the workbook is evaluated at July.
    expect(seasonality[fixture.seasonality.current_month_index].current).toBe(true);
    expect(seasonality.filter((point) => point.current)).toHaveLength(1);

    // Indices average 100 by construction — they are month over series mean.
    const mean =
      seasonality.reduce((running, point) => running + point.index, 0) / 12;
    expect(mean).toBeCloseTo(100, 6);
  });
});
