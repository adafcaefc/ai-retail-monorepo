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
    // Mirrors a live Formula Manager edit that adds a term this engine has no
    // way to know about ahead of time. `store_horizon_multiplier` is a stand-in
    // for "some future field" — it must NOT be `arch_horizon_factor`, which
    // v8.5 made a real f01 term with a real (non-1) value on every item (see
    // `engine.js`'s `run`), so patching that name back in would not exercise
    // the "genuinely unknown" fallback this test is about.
    const patched = {
      ...fixture.formulas,
      "f01-ads-per-store": fixture.formulas["f01-ads-per-store"].replace(
        "store_size *",
        "store_size * store_horizon_multiplier *",
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

describe("arch_horizon_factor", () => {
  // Regression test for the Store filter crash: "Operator '*' needs a
  // number, got undefined". f01 references `arch_horizon_factor` for real
  // (v8.5), engine.js always supplies the key, and the Store filter (and any
  // What-If lever) unconditionally re-runs f01 via `atStore`/`applyLevers`
  // even at baseline — so every fixture item must carry a real numeric value,
  // not rely on the "unknown parameter" fallback above (that only fires when
  // the key is absent, not when it's present but undefined).
  it("is a finite number on every promo-eligible item", () => {
    for (const item of fixture.items) {
      expect(Number.isFinite(item.arch_horizon_factor)).toBe(true);
    }
  });

  it("does not throw when the Store filter re-runs f01 at baseline levers", () => {
    const item = fixture.items[0];
    const store = fixture.stores.find((s) => s.vertical_id === item.vertical_id);
    expect(() => applyLevers(atStore(item, store), BASELINE_LEVERS)).not.toThrow();
  });

  it("does not throw when a What-If lever moves", () => {
    const item = fixture.items[0];
    expect(() => applyLevers(item, { ...BASELINE_LEVERS, promo: 20 })).not.toThrow();
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
