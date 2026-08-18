import { describe, expect, it } from "vitest";

import { candidatesOf } from "./selectors.js";
import { buildDrilldown, drillableMetrics, drilldownMetric } from "./drilldown.js";
import fixture from "./fixture.json";

describe("drillableMetrics", () => {
  it("lists at_risk_value, recoverable_value and write_off_value", () => {
    expect(drillableMetrics()).toEqual(
      expect.arrayContaining(["at_risk_value", "recoverable_value", "write_off_value"]),
    );
  });

  it("throws for an unknown metric", () => {
    expect(() => drilldownMetric("not_a_metric")).toThrow(/no drilldown metric/);
  });
});

describe("buildDrilldown", () => {
  const candidates = candidatesOf(fixture.items);

  it("total matches the sum of the reduced metric over the given items", () => {
    const built = buildDrilldown("at_risk_value", candidates);
    const expected = Math.round(candidates.reduce((t, i) => t + i.at_risk_value, 0));
    expect(built.total).toBe(expected);
    expect(built.sku_count).toBe(candidates.length);
  });

  it("names the top contributing SKUs, sorted descending", () => {
    const built = buildDrilldown("at_risk_value", candidates);
    for (let i = 1; i < built.top_skus.length; i++) {
      expect(built.top_skus[i - 1].value).toBeGreaterThanOrEqual(built.top_skus[i].value);
    }
  });

  it("history is always null — the workbook has one snapshot day", () => {
    const built = buildDrilldown("at_risk_value", candidates);
    expect(built.history).toBeNull();
  });
});
