/**
 * Regression coverage for `topGroups`: it used to return the literal field
 * name ("vertical_id") as every group's `key` instead of that group's own
 * value ("GRC", "ELC", ...), which meant `buildDrilldown` labelled every
 * by-vertical and by-category bar identically and React warned about
 * duplicate list keys. Fixed by mapping `[k, rs]` to `key: k`, not `key`.
 */

import { describe, expect, it } from "vitest";

import fixture from "./fixture.json";
import { buildDrilldown, drillableMetrics } from "./drilldown.js";

describe("buildDrilldown", () => {
  it("labels by-vertical rows with real, distinct vertical ids", () => {
    const drilldown = buildDrilldown("incremental_margin", fixture.items);

    const verticalIds = drilldown.by_vertical.map((row) => row.vertical_id);
    expect(new Set(verticalIds).size).toBe(verticalIds.length);
    for (const id of verticalIds) {
      expect(id).not.toBe("vertical_id");
      expect(fixture.items.some((item) => item.vertical_id === id)).toBe(true);
    }
  });

  it("labels by-category rows with real, distinct category ids", () => {
    const drilldown = buildDrilldown("incremental_margin", fixture.items);

    const categoryIds = drilldown.by_category.map((row) => row.category_id);
    expect(new Set(categoryIds).size).toBe(categoryIds.length);
    for (const id of categoryIds) {
      expect(id).not.toBe("category_id");
      expect(fixture.items.some((item) => item.category_id === id)).toBe(true);
    }
  });

  it("sums by-vertical rows back to the additive metric's total", () => {
    const drilldown = buildDrilldown("incremental_margin", fixture.items);
    const byVerticalTotal = drilldown.by_vertical.reduce((t, r) => t + r.value, 0);
    expect(byVerticalTotal).toBeCloseTo(drilldown.total, -1);
  });

  it("only opens from the metrics that actually decompose to a total", () => {
    expect(drillableMetrics()).toEqual(
      expect.arrayContaining(["incremental_margin", "cannibalisation_pct", "supplier_funding"]),
    );
    expect(drillableMetrics()).not.toContain("uplift_pct");
    expect(drillableMetrics()).not.toContain("roi_x");
  });
});
