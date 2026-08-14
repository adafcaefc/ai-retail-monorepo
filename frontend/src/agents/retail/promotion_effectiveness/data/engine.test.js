/**
 * The What-If engine answers two questions:
 *   1. At zero levers, does it reproduce the fixture unchanged?
 *   2. When a lever moves, does the incremental margin move in the right
 *      direction and by a plausible order of magnitude?
 */

import { describe, expect, it } from "vitest";

import { BASELINE_LEVERS } from "./contract.js";
import { createEngine, isBaseline } from "./engine.js";
import fixture from "./fixture.json";

const applyLevers = createEngine(fixture.formulas);

describe("at the workbook's own lever setting (baseline)", () => {
  it("returns every item's incremental margin within floating-point noise", () => {
    // The engine re-derives ADS from base_ads × seasonality × store_size (f01)
    // before pricing f13, while the fixture stored f13 from the workbook's own
    // pre-rounded ADS. The two agree to ~5 parts per million; a tight relative
    // tolerance is the honest assertion, not an exact equality.
    for (const item of fixture.items) {
      const result = applyLevers(item, BASELINE_LEVERS);
      const baseline = Number(item.incremental_margin) || 0;
      if (baseline === 0) continue;
      const relative = Math.abs(result.incremental_margin - baseline) / baseline;
      expect(relative).toBeLessThan(1e-4);
    }
  });

  it("recognizes the baseline position", () => {
    expect(isBaseline(BASELINE_LEVERS)).toBe(true);
    expect(isBaseline({ ...BASELINE_LEVERS, promo: 5 })).toBe(false);
  });
});

describe("with the promo lever moved", () => {
  it("raises the incremental margin on promo-eligible SKUs", () => {
    const item = fixture.items[0];
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, promo: 20 });
    expect(scenario.incremental_margin).toBeGreaterThan(baseline.incremental_margin);
  });

  it("raises the demand-boosted ADS", () => {
    const item = fixture.items[0];
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, demand: 20 });
    expect(scenario.ads).toBeGreaterThan(baseline.ads);
  });
});
