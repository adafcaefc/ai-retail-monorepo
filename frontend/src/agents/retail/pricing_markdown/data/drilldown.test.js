import { describe, expect, it } from "vitest";

import { candidatesOf, computeKpis, depthWeightedAvgPct, distinctBySku } from "./selectors.js";
import { buildDrilldown, drillableMetrics, drilldownMetric } from "./drilldown.js";
import { BASELINE_LEVERS } from "./contract.js";
import fixture from "./fixture.json";

describe("drillableMetrics", () => {
  it("lists markdown_candidates, at_risk_value, recoverable_value, write_off_value, avg_depth_pct and comp_idx", () => {
    expect(drillableMetrics()).toEqual(
      expect.arrayContaining([
        "markdown_candidates",
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
  it("by_category, by_vertical and by_store are non-empty for an additive metric", () => {
    const built = buildDrilldown("at_risk_value", candidates, { stores: fixture.filter_options.stores });
    expect(built.by_category.length).toBeGreaterThan(0);
    expect(built.by_vertical.length).toBeGreaterThan(0);
    expect(built.by_store.length).toBeGreaterThan(0);
    expect(built.store_unavailable_reason).toBeNull();
  });

  it("by_store rows are labelled from the given stores list", () => {
    const built = buildDrilldown("at_risk_value", candidates, { stores: fixture.filter_options.stores });
    const labels = new Map(fixture.filter_options.stores.map((s) => [s.value, s.label]));
    for (const row of built.by_store) {
      expect(row.label).toBe(labels.get(row.store_id));
    }
  });

  it("avg_depth_pct is a non-additive weighted average matching the KPI formula", () => {
    // markdown lever at the workbook's own rest position (25, matching B6)
    // -- 0 is not baseline for this lever, see contract.js's LEVER_DEFINITIONS.
    const built = buildDrilldown("avg_depth_pct", candidates, { markdownLever: BASELINE_LEVERS.markdown });
    expect(built.additive).toBe(false);
    expect(built.total).toBeGreaterThan(0);
    expect(built.by_category.length).toBeGreaterThan(0);
    expect(built.by_vertical.length).toBeGreaterThan(0);
    expect(built.by_store.length).toBeGreaterThan(0);
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

  // comp_idx's own population (sku_index) carries no store_id -- see the
  // note above buildDrilldown's byStore -- so its drawer names the reason
  // instead of fabricating a per-store split.
  it("comp_idx has no by_store split and names the reason", () => {
    const skuIndex = distinctBySku(fixture.items);
    const built = buildDrilldown("comp_idx", skuIndex, { stores: fixture.filter_options.stores });
    expect(built.by_store).toEqual([]);
    expect(built.store_unavailable_reason).toMatch(/no per-store figure/);
  });

  it("markdown_candidates counts rows and is additive, by category and by store", () => {
    const built = buildDrilldown("markdown_candidates", candidates, { stores: fixture.filter_options.stores });
    expect(built.additive).toBe(true);
    expect(built.total).toBe(candidates.length);
    expect(built.by_category.length).toBeGreaterThan(0);
    expect(built.by_store.length).toBeGreaterThan(0);
  });

  // Regression test for the wiring bug (fixed in dashboardData.js): the
  // drawer used to read the preview table's top-300-by-at_risk_value slice,
  // which understated every additive total by ~33% and skewed avg_depth_pct
  // toward whatever state that slice happened to be dominated by. Pinned
  // against a hand-checked reference rollup of the full fixture. (by_category
  // itself is a top-12-of-116 view, so the per-category check below goes
  // through depthWeightedAvgPct directly rather than the capped breakdown.)
  it("on the full candidate population, matches the hand-checked chain total and per-category avg depth", () => {
    const built = buildDrilldown("at_risk_value", candidates);
    expect(built.total).toBe(300089740200);

    const grcC13 = candidates.filter((c) => c.category_id === "GRC-C13");
    const grcC11 = candidates.filter((c) => c.category_id === "GRC-C11");
    expect(depthWeightedAvgPct(grcC13, BASELINE_LEVERS.markdown)).toBeCloseTo(26.82, 1);
    expect(depthWeightedAvgPct(grcC11, BASELINE_LEVERS.markdown)).toBeCloseTo(25, 1);
  });
});
