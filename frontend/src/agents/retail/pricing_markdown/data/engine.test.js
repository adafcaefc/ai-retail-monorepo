/**
 * The What-If engine re-runs f01..f07 (+f12/f20-f22, plus f23 into f14) from
 * each item's CHAIN-level inputs (position, on_hand, open_po — all from the
 * ENGINE table, which the audit did not flag as broken). The fixture's
 * shipped `at_risk_value` / `recoverable_value` / `state`, by contrast, are
 * summed or chosen from that SKU's STORE-level rows (ENGINE_STORE), per the
 * decision to follow AUDIT Fix Register's F-05. Those are two different
 * grains by design (see contract.js's module docstring and RC-1 in the
 * audit: "one SKU can be Healthy chain-wide but Low in six stores") — so
 * this suite does NOT assert the engine reproduces the shipped baseline
 * figures. It asserts the engine is internally consistent and moves the
 * right direction when a lever moves.
 */

import { describe, expect, it } from "vitest";

import { BASELINE_LEVERS, STATE_ORDER } from "./contract.js";
import { createEngine, isBaseline } from "./engine.js";
import fixture from "./fixture.json";

const applyLevers = createEngine(fixture.formulas);

describe("at the workbook's own lever setting (baseline)", () => {
  it("recognizes the baseline position", () => {
    expect(isBaseline(BASELINE_LEVERS)).toBe(true);
    expect(isBaseline({ ...BASELINE_LEVERS, demand: 5 })).toBe(false);
  });

  it("is deterministic: the same item and levers always produce the same result", () => {
    const item = fixture.items[0];
    const first = applyLevers(item, BASELINE_LEVERS);
    const second = applyLevers(item, BASELINE_LEVERS);
    expect(second.at_risk_value).toBe(first.at_risk_value);
    expect(second.state).toBe(first.state);
  });

  it("only ever assigns a state from the workbook's six", () => {
    for (const item of fixture.items.slice(0, 100)) {
      const result = applyLevers(item, BASELINE_LEVERS);
      expect(STATE_ORDER).toContain(result.state);
    }
  });

  // Regression test: `lead_days` used to come from a designated-trade-agreement
  // sum that didn't match the workbook's own ROP/Max for several SKUs. At rest
  // that silently reclassified roughly half of GRC's rows the moment ANY
  // lever moved and "Drive whole page" re-ran f01-f07 (mostly Expiry -> Low/
  // Stockout, the state with the largest lead-time gap) — this asserts the
  // cascade reproduces the shipped state for the WHOLE population, not a
  // hand-picked item or a 100-row slice.
  it("reproduces the shipped state for every item in the fixture", () => {
    let mismatches = 0;
    for (const item of fixture.items) {
      if (applyLevers(item, BASELINE_LEVERS).state !== item.state) mismatches++;
    }
    expect(mismatches).toBe(0);
  });
});

describe("with the demand lever moved", () => {
  it("raises ADS", () => {
    const item = fixture.items.find((i) => i.is_markdown_candidate);
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, demand: 30 });
    expect(scenario.ads).toBeGreaterThan(baseline.ads);
  });

  it("lowers days-of-supply for a Slow-mover SKU", () => {
    const slowMover = fixture.items.find((i) => i.state === "Slow-mover");
    expect(slowMover).toBeDefined();
    const baseline = applyLevers(slowMover, BASELINE_LEVERS);
    const scenario = applyLevers(slowMover, { ...BASELINE_LEVERS, demand: 40 });
    expect(scenario.dos).toBeLessThan(baseline.dos);
  });
});

describe("with the markdown lever moved", () => {
  // f14-recoverable-at-risk-value is the one formula in this cascade that
  // reads `markdown`: it widens the recovery depth applied to f23's gross
  // exposure. Deeper is not always more recovered — past the point where
  // the recovery factor hits its 0.95 cap, a wider depth mostly gives away
  // margin for no further recovery credit — so this only asserts the lever
  // has SOME effect, not a fixed direction. f12-at-risk-value never reads
  // `markdown`, so at-risk stays exactly put.
  it("changes recoverable value but never at-risk value", () => {
    const item = fixture.items.find((i) => i.is_markdown_candidate);
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, markdown: 40 });
    expect(scenario.at_risk_value).toBeCloseTo(baseline.at_risk_value, 6);
    expect(scenario.recoverable_value).not.toBeCloseTo(baseline.recoverable_value, 2);
  });

  it("leaves state and position untouched — markdown depth is not a supply lever", () => {
    const item = fixture.items.find((i) => i.is_markdown_candidate);
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, markdown: 40 });
    expect(scenario.state).toBe(baseline.state);
    expect(scenario.position).toBe(baseline.position);
  });

  // The exact scenario the lead_days regression above guards: moving ONLY
  // the markdown lever, with "Drive whole page" re-running the full cascade,
  // must not reclassify a single item chain-wide.
  it("leaves every item's state untouched, chain-wide", () => {
    let mismatches = 0;
    for (const item of fixture.items) {
      if (applyLevers(item, { ...BASELINE_LEVERS, markdown: 40 }).state !== item.state) mismatches++;
    }
    expect(mismatches).toBe(0);
  });

  // Regression test: a driven item used to have no at_risk_gross field at
  // all, so depthWeightedAvgPct's weight (selectors.js) fell back to 0 for
  // every driven row under an active scenario. It's f14's own first input
  // (`gross`), so it must not move with the markdown lever itself.
  it("exposes at_risk_gross, f14's own gross input — unaffected by the markdown lever itself", () => {
    const item = fixture.items.find((i) => i.is_markdown_candidate);
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, markdown: 40 });
    expect(baseline.at_risk_gross).toBeGreaterThanOrEqual(0);
    expect(scenario.at_risk_gross).toBeCloseTo(baseline.at_risk_gross, 6);
  });
});

describe("with the inbound lever raised", () => {
  it("raises position", () => {
    const item = fixture.items.find((i) => i.is_markdown_candidate);
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, inbound: 40 });
    expect(scenario.position).toBeGreaterThan(baseline.position);
  });
});
