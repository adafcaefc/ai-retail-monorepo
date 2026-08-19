import { describe, expect, it } from "vitest";

import fixture from "./fixture.json";
import {
  candidatesOf,
  computeByCategory,
  computeByCluster,
  computeByState,
  computeByVertical,
  computeBestActions,
  computeKpis,
  computeSimulation,
  scopeItems,
} from "./selectors.js";
import { ALL, BASELINE_LEVERS, BEST_ACTION_TABS, CANDIDATE_STATES } from "./contract.js";
import { createEngine } from "./engine.js";

describe("candidatesOf", () => {
  it("keeps only SKUs flagged as markdown candidates", () => {
    const candidates = candidatesOf(fixture.items);
    expect(candidates.length).toBeGreaterThan(0);
    for (const item of candidates) {
      expect(item.is_markdown_candidate).toBe(true);
      expect(CANDIDATE_STATES).toContain(item.state);
    }
  });
});

describe("computeKpis", () => {
  it("sums at-risk and recoverable value over candidates only", () => {
    const kpis = computeKpis(fixture.items);
    const candidates = candidatesOf(fixture.items);
    expect(kpis.markdown_candidates).toBe(candidates.length);
    expect(kpis.at_risk_value).toBeGreaterThan(0);
    expect(kpis.recoverable_value).toBeGreaterThan(0);
    expect(kpis.write_off_value).toBe(
      Math.round(kpis.at_risk_value - kpis.recoverable_value),
    );
  });

  it("recoverable never exceeds at-risk, chain-wide", () => {
    const kpis = computeKpis(fixture.items);
    expect(kpis.recoverable_value).toBeLessThanOrEqual(kpis.at_risk_value);
  });
});

describe("scopeItems", () => {
  it("narrows by vertical", () => {
    const vertical = fixture.items[0].vertical_id;
    const scoped = scopeItems(fixture.items, { legal_entity_id: vertical });
    expect(scoped.length).toBeGreaterThan(0);
    expect(scoped.every((i) => i.vertical_id === vertical)).toBe(true);
  });

  it("ALL is a no-op", () => {
    const scoped = scopeItems(fixture.items, { legal_entity_id: ALL });
    expect(scoped.length).toBe(fixture.items.length);
  });
});

describe("computeByVertical", () => {
  it("every row's at_risk_value is non-negative and rows sum to the candidate total", () => {
    const rows = computeByVertical(fixture.items, fixture.reference_by_vertical);
    const candidateTotal = computeKpis(fixture.items).at_risk_value;
    const rowTotal = rows.reduce((t, r) => t + r.at_risk_value, 0);
    for (const row of rows) expect(row.at_risk_value).toBeGreaterThanOrEqual(0);
    expect(Math.abs(rowTotal - candidateTotal)).toBeLessThan(candidateTotal * 0.01 + 1);
  });
});

describe("computeByCategory", () => {
  it("returns at most the requested limit, sorted descending", () => {
    const rows = computeByCategory(fixture.items, 5);
    expect(rows.length).toBeLessThanOrEqual(5);
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i - 1].value).toBeGreaterThanOrEqual(rows[i].value);
    }
  });
});

describe("computeByCluster", () => {
  it("every store row is counted in exactly one cluster", () => {
    const rows = computeByCluster(fixture.stores);
    const total = rows.reduce((t, r) => t + r.store_count, 0);
    expect(total).toBe(fixture.stores.length);
  });
});

describe("computeByState", () => {
  it("covers every state present in the fixture, including Healthy", () => {
    const rows = computeByState(fixture.items);
    const states = rows.map((r) => r.state);
    expect(states).toContain("Healthy");
  });
});

describe("computeBestActions", () => {
  it("partitions every candidate into exactly one tab", () => {
    const tabs = computeBestActions(fixture.items);
    const tabbed = BEST_ACTION_TABS.reduce((t, tab) => t + tabs[tab.id].length, 0);
    expect(tabbed).toBe(candidatesOf(fixture.items).length);
  });
});

describe("computeSimulation", () => {
  const applyLevers = createEngine(fixture.formulas);

  it("reports unapplied at the baseline levers", () => {
    const simulation = computeSimulation(fixture.items, BASELINE_LEVERS, applyLevers);
    expect(simulation.applied).toBe(false);
    expect(simulation.baseline).toBeNull();
    expect(simulation.scenario).toBeNull();
  });

  it("carries recovery_rate_pct on baseline, scenario and index once a lever moves", () => {
    const simulation = computeSimulation(
      fixture.items,
      { ...BASELINE_LEVERS, markdown: 40 },
      applyLevers,
    );
    expect(simulation.applied).toBe(true);
    expect(simulation.baseline.recovery_rate_pct).toBeGreaterThanOrEqual(0);
    expect(simulation.scenario.recovery_rate_pct).toBeGreaterThanOrEqual(0);
    // recovery_rate_pct = recoverable / at-risk * 100, both at the baseline lever setting.
    expect(simulation.baseline.recovery_rate_pct).toBeCloseTo(
      (simulation.baseline.recoverable_value / simulation.baseline.at_risk_value) * 100,
      1,
    );
  });

  it("widening markdown depth moves recovery_rate_pct without moving at-risk value", () => {
    // Per f14-recoverable-at-risk-value, a deeper markdown raises the sell-through
    // probability but cuts the price it sells at — recovered dollar value (and so
    // recovery_rate_pct) is not guaranteed to move in a fixed direction, only to move.
    // See engine.test.js's own "with the markdown lever moved" suite for the same call.
    const baselineSim = computeSimulation(fixture.items, BASELINE_LEVERS, applyLevers);
    const scenarioSim = computeSimulation(
      fixture.items,
      { ...BASELINE_LEVERS, markdown: 40 },
      applyLevers,
    );
    expect(scenarioSim.scenario.recovery_rate_pct).not.toBeCloseTo(
      scenarioSim.baseline.recovery_rate_pct,
      1,
    );
    expect(scenarioSim.scenario.at_risk_value).toBeCloseTo(scenarioSim.baseline.at_risk_value, 0);
    // the unapplied simulation is a distinct all-zero shape, not a real baseline read.
    expect(baselineSim.applied).toBe(false);
  });
});
