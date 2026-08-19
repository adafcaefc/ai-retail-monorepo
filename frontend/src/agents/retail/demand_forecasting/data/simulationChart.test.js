import { describe, expect, it } from "vitest";

import {
  buildDemandComparisonChartData,
  getDemandComparisonYAxisDomain,
  normalizedDemandScenarioIndex,
} from "./simulation.js";

describe("Demand What-If comparison normalization", () => {
  it("pins the baseline to 100 and expresses scenario values as an index", () => {
    expect(normalizedDemandScenarioIndex(100, 110)).toBeCloseTo(110, 12);
    expect(normalizedDemandScenarioIndex(100, 80)).toBeCloseTo(80, 12);
    expect(normalizedDemandScenarioIndex(1000, 1100)).toBeCloseTo(110, 12);
  });

  it("clips negative scenario values because these metrics are non-negative", () => {
    expect(normalizedDemandScenarioIndex(100, -20)).toBe(0);
  });

  it.each([
    [0, 0],
    [0, 100],
    [null, 100],
    [100, null],
    [100, Number.NaN],
    [100, Number.POSITIVE_INFINITY],
    ["100", 110],
  ])("returns null for an invalid or zero baseline (%j, %j)", (baseline, scenario) => {
    expect(normalizedDemandScenarioIndex(baseline, scenario)).toBeNull();
  });

  it("keeps invalid metric rows safe while preserving the other plotted rows", () => {
    const rows = buildDemandComparisonChartData({
      baseline: {
        forecast_next_7d: 0,
        stockout_risk_skus: 100,
        forecast_accuracy_pct: 100,
        predicted_to_trend: 100,
      },
      scenario: {
        forecast_next_7d: 0,
        stockout_risk_skus: 80,
        forecast_accuracy_pct: 110,
        predicted_to_trend: Number.NaN,
      },
    });

    expect(rows.map(({ baseline }) => baseline)).toEqual([100, 100, 100, 100]);
    expect(rows[0].scenario).toBeNull();
    expect(rows[1].scenario).toBeCloseTo(80, 12);
    expect(rows[2].scenario).toBeCloseTo(110, 12);
    expect(rows[3].scenario).toBeNull();
  });
});

describe("Demand What-If comparison Y-axis domain", () => {
  it.each([
    [[100, 100, 80, 110], [70, 120]],
    [[67, 110], [60, 120]],
    [[82, 107], [80, 110]],
    [[100, 100], [90, 110]],
    [[99, 101], [90, 110]],
    [[41, 58], [40, 60]],
    [[0, 100], [0, 110]],
  ])("rounds %j to %j", (values, expected) => {
    expect(getDemandComparisonYAxisDomain(values)).toEqual(expected);
  });

  it("ignores null, undefined, NaN, and Infinity and falls back safely", () => {
    expect(getDemandComparisonYAxisDomain([
      null,
      undefined,
      Number.NaN,
      Number.POSITIVE_INFINITY,
    ])).toEqual([0, 100]);
    expect(getDemandComparisonYAxisDomain([100, null, Number.NaN])).toEqual([90, 110]);
  });

  it("does not allow a negative normalized-axis minimum", () => {
    expect(getDemandComparisonYAxisDomain([-40, 100])).toEqual([0, 110]);
  });
});
