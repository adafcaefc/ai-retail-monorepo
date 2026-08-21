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
  computeLadderHistory,
  computeSimulation,
  depthWeightedAvgPct,
  distinctBySku,
  mean,
  scopeItems,
} from "./selectors.js";
import { ALL, BASELINE_LEVERS, BEST_ACTION_TABS, CANDIDATE_STATES, DEPTH_BY_STATE } from "./contract.js";
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

  it("defaults to the top 300 by at_risk_value, for the preview table", () => {
    const rows = computeCandidates(fixture.items);
    expect(rows.length).toBeLessThanOrEqual(300);
  });

  it("an explicit Infinity limit returns every candidate, unsorted-cap-free", () => {
    const rows = computeCandidates(fixture.items, Infinity);
    expect(rows.length).toBe(candidatesOf(fixture.items).length);
  });

  // Regression test: elasticity and depth_pct used to be dropped entirely,
  // so the Elasticity vs depth chart had nothing to plot per candidate.
  it("carries elasticity and depth_pct — the Elasticity vs depth chart's own axes", () => {
    const rows = computeCandidates(fixture.items, 300, BASELINE_LEVERS.markdown);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(typeof row.elasticity).toBe("number");
      expect(row.depth_pct).toBeGreaterThan(0);
      expect(row.depth_pct).toBeLessThanOrEqual(65);
    }
    const bySku = new Map(fixture.items.map((i) => [`${i.sku_id}:${i.store_id}`, i]));
    for (const row of rows.slice(0, 20)) {
      const raw = bySku.get(`${row.sku_id}:${row.store_id}`);
      const base = DEPTH_BY_STATE[raw.state];
      const expected = Math.round(Math.min(0.65, base * (BASELINE_LEVERS.markdown / 25)) * 1000) / 10;
      expect(row.depth_pct).toBeCloseTo(expected, 1);
    }
  });

  it("depth_pct scales with the markdown lever, same as avg_depth_pct", () => {
    const at40 = computeCandidates(fixture.items, 300, 40);
    const atBaseline = computeCandidates(fixture.items, 300, BASELINE_LEVERS.markdown);
    const bySkuAt40 = new Map(at40.map((r) => [`${r.sku_id}:${r.store_id}`, r.depth_pct]));
    let widened = 0;
    for (const row of atBaseline) {
      if (bySkuAt40.get(`${row.sku_id}:${row.store_id}`) > row.depth_pct) widened++;
    }
    expect(widened).toBeGreaterThan(0);
  });
});

describe("computeLadderHistory", () => {
  // no_action[0]/ladder[0] is "+1 week" (w1), NOT today -- today (week 0)
  // is never in this data at all, it is injected from `kpis` (the third
  // argument). history_no_action[0]/history_ladder[0] is "1 week ago"
  // (hist_w1) .. [2] is "3 weeks ago" (hist_w3) -- see the generator's own
  // column ordering. computeLadderHistory reverses history to oldest-first.
  const ladderByVertical = [
    {
      legal_entity_id: "GRC",
      no_action: [110, 120, 130],
      ladder: [84, 88, 92],
      history_no_action: [95, 90, 85],
      history_ladder: [76, 72, 68],
    },
    {
      legal_entity_id: "DGT",
      no_action: [55, 60, 65],
      ladder: [42, 44, 46],
      history_no_action: [48, 46, 44],
      history_ladder: [38, 37, 35],
    },
  ];

  it("sums every vertical when unscoped, oldest week first, today from kpis", () => {
    const kpis = { at_risk_value: 150, write_off_value: 120 };
    const rows = computeLadderHistory(ladderByVertical, { legal_entity_id: ALL }, kpis);
    expect(rows).toEqual([
      { week: -3, no_action: 129, ladder: 103 },
      { week: -2, no_action: 136, ladder: 109 },
      { week: -1, no_action: 143, ladder: 114 },
      { week: 0, no_action: 150, ladder: 120 },
      { week: 1, no_action: 165, ladder: 126 },
      { week: 2, no_action: 180, ladder: 132 },
      { week: 3, no_action: 195, ladder: 138 },
    ]);
  });

  it("narrows the -16..-1/1..16 weeks to one vertical when scoped; today still comes from kpis, not the vertical", () => {
    const kpis = { at_risk_value: 100, write_off_value: 80 };
    const rows = computeLadderHistory(ladderByVertical, { legal_entity_id: "GRC" }, kpis);
    expect(rows).toEqual([
      { week: -3, no_action: 85, ladder: 68 },
      { week: -2, no_action: 90, ladder: 72 },
      { week: -1, no_action: 95, ladder: 76 },
      { week: 0, no_action: 100, ladder: 80 },
      { week: 1, no_action: 110, ladder: 84 },
      { week: 2, no_action: 120, ladder: 88 },
      { week: 3, no_action: 130, ladder: 92 },
    ]);
  });

  it("today defaults to zero when kpis is omitted", () => {
    const rows = computeLadderHistory(ladderByVertical, { legal_entity_id: ALL });
    expect(rows.find((r) => r.week === 0)).toEqual({ week: 0, no_action: 0, ladder: 0 });
  });

  it("returns an empty array when there is nothing to project", () => {
    expect(computeLadderHistory([], {})).toEqual([]);
    expect(computeLadderHistory(undefined, {})).toEqual([]);
  });

  // Regression proof against the actual fixture: the underlying trend rises
  // from the oldest history week to the furthest forecast week (the wiggle
  // this generator now applies lets it dip locally week to week, so this
  // checks the edges, not every single step), and today (week 0) is the
  // real, unrounded anchor both computeKpis and the Rescue waterfall read
  // (injected here from the fixture's own candidate population, the same
  // way buildDashboardFromFixture wires kpis through). See the gates
  // scripts/generate_synthetic_markdown_ladder_16w.py enforces before the
  // CSV is ever written.
  it("the real fixture's projection rises from oldest to newest and stays separated at the edges", () => {
    const candidates = candidatesOf(fixture.items);
    const kpis = {
      at_risk_value: candidates.reduce((sum, i) => sum + i.at_risk_value, 0),
      write_off_value: candidates.reduce((sum, i) => sum + Math.max(0, i.at_risk_value - i.recoverable_value), 0),
    };
    const rows = computeLadderHistory(fixture.ladder_by_vertical ?? [], { legal_entity_id: ALL }, kpis);
    if (!rows.length) return; // fixture built before the generator ran; nothing to assert
    const first = rows[0];
    const today = rows.find((r) => r.week === 0);
    const last = rows[rows.length - 1];
    expect(rows).toHaveLength(33);
    expect(last.week).toBe(16);
    expect(first.no_action).toBeLessThan(today.no_action);
    expect(today.no_action).toBeLessThan(last.no_action);
    expect(first.ladder).toBeLessThan(first.no_action);
    expect(last.ladder).toBeLessThan(last.no_action);
  });
});

// Regression test for the drilldown drawer reading a value-sorted, 300-row
// slice: it silently dropped most categories/stores and skewed every
// weighted figure (avg_depth_pct especially, since the top-300-by-value
// slice skews toward Slow-mover rows). See dashboardData.js's
// loadPricingMarkdownDrilldown, which reads candidates_full for exactly
// this reason.
describe("buildDashboardFromFixture — candidates_full", () => {
  it("is the full candidate population, not the preview table's 300-row cap", () => {
    const dashboard = buildDashboardFromFixture(fixture);
    const allCandidates = candidatesOf(fixture.items);
    expect(dashboard.candidates.length).toBeLessThanOrEqual(300);
    expect(dashboard.candidates_full.length).toBe(allCandidates.length);
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
