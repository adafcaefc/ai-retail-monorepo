import { describe, expect, it } from "vitest";

import fixture from "./fixture.json";
import {
  DEFAULT_DEMAND_LEVERS,
  DEMAND_LEVER_DEFINITIONS,
  normalizeDemandLevers,
} from "./contract.js";
import {
  baselineLeadTimeDays,
  createDemandEngine,
} from "./engine.js";
import {
  buildDashboardFromFixture,
  buildDrilldownFromFixture,
} from "./selectors.js";

const metricIds = [
  "forecast_next_7d",
  "stockout_risk_skus",
  "forecast_accuracy_pct",
  "predicted_to_trend",
];

function levers(overrides = {}) {
  return { ...DEFAULT_DEMAND_LEVERS, ...overrides };
}

function dashboard(overrides = {}, options = {}) {
  return buildDashboardFromFixture(fixture, {}, {
    levers: levers(overrides),
    ...options,
  });
}

function scenario(overrides = {}) {
  return dashboard(overrides).simulation.scenario;
}

function expectFiniteMetrics(metrics) {
  for (const id of metricIds) {
    expect(Number.isFinite(metrics[id]), id).toBe(true);
  }
  expect(metrics.forecast_next_7d).toBeGreaterThanOrEqual(0);
  expect(metrics.stockout_risk_skus).toBeGreaterThanOrEqual(0);
  expect(metrics.predicted_to_trend).toBeGreaterThanOrEqual(0);
  expect(Number.isInteger(metrics.stockout_risk_skus)).toBe(true);
  expect(Number.isInteger(metrics.predicted_to_trend)).toBe(true);
  expect(metrics.forecast_accuracy_pct).toBeGreaterThanOrEqual(0);
  expect(metrics.forecast_accuracy_pct).toBeLessThanOrEqual(100);
}

describe("Demand Forecasting What-If calculations", () => {
  it("defines the neutral scenario as the displayed baseline", () => {
    const result = dashboard();

    expect(result.simulation.applied).toBe(false);
    expect(result.simulation.scenario).toEqual(result.simulation.baseline);
    expect(result.simulation.scenario_levers).toEqual(DEFAULT_DEMAND_LEVERS);
    expect(DEFAULT_DEMAND_LEVERS.promo).toBe(0);
    expect(DEFAULT_DEMAND_LEVERS.markdown).toBe(0);
  });

  it("replays every baseline row without changing the source values", () => {
    const applyLevers = createDemandEngine(fixture.formulas, fixture.constants.dow_sum);
    const before = JSON.parse(JSON.stringify(fixture.items));

    for (const item of fixture.items) {
      const replayed = applyLevers(item, DEFAULT_DEMAND_LEVERS);
      expect(replayed.ads).toBeCloseTo(item.ads, 9);
      expect(replayed.open_po).toBe(item.open_po);
      expect(replayed.position).toBe(item.position);
      expect(replayed.rop).toBe(item.rop);
      expect(replayed.forecast_7d).toBeCloseTo(item.forecast_7d, 9);
      expect(replayed.is_stockout_risk).toBe(item.is_stockout_risk);
    }

    expect(fixture.items).toEqual(before);
  });

  it("uses the displayed baseline ROP to recover the designated lead input", () => {
    const item = fixture.items[0];

    // Payload and baseline agree on the same source: the lead_days the
    // payload exposes is the one the baseline ROP was calculated from, which
    // is also the column ENGINE's stored ROP uses.
    expect(item.lead_days).toBe(2);
    // ROP is rounded, so recovering the source day count is approximate even
    // though it reproduces the displayed baseline exactly. The tolerance is
    // wider than it was against a lead of 6 because the same rounding error
    // is a larger share of a smaller number.
    expect(baselineLeadTimeDays(item)).toBeCloseTo(2, 2);
  });

  it("implements demand shift as a multiplicative ADS and forecast change", () => {
    const applyLevers = createDemandEngine(fixture.formulas, fixture.constants.dow_sum);
    const item = fixture.items.find((row) => row.promo_eligible === "N");
    const base = applyLevers(item, DEFAULT_DEMAND_LEVERS);
    const shifted = applyLevers(item, levers({ demand: 20 }));

    expect(shifted.ads).toBeCloseTo(base.ads * 1.2, 9);
    expect(shifted.forecast_7d).toBeCloseTo(base.forecast_7d * 1.2, 9);
  });

  it("implements promo intensity only for promo-eligible SKUs", () => {
    const applyLevers = createDemandEngine(fixture.formulas, fixture.constants.dow_sum);
    const promoItem = fixture.items.find((row) => row.promo_eligible === "Y");
    const nonPromoItem = fixture.items.find((row) => row.promo_eligible !== "Y");
    const promoBase = applyLevers(promoItem, DEFAULT_DEMAND_LEVERS);
    const promoScenario = applyLevers(promoItem, levers({ promo: 25 }));
    const nonPromoBase = applyLevers(nonPromoItem, DEFAULT_DEMAND_LEVERS);
    const nonPromoScenario = applyLevers(nonPromoItem, levers({ promo: 25 }));
    const expectedMultiplier = 1 + (25 / 100) * 1.3 * (1 - promoItem.promo_depth);

    expect(promoScenario.ads).toBeCloseTo(promoBase.ads * expectedMultiplier, 9);
    expect(nonPromoScenario.ads).toBeCloseTo(nonPromoBase.ads, 9);
  });

  it("keeps markdown depth inert because no Demand formula consumes it", () => {
    const base = scenario();
    const markdown = scenario({ markdown: 60 });

    expect(markdown.forecast_next_7d).toBeCloseTo(base.forecast_next_7d, 9);
    expect(markdown.stockout_risk_skus).toBe(base.stockout_risk_skus);
    expect(markdown.forecast_accuracy_pct).toBeCloseTo(base.forecast_accuracy_pct, 9);
    expect(markdown.predicted_to_trend).toBe(base.predicted_to_trend);
  });

  it("changes supply cover with inbound but not forecast demand", () => {
    const applyLevers = createDemandEngine(fixture.formulas, fixture.constants.dow_sum);
    const item = fixture.items[0];
    const base = applyLevers(item, DEFAULT_DEMAND_LEVERS);
    const supplied = applyLevers(item, levers({ inbound: 20 }));

    expect(supplied.open_po).toBeCloseTo(base.open_po * 1.2, 9);
    expect(supplied.position).toBeGreaterThanOrEqual(base.position);
    expect(supplied.forecast_7d).toBeCloseTo(base.forecast_7d, 9);
    expect(supplied.rop).toBe(base.rop);
  });

  it("changes only ROP exposure for lead-time and safety-stock levers", () => {
    const applyLevers = createDemandEngine(fixture.formulas, fixture.constants.dow_sum);
    const item = fixture.items[0];
    const base = applyLevers(item, DEFAULT_DEMAND_LEVERS);
    const lead = applyLevers(item, levers({ lead: 2 }));
    const safety = applyLevers(item, levers({ safety: 2 }));
    const leadDays = baselineLeadTimeDays(item);

    const expectedLeadRop = Math.round(
      base.ads * (Math.max(1, leadDays + 2) + Math.max(0, item.safety_days)),
    );
    const expectedSafetyRop = Math.round(
      base.ads * (Math.max(1, leadDays) + Math.max(0, item.safety_days + 2)),
    );

    expect(lead.rop).toBe(expectedLeadRop);
    expect(safety.rop).toBe(expectedSafetyRop);
    expect(lead.forecast_7d).toBeCloseTo(base.forecast_7d, 9);
    expect(safety.forecast_7d).toBeCloseTo(base.forecast_7d, 9);
    expect(lead.position).toBe(base.position);
    expect(safety.position).toBe(base.position);
  });

  it("keeps all valid boundary and representative lever values finite", () => {
    for (const definition of DEMAND_LEVER_DEFINITIONS) {
      for (const value of [definition.min, definition.max]) {
        const metrics = scenario({ [definition.id]: value });
        expectFiniteMetrics(metrics);
      }
    }

    const representative = [
      { demand: 1 },
      { demand: 40 },
      { demand: -1 },
      { promo: 1 },
      { promo: 50 },
      { markdown: 1 },
      { markdown: 60 },
      { inbound: -1 },
      { inbound: 60 },
      { lead: -1 },
      { lead: 6 },
      { safety: -1 },
      { safety: 5 },
    ];

    for (const overrides of representative) expectFiniteMetrics(scenario(overrides));
  });

  it("clamps invalid and out-of-range lever input at the contract boundary", () => {
    expect(normalizeDemandLevers({
      demand: -999,
      promo: 999,
      markdown: Number.NaN,
      inbound: Number.POSITIVE_INFINITY,
      lead: 999,
      safety: -999,
    })).toEqual({
      demand: -30,
      promo: 50,
      markdown: 0,
      inbound: 0,
      lead: 6,
      safety: -2,
    });
  });

  it("preserves the directional relationships implied by the formulas", () => {
    const demand = [-30, 0, 20, 40].map((value) => scenario({ demand: value }));
    const promo = [0, 1, 25, 50].map((value) => scenario({ promo: value }));
    const inbound = [-40, 0, 20, 60].map((value) => scenario({ inbound: value }));
    const lead = [-2, -1, 0, 6].map((value) => scenario({ lead: value }));
    const safety = [-2, -1, 0, 5].map((value) => scenario({ safety: value }));

    expect(demand.map((row) => row.forecast_next_7d)).toEqual(
      [...demand.map((row) => row.forecast_next_7d)].sort((a, b) => a - b),
    );
    expect(demand.map((row) => row.stockout_risk_skus)).toEqual(
      [...demand.map((row) => row.stockout_risk_skus)].sort((a, b) => a - b),
    );
    expect(promo.map((row) => row.forecast_next_7d)).toEqual(
      [...promo.map((row) => row.forecast_next_7d)].sort((a, b) => a - b),
    );
    expect(inbound.map((row) => row.stockout_risk_skus)).toEqual(
      [...inbound.map((row) => row.stockout_risk_skus)].sort((a, b) => b - a),
    );
    expect(lead.map((row) => row.stockout_risk_skus)).toEqual(
      [...lead.map((row) => row.stockout_risk_skus)].sort((a, b) => a - b),
    );
    expect(safety.map((row) => row.stockout_risk_skus)).toEqual(
      [...safety.map((row) => row.stockout_risk_skus)].sort((a, b) => a - b),
    );
  });

  it.each([
    ["demand acceleration", { demand: 20, promo: 50 }],
    ["supply support", { inbound: 60, safety: 5 }],
    ["supply stress", { demand: 20, lead: 6 }],
    ["all levers", { demand: 20, promo: 50, markdown: 60, inbound: 60, lead: 6, safety: 5 }],
  ])("composes the %s scenario deterministically", (_name, overrides) => {
    const first = dashboard(overrides);
    const second = dashboard(overrides);

    expect(second.simulation).toEqual(first.simulation);
    expect(second.forecast).toEqual(first.forecast);
    expectFiniteMetrics(first.simulation.scenario);
  });

  it("keeps the scenario preview isolated or propagates it according to the toggle", () => {
    const isolated = dashboard({ demand: 20 }, { driveWholePage: false });
    const applied = dashboard({ demand: 20 }, { driveWholePage: true });
    const baseline = dashboard({}, { driveWholePage: false });

    expect(isolated.kpis.find((kpi) => kpi.id === "forecast_next_7d").value)
      .toBeCloseTo(baseline.kpis.find((kpi) => kpi.id === "forecast_next_7d").value, 9);
    expect(isolated.simulation.scenario.forecast_next_7d)
      .toBeGreaterThan(isolated.simulation.baseline.forecast_next_7d);
    expect(applied.kpis.find((kpi) => kpi.id === "forecast_next_7d").value)
      .toBeCloseTo(applied.simulation.scenario.forecast_next_7d, 9);
    expect(applied.forecast.points[0].forecast)
      .toBeGreaterThan(isolated.forecast.points[0].forecast);
    expect(applied.dimensions.categories[0].forecast_units)
      .not.toBe(isolated.dimensions.categories[0].forecast_units);
    // Store/cluster rollups are built from the store snapshot and therefore
    // are explicitly outside the current whole-page scenario propagation.
    expect(applied.dimensions.stores).toEqual(isolated.dimensions.stores);
    expect(applied.dimensions.clusters).toEqual(isolated.dimensions.clusters);
  });

  it("keeps scenario KPI drilldowns aligned with the scenario rows", () => {
    const baseline = buildDrilldownFromFixture(fixture, {}, "forecast_next_7d", {
      levers: DEFAULT_DEMAND_LEVERS,
      driveWholePage: false,
    });
    const isolated = buildDrilldownFromFixture(fixture, {}, "forecast_next_7d", {
      levers: { ...DEFAULT_DEMAND_LEVERS, demand: 20 },
      driveWholePage: false,
    });
    const applied = buildDrilldownFromFixture(fixture, {}, "forecast_next_7d", {
      levers: { ...DEFAULT_DEMAND_LEVERS, demand: 20 },
      driveWholePage: true,
    });
    const categoryTotal = (drilldown) =>
      drilldown.by_category.reduce((total, row) => total + row.value, 0);

    expect(isolated.by_category).toEqual(baseline.by_category);
    expect(applied.total).toBeGreaterThan(baseline.total);
    expect(categoryTotal(applied)).toBeCloseTo(applied.total, 8);
    expect(applied.top_skus[0].value).toBeGreaterThan(baseline.top_skus[0].value);
  });

  it("does not mutate the baseline object while running combinations", () => {
    const before = JSON.parse(JSON.stringify(fixture));

    for (const overrides of [
      { demand: 20 },
      { promo: 50 },
      { inbound: 60, safety: 5 },
      { demand: 20, promo: 50, markdown: 60, inbound: 60, lead: 6, safety: 5 },
    ]) {
      dashboard(overrides);
    }

    expect(fixture).toEqual(before);
  });
});
