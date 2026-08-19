/**
 * The What-If engine answers two questions:
 *   1. At zero levers, does it reproduce the fixture unchanged?
 *   2. When a lever moves, does the incremental margin move in the right
 *      direction and by a plausible order of magnitude?
 */

import { describe, expect, it } from "vitest";

import { BASELINE_LEVERS } from "./contract.js";
import { atStore, createEngine, isBaseline } from "./engine.js";
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

describe("when the formula catalog references a parameter this engine doesn't supply", () => {
  it("defaults the unknown parameter to 1 instead of throwing", () => {
    // Mirrors a live Formula Manager edit that adds a term (e.g.
    // arch_horizon_factor) engine.js has no way to know about ahead of time.
    // The Store filter always re-runs f01 via `atStore`, even at baseline
    // levers, so this must not crash the board.
    const patched = {
      ...fixture.formulas,
      "f01-ads-per-store": fixture.formulas["f01-ads-per-store"].replace(
        "store_size *",
        "store_size * arch_horizon_factor *",
      ),
    };
    const patchedApplyLevers = createEngine(patched);
    const item = fixture.items[0];

    expect(() => patchedApplyLevers(item, BASELINE_LEVERS)).not.toThrow();

    // Defaulting the unknown factor to 1 is a no-op, so the result matches
    // the unpatched formula exactly.
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const patchedResult = patchedApplyLevers(item, BASELINE_LEVERS);
    expect(patchedResult.ads).toBeCloseTo(baseline.ads, 9);
    expect(patchedResult.incremental_margin).toBeCloseTo(baseline.incremental_margin, 9);
  });
});

describe("atStore", () => {
  it("reproduces a store's proportional share of an item's incremental margin", () => {
    // f01 is purely multiplicative in store_size and f13 is linear in ads, so
    // overriding store_size with one store's size_index should reproduce the
    // exact proportional split — the same relationship computeByStore relies
    // on in selectors.js, and that the fixture builder's verify_store_split
    // checks against the real ENGINE_STORE extract at build time.
    const item = fixture.items[0];
    const store = fixture.stores.find((s) => s.vertical_id === item.vertical_id);
    const atStoreResult = applyLevers(atStore(item, store), BASELINE_LEVERS);

    const expectedShare =
      (Number(item.incremental_margin) || 0) *
      (Number(store.size_index) / Number(item.store_size));

    expect(atStoreResult.incremental_margin).toBeCloseTo(expectedShare, 0);
  });
});
