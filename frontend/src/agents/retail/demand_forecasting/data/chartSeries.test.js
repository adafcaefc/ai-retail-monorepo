import { describe, expect, it } from "vitest";

import {
  buildConfidenceSeries,
  buildDemandChartSeries,
  buildDemandTransitionData,
  chartSourceColumns,
  getDemandChartYAxisDomain,
  isDemandGrainEnabled,
} from "./chartSeries.js";

function source() {
  return {
    source: "synthetic.demand_store_sku_104w",
    ...Object.fromEntries(
      Array.from({ length: 52 }, (_, index) => [`actual_w${52 - index}`, (52 - index) * 10]),
    ),
    ...Object.fromEntries(
      Array.from({ length: 52 }, (_, index) => [`forecast_w${index + 1}`, 1000 + index + 1]),
    ),
  };
}

function sum(values) {
  return values.reduce((total, value) => total + value, 0);
}

describe("104W Demand Forecasting chart series", () => {
  it("uses the 104W source columns and supports weekly Horizons", () => {
    expect(chartSourceColumns()).toHaveLength(104);
    for (const horizon of [4, 8, 12, 16]) {
      const series = buildDemandChartSeries(source(), {
        grain: "weekly",
        horizonWeeks: horizon,
      });
      expect(series.points.slice(0, 4).map((point) => point.label))
        .toEqual(["W-4", "W-3", "W-2", "W-1"]);
      expect(series.points.slice(4).map((point) => point.label))
        .toEqual(Array.from({ length: horizon }, (_, index) => `W+${index + 1}`));
      expect(series.points.slice(4).map((point) => point.forecast))
        .toEqual(Array.from({ length: horizon }, (_, index) => 1001 + index));
    }
  });

  it("splits W1 into seven profile-weighted daily values that reconcile", () => {
    const series = buildDemandChartSeries(source(), {
      grain: "daily",
      horizonWeeks: 16,
    });
    const actual = series.points.slice(0, 7);
    const forecast = series.points.slice(7);

    expect(actual.map((point) => point.label)).toEqual([
      "D-7", "D-6", "D-5", "D-4", "D-3", "D-2", "D-1",
    ]);
    expect(forecast.map((point) => point.label)).toEqual([
      "D+1", "D+2", "D+3", "D+4", "D+5", "D+6", "D+7",
    ]);
    expect(sum(actual.map((point) => point.actual))).toBeCloseTo(source().actual_w1, 10);
    expect(sum(forecast.map((point) => point.forecast))).toBeCloseTo(source().forecast_w1, 10);
    expect(series.points.every((point) => !point.label.includes("W0"))).toBe(true);
  });

  it("builds exact four-week Monthly buckets", () => {
    const series = buildDemandChartSeries(source(), {
      grain: "monthly",
      horizonWeeks: 8,
    });

    expect(series.points.map((point) => point.label)).toEqual([
      "M-4", "M-3", "M-2", "M-1", "M+1", "M+2",
    ]);
    expect(series.points.slice(0, 4).map((point) => point.actual)).toEqual([
      160 + 150 + 140 + 130,
      120 + 110 + 100 + 90,
      80 + 70 + 60 + 50,
      40 + 30 + 20 + 10,
    ]);
    expect(series.points.slice(4).map((point) => point.forecast)).toEqual([
      1001 + 1002 + 1003 + 1004,
      1005 + 1006 + 1007 + 1008,
    ]);
  });

  it("enables Quarterly only at 16W and uses full 13-week buckets", () => {
    expect(isDemandGrainEnabled("quarterly", 8)).toBe(false);
    expect(isDemandGrainEnabled("quarterly", 16)).toBe(true);
    expect(isDemandGrainEnabled("yearly", 16)).toBe(false);

    const series = buildDemandChartSeries(source(), {
      grain: "quarterly",
      horizonWeeks: 16,
    });
    expect(series.points.map((point) => point.label)).toEqual([
      "Q-4", "Q-3", "Q-2", "Q-1", "Q+1",
    ]);
    expect(series.points.slice(0, 4).map((point) => point.actual)).toEqual([
      sum(Array.from({ length: 13 }, (_, index) => (52 - index) * 10)),
      sum(Array.from({ length: 13 }, (_, index) => (39 - index) * 10)),
      sum(Array.from({ length: 13 }, (_, index) => (26 - index) * 10)),
      sum(Array.from({ length: 13 }, (_, index) => (13 - index) * 10)),
    ]);
    expect(series.points.at(-1).forecast).toBe(
      sum(Array.from({ length: 13 }, (_, index) => 1001 + index)),
    );
    expect(buildDemandChartSeries(source(), { grain: "quarterly", horizonWeeks: 8 }).points)
      .toEqual([]);
    expect(buildDemandChartSeries(source(), { grain: "yearly", horizonWeeks: 16 }).points)
      .toEqual([]);
  });

  it("keeps confidence centers SQL-backed while retaining the existing illustrative band method", () => {
    const series = buildConfidenceSeries(source(), 8, 92.4, 1.645);
    expect(series.points.slice(0, 12).map((point) => point.actual)).toEqual(
      Array.from({ length: 12 }, (_, index) => (12 - index) * 10),
    );
    expect(series.points.slice(12).map((point) => point.forecast)).toEqual(
      Array.from({ length: 8 }, (_, index) => 1001 + index),
    );
    expect(series.points.slice(12).every((point) => point.confidence_low != null)).toBe(true);
    expect(series.points.slice(0, 12).every((point) => point.confidence_low == null)).toBe(true);
  });

  it("pads the Demand Outlook domain from visible actual and forecast values", () => {
    expect(getDemandChartYAxisDomain([
      { actual: 100, forecast: null },
      { actual: null, forecast: 200 },
    ])).toEqual([90, 210]);
  });

  it("includes confidence bounds, clamps below zero, and gives flat data room", () => {
    const points = [
      { actual: 100, forecast: 110, confidence_low: 80, confidence_high: 140 },
    ];
    expect(getDemandChartYAxisDomain(points)).toEqual([98.7, 111.3]);
    expect(getDemandChartYAxisDomain(points, { includeConfidence: true }))
      .toEqual([74, 146]);
    expect(getDemandChartYAxisDomain([
      { actual: 0, forecast: 100, confidence_low: 0, confidence_high: 100 },
    ], { includeConfidence: true })).toEqual([0, 110]);
    expect(getDemandChartYAxisDomain([{ actual: 100, forecast: 100 }]))
      .toEqual([94, 106]);
  });

  it("adds a visual transition without inserting W0", () => {
    const sourcePoints = buildDemandChartSeries(source(), {
      grain: "weekly",
      horizonWeeks: 4,
    }).points;
    const transition = buildDemandTransitionData(sourcePoints);

    expect(transition.data).toHaveLength(sourcePoints.length);
    expect(transition.data.map((point) => point.label)).not.toContain("W0");
    expect(transition.lastActualKey).toBe("W-1");
    expect(transition.firstForecastKey).toBe("W+1");
    expect(transition.data.find((point) => point.key === "W-1").forecast_transition)
      .toBe(source().actual_w1);
    expect(transition.data.find((point) => point.key === "W+1").forecast_transition)
      .toBe(source().forecast_w1);
    expect(transition.data.filter((point) => point.forecast_transition != null))
      .toHaveLength(2);
  });
});
