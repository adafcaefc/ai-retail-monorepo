import { describe, expect, it } from "vitest";

import { candidatesOf, computeKpis, distinctBySku } from "./selectors.js";
import { buildDrilldown, drillableMetrics, drilldownMetric } from "./drilldown.js";
import { BASELINE_LEVERS } from "./contract.js";
import fixture from "./fixture.json";

describe("drillableMetrics", () => {
  it("lists at_risk_value, recoverable_value, write_off_value, avg_depth_pct and comp_idx", () => {
    expect(drillableMetrics()).toEqual(
      expect.arrayContaining([
        "at_risk_value",
        "recoverable_value",
        "write_off_value",
        "avg_depth_pct",
        "comp_idx",
      ]),
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

  // Regression test: computeCandidates used to drop category_id/vertical_id,
  // so these breakdowns silently rendered empty for every drillable metric.
  it("by_category and by_vertical are non-empty for an additive metric", () => {
    const built = buildDrilldown("at_risk_value", candidates);
    expect(built.by_category.length).toBeGreaterThan(0);
    expect(built.by_vertical.length).toBeGreaterThan(0);
  });

  it("avg_depth_pct is a non-additive weighted average matching the KPI formula", () => {
    // markdown lever at the workbook's own rest position (25, matching B6)
    // -- 0 is not baseline for this lever, see contract.js's LEVER_DEFINITIONS.
    const built = buildDrilldown("avg_depth_pct", candidates, { markdownLever: BASELINE_LEVERS.markdown });
    expect(built.additive).toBe(false);
    expect(built.total).toBeGreaterThan(0);
    expect(built.by_category.length).toBeGreaterThan(0);
    expect(built.by_vertical.length).toBeGreaterThan(0);
  });

  // comp_idx is a per-SKU figure, not an at-risk one — its drawer is built
  // from the full SKU population (dashboard.sku_index in production, here
  // distinctBySku(fixture.items)), not the candidate rows every other
  // metric's drawer uses. See dashboardData.js's loadPricingMarkdownDrilldown.
  it("comp_idx is a non-additive mean of comp_idx over every distinct SKU, matching the KPI tile", () => {
    const skuIndex = distinctBySku(fixture.items);
    const built = buildDrilldown("comp_idx", skuIndex);
    expect(built.additive).toBe(false);
    expect(built.total).toBeGreaterThan(0);
    expect(built.total).toBeCloseTo(computeKpis(fixture.items).comp_idx, 1);
    expect(built.by_category.length).toBeGreaterThan(0);
    expect(built.by_vertical.length).toBeGreaterThan(0);
  });
});
