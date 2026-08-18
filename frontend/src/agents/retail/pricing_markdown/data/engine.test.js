/**
 * The What-If engine re-runs f01..f07 (+f12/f14/f20-f22) from each item's
 * CHAIN-level inputs (position, on_hand, open_po — all from the ENGINE
 * table, which the audit did not flag as broken). The fixture's shipped
 * `at_risk_value` / `recoverable_value` / `state`, by contrast, are summed
 * or chosen from that SKU's STORE-level rows (ENGINE_STORE), per the
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
  it("has no modelled effect on at-risk or recoverable value", () => {
    const item = fixture.items.find((i) => i.is_markdown_candidate);
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, markdown: 40 });
    expect(scenario.at_risk_value).toBeCloseTo(baseline.at_risk_value, 6);
    expect(scenario.recoverable_value).toBeCloseTo(baseline.recoverable_value, 6);
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
