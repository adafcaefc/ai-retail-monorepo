import { describe, expect, it } from "vitest";

import {
  buildConfidenceSeries,
  buildDemandChartSeries,
  buildDemandTransitionData,
  chartSourceColumns,
  getDemandChartYAxisDomain,
  getDemandScenarioYAxisDomain,
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
      expect(series.history_count).toBe(52);
      expect(series.points.slice(0, 52).map((point) => point.label))
        .toEqual(Array.from({ length: 52 }, (_, index) => `W-${52 - index}`));
      expect(series.points.slice(52).map((point) => point.label))
        .toEqual(Array.from({ length: horizon }, (_, index) => `W+${index + 1}`));
      expect(series.points.slice(52).map((point) => point.forecast))
        .toEqual(Array.from({ length: horizon }, (_, index) => 1001 + index));
    }
  });

  it("expands four ordered historical weeks and Horizon forecast weeks into daily blocks", () => {
    for (const horizon of [4, 8, 12, 16]) {
      const series = buildDemandChartSeries(source(), {
        grain: "daily",
        horizonWeeks: horizon,
      });
      const actual = series.points.slice(0, 28);
      const forecast = series.points.slice(28);

      expect(series.history_count).toBe(28);
      expect(actual).toHaveLength(28);
      expect(forecast).toHaveLength(horizon * 7);
      expect(actual.map((point) => point.label)).toEqual(
        Array.from({ length: 28 }, (_, index) => `D-${28 - index}`),
      );
      expect(forecast.map((point) => point.label)).toEqual(
        Array.from({ length: horizon * 7 }, (_, index) => `D+${index + 1}`),
      );

      [4, 3, 2, 1].forEach((week, index) => {
        const block = actual.slice(index * 7, index * 7 + 7);
        expect(sum(block.map((point) => point.actual)))
          .toBeCloseTo(source()[`actual_w${week}`], 10);
      });
      for (let week = 1; week <= horizon; week += 1) {
        const block = forecast.slice((week - 1) * 7, week * 7);
        expect(sum(block.map((point) => point.forecast)))
          .toBeCloseTo(source()[`forecast_w${week}`], 10);
      }

      expect(series.points.every((point) => !point.label.includes("D0"))).toBe(true);
    }
  });

  it("builds twelve four-week Monthly buckets from the latest 48 actual weeks", () => {
    const series = buildDemandChartSeries(source(), {
      grain: "monthly",
      horizonWeeks: 8,
    });

    expect(series.points.map((point) => point.label)).toEqual([
      "M-12", "M-11", "M-10", "M-9", "M-8", "M-7",
      "M-6", "M-5", "M-4", "M-3", "M-2", "M-1", "M+1", "M+2",
    ]);
    expect(series.history_count).toBe(12);
    expect(series.points.slice(0, 12).map((point) => point.actual)).toEqual([
      480 + 470 + 460 + 450,
      440 + 430 + 420 + 410,
      400 + 390 + 380 + 370,
      360 + 350 + 340 + 330,
      320 + 310 + 300 + 290,
      280 + 270 + 260 + 250,
      240 + 230 + 220 + 210,
      200 + 190 + 180 + 170,
      160 + 150 + 140 + 130,
      120 + 110 + 100 + 90,
      80 + 70 + 60 + 50,
      40 + 30 + 20 + 10,
    ]);
    expect(sum(series.points.slice(0, 12).map((point) => point.actual))).toBe(
      sum(Array.from({ length: 48 }, (_, index) => (48 - index) * 10)),
    );
    expect(series.points.slice(12).map((point) => point.forecast)).toEqual([
      1001 + 1002 + 1003 + 1004,
      1005 + 1006 + 1007 + 1008,
    ]);
  });

  it("shows four forecast quarters regardless of the selected Horizon", () => {
    expect(isDemandGrainEnabled("yearly", 16)).toBe(true);

    for (const horizon of [4, 8, 12, 16]) {
      expect(isDemandGrainEnabled("quarterly", horizon)).toBe(true);

      const series = buildDemandChartSeries(source(), {
        grain: "quarterly",
        horizonWeeks: horizon,
      });
      expect(series.history_count).toBe(4);
      expect(series.points.map((point) => point.label)).toEqual([
        "Q-4", "Q-3", "Q-2", "Q-1", "Q+1", "Q+2", "Q+3", "Q+4",
      ]);
      expect(series.points.slice(0, 4).map((point) => point.actual)).toEqual([
        sum(Array.from({ length: 13 }, (_, index) => (52 - index) * 10)),
        sum(Array.from({ length: 13 }, (_, index) => (39 - index) * 10)),
        sum(Array.from({ length: 13 }, (_, index) => (26 - index) * 10)),
        sum(Array.from({ length: 13 }, (_, index) => (13 - index) * 10)),
      ]);
      expect(series.points.slice(4).map((point) => point.forecast)).toEqual(
        Array.from({ length: 4 }, (_, quarter) =>
          sum(Array.from({ length: 13 }, (_, index) => 1001 + quarter * 13 + index)),
        ),
      );
    }
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

  it("builds Yearly from the complete 52-week actual and forecast ranges", () => {
    for (const horizon of [4, 8, 12, 16]) {
      const series = buildDemandChartSeries(source(), {
        grain: "yearly",
        horizonWeeks: horizon,
      });

      expect(series.history_count).toBe(1);
      expect(series.points.map((point) => point.label)).toEqual(["Y-1", "Y+1"]);
      expect(series.points[0].actual).toBe(
        sum(Array.from({ length: 52 }, (_, index) => (52 - index) * 10)),
      );
      expect(series.points[1].forecast).toBe(
        sum(Array.from({ length: 52 }, (_, index) => 1001 + index)),
      );
    }
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

describe("Compare Scenarios Y-axis domain", () => {
  it("uses baseline and every visible saved scenario point", () => {
    expect(getDemandScenarioYAxisDomain([
      { label: "W+1", baseline: 370000, scenario_a: 500000, scenario_b: 520000 },
      { label: "W+2", baseline: 400000, scenario_a: 450000, scenario_b: 480000 },
    ])).toEqual([355000, 535000]);
  });

  it("ignores labels and invalid values while keeping the domain non-negative", () => {
    expect(getDemandScenarioYAxisDomain([
      { label: "W+1", baseline: -40, scenario_a: 100, scenario_b: Number.NaN },
      { label: "W+2", baseline: null, scenario_a: Number.POSITIVE_INFINITY },
    ])).toEqual([0, 114]);
  });

  it("gives nearly-flat series a useful minimum range", () => {
    const [minimum, maximum] = getDemandScenarioYAxisDomain([
      { label: "W+1", baseline: 400000, scenario_a: 400000 },
      { label: "W+2", baseline: 400100, scenario_a: 400050 },
    ]);

    expect(minimum).toBeGreaterThanOrEqual(0);
    expect(maximum - minimum).toBeGreaterThan(1000);
  });
});
