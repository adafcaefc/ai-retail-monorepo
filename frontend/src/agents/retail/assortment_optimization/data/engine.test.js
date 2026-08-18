/**
 * The engine re-derives the whole productivity chain from a lever-driven
 * ADS. Unlike the Pricing & Markdown board — whose shipped figures are
 * store-grain sums and therefore a different grain from what its engine
 * computes — Agent 6's shipped `contribution_per_day` IS the chain figure
 * this engine reproduces (verified against all 800 rows before the engine
 * was written). So here the baseline round-trip is a real assertion, and
 * this suite makes it.
 */

import { describe, expect, it } from "vitest";

import { BASELINE_LEVERS, STATE_ORDER } from "./contract.js";
import { createEngine, isBaseline } from "./engine.js";
import fixture from "./fixture.json";

const applyLevers = createEngine(fixture.formulas, fixture.classification_thresholds);

describe("at the workbook's own lever setting (baseline)", () => {
  it("reproduces every item's contribution/day within floating-point noise", () => {
    for (const item of fixture.items) {
      const result = applyLevers(item, BASELINE_LEVERS);
      const shipped = Number(item.contribution_per_day) || 0;
      if (shipped === 0) continue;
      const relative = Math.abs(result.contribution_per_day - shipped) / shipped;
      expect(relative).toBeLessThan(1e-4);
    }
  });

  it("reproduces every item's GMROI within floating-point noise", () => {
    for (const item of fixture.items) {
      const result = applyLevers(item, BASELINE_LEVERS);
      const shipped = Number(item.gmroi) || 0;
      if (shipped === 0) continue;
      const relative = Math.abs(result.gmroi - shipped) / shipped;
      expect(relative).toBeLessThan(1e-3);
    }
  });

  it("reproduces the shipped classification for every item", () => {
    for (const item of fixture.items) {
      const result = applyLevers(item, BASELINE_LEVERS);
      expect(result.classification).toBe(item.classification);
    }
  });

  it("recognizes the baseline position", () => {
    expect(isBaseline(BASELINE_LEVERS)).toBe(true);
    expect(isBaseline({ ...BASELINE_LEVERS, demand: 5 })).toBe(false);
  });

  it("only ever assigns a state from the workbook's six", () => {
    for (const item of fixture.items.slice(0, 100)) {
      expect(STATE_ORDER).toContain(applyLevers(item, BASELINE_LEVERS).state);
    }
  });
});

describe("with the demand lever raised", () => {
  it("raises contribution/day", () => {
    const item = fixture.items[0];
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, demand: 30 });
    expect(scenario.contribution_per_day).toBeGreaterThan(baseline.contribution_per_day);
  });

  it("shrinks the tail across the whole range", () => {
    const baselineTail = fixture.items.filter((i) => applyLevers(i, BASELINE_LEVERS).is_tail).length;
    const scenarioTail = fixture.items.filter(
      (i) => applyLevers(i, { ...BASELINE_LEVERS, demand: 40 }).is_tail,
    ).length;
    expect(scenarioTail).toBeLessThan(baselineTail);
  });
});

describe("with the markdown lever moved", () => {
  it("has no modelled effect on contribution or GMROI", () => {
    const item = fixture.items[0];
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, markdown: 50 });
    expect(scenario.contribution_per_day).toBeCloseTo(baseline.contribution_per_day, 6);
    expect(scenario.gmroi).toBeCloseTo(baseline.gmroi, 6);
  });
});

describe("with the inbound lever raised", () => {
  it("raises position and therefore inventory value", () => {
    const item = fixture.items[0];
    const baseline = applyLevers(item, BASELINE_LEVERS);
    const scenario = applyLevers(item, { ...BASELINE_LEVERS, inbound: 50 });
    expect(scenario.position).toBeGreaterThan(baseline.position);
    expect(scenario.inv_value).toBeGreaterThan(baseline.inv_value);
  });
});

describe("best_action_tab", () => {
  it("is left null — it is a population-level decision selectors.js owns", () => {
    const result = applyLevers(fixture.items[0], BASELINE_LEVERS);
    expect(result.best_action_tab).toBeNull();
  });
});
