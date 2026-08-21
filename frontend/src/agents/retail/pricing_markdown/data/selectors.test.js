import { describe, expect, it } from "vitest";

import fixture from "./fixture.json";
import {
  buildDashboardFromFixture,
  candidatesOf,
  computeByCategory,
  computeByCluster,
  computeByState,
  computeByVertical,
  computeBestActions,
  computeCandidates,
  computeKpis,
  computeSimulation,
  depthWeightedAvgPct,
  distinctBySku,
  mean,
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

  // Regression test: comp_idx used to be averaged over candidatesOf(items)
  // only (~20% of SKUs), which does not match SKU_Master's own AVERAGEIFS in
  // the workbook — a per-SKU figure has to be averaged over every SKU.
  it("averages comp_idx over every distinct SKU in scope, not just markdown candidates", () => {
    const kpis = computeKpis(fixture.items);
    const expected = mean(distinctBySku(fixture.items).map((i) => i.comp_idx));
    expect(kpis.comp_idx).toBeCloseTo(expected, 1);

    const candidatesOnly = mean(candidatesOf(fixture.items).map((i) => i.comp_idx));
    // The two populations diverge in this dataset — pins that the fix is
    // actually wired to distinctBySku(items), not silently still candidates.
    expect(kpis.comp_idx).not.toBeCloseTo(candidatesOnly, 1);
  });
});

describe("depthWeightedAvgPct", () => {
  // Regression test: the weight used to be at_risk_value (f12, a row's full
  // position x price for any non-Healthy state) instead of at_risk_gross
  // (f23's own at-risk-PORTION output) — at_risk_value overstates the true
  // weight 3x-20x per row, and was the entire cause of GRC's avg markdown
  // depth reading 34% against a from-scratch, hand-checked Excel recompute
  // of 35.0000% (SUMPRODUCT over ENGINE_STORE, same population, same depth
  // table, same 25%-lever baseline).
  it("matches the hand-checked GRC figure (35%) at the baseline lever", () => {
    const grcCandidates = candidatesOf(fixture.items).filter((i) => i.vertical_id === "GRC");
    const pct = depthWeightedAvgPct(grcCandidates, BASELINE_LEVERS.markdown);
    expect(pct).toBeCloseTo(35, 0);
  });

  it("is wired to at_risk_gross, not at_risk_value", () => {
    const grcCandidates = candidatesOf(fixture.items).filter((i) => i.vertical_id === "GRC");
    const wrongWeight = depthWeightedAvgPct(
      grcCandidates.map((i) => ({ ...i, at_risk_gross: i.at_risk_value })),
      BASELINE_LEVERS.markdown,
    );
    const correct = depthWeightedAvgPct(grcCandidates, BASELINE_LEVERS.markdown);
    expect(correct).not.toBeCloseTo(wrongWeight, 0);
  });

  // Regression test: `lead_days` used to come from a source that didn't
  // reproduce the workbook's own ROP/Max, so "Drive whole page" silently
  // dropped ~3/4 of GRC's candidates (mostly Expiry) the moment ANY lever
  // moved — collapsing the lever's effect on avg_depth_pct from a clean
  // linear scale (20%->28%, 25%->35%, 30%->42%, hand-checked against Excel)
  // down to a barely-moving 34%->35.7%. This exercises the full driven path
  // (buildDashboardFromFixture with driveWholePage: true), not just the pure
  // depthWeightedAvgPct function, since the bug was upstream of it.
  it("scales linearly with the markdown lever for GRC, matching the hand-checked Excel figures", () => {
    const expected = { 20: 28, 25: 35, 30: 42 };
    for (const [markdown, pct] of Object.entries(expected)) {
      const levers = { ...BASELINE_LEVERS, markdown: Number(markdown) };
      const dashboard = buildDashboardFromFixture(
        fixture,
        { legal_entity_id: "GRC" },
        { levers, driveWholePage: true },
      );
      expect(dashboard.kpis.markdown_candidates).toBe(201);
      expect(dashboard.kpis.avg_depth_pct).toBeCloseTo(pct, 0);
    }
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

  it("comp_idx per vertical is averaged over every distinct SKU in that vertical, not just candidates", () => {
    const rows = computeByVertical(fixture.items, fixture.reference_by_vertical);
    for (const row of rows) {
      const skusInVertical = distinctBySku(fixture.items).filter((i) => i.vertical_id === row.vertical_id);
      const expected = mean(skusInVertical.map((i) => i.comp_idx));
      expect(row.comp_idx).toBeCloseTo(expected, 1);
    }
  });

  it("GRC's avg_depth_pct matches the hand-checked Excel figure (35%)", () => {
    const rows = computeByVertical(fixture.items, fixture.reference_by_vertical);
    const grc = rows.find((r) => r.vertical_id === "GRC");
    expect(grc).toBeDefined();
    expect(grc.avg_depth_pct).toBeCloseTo(35, 0);
  });
});

describe("computeCandidates", () => {
  it("carries category_id, vertical_id, comp_idx and at_risk_gross — the drilldown drawer's grouping keys and depth weight", () => {
    const rows = computeCandidates(fixture.items);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.category_id).toBeTruthy();
      expect(row.vertical_id).toBeTruthy();
      expect(row.comp_idx).toBeGreaterThan(0);
      expect(row.at_risk_gross).toBeGreaterThanOrEqual(0);
    }
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

  // Regression test: avg_depth_pct used to be entirely absent from
  // computeSimulation's baseline/scenario (and from SIMULATION_METRICS /
  // SIMULATION_STRIP_METRICS in contract.js) — the What-If simulator could
  // never show avg depth reacting to the markdown lever even though the
  // underlying formula was correct.
  it("carries avg_depth_pct on baseline and scenario, and moves it with the markdown lever", () => {
    const simulation = computeSimulation(
      fixture.items,
      { ...BASELINE_LEVERS, markdown: 40 },
      applyLevers,
    );
    expect(simulation.baseline.avg_depth_pct).toBeGreaterThan(0);
    expect(simulation.scenario.avg_depth_pct).toBeGreaterThan(simulation.baseline.avg_depth_pct);
  });
});
