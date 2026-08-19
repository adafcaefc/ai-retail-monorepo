import { describe, expect, it } from "vitest";

import {
  TOP_FORECAST_DIMENSION_LIMIT,
  takeTopForecastDimensions,
} from "./topForecastDimensions.js";

function dimension(id, forecast, label = id) {
  return { id, label, forecast_units: forecast };
}

describe("top Forecast Dimension rows", () => {
  it("returns the 20 highest category forecasts in numeric order", () => {
    const categories = Array.from({ length: 21 }, (_unused, index) =>
      dimension(`C-${index + 1}`, index + 1, `Category ${index + 1}`),
    ).reverse();

    const top = takeTopForecastDimensions(categories);

    expect(top).toHaveLength(TOP_FORECAST_DIMENSION_LIMIT);
    expect(top[0].forecast_units).toBe(21);
    expect(top.at(-1).forecast_units).toBe(2);
    expect(top.some((row) => row.id === "C-1")).toBe(false);
  });

  it("returns the 20 highest store forecasts and excludes the 21st", () => {
    const stores = Array.from({ length: 25 }, (_unused, index) =>
      dimension(`S-${index + 1}`, 1000 + index * 100, `Store ${index + 1}`),
    );

    const top = takeTopForecastDimensions(stores);

    expect(top).toHaveLength(20);
    expect(top.map((row) => row.forecast_units)).toEqual(
      Array.from({ length: 20 }, (_unused, index) => 3400 - index * 100),
    );
    expect(top.some((row) => row.id === "S-5")).toBe(false);
  });

  it("sorts ties by label, keeps smaller sets, and does not mutate input", () => {
    const rows = [
      dimension("Z-1", 100, "Zeta"),
      dimension("A-1", 100, "Alpha"),
      dimension("B-1", 80, "Beta"),
    ];
    const original = [...rows];

    const top = takeTopForecastDimensions(rows);

    expect(top.map((row) => row.label)).toEqual(["Alpha", "Zeta", "Beta"]);
    expect(top).toHaveLength(3);
    expect(rows).toEqual(original);
  });

  it("limits the already-filtered result set rather than a global source set", () => {
    const allRows = [
      dimension("OTHER-1", 10000, "Other high forecast"),
      dimension("GRC-1", 300, "GRC first"),
      dimension("GRC-2", 200, "GRC second"),
    ];
    const filteredRows = allRows.filter((row) => row.id.startsWith("GRC-"));

    expect(takeTopForecastDimensions(filteredRows).map((row) => row.id)).toEqual([
      "GRC-1",
      "GRC-2",
    ]);
  });
});
