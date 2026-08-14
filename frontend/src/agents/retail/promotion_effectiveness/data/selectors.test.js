/**
 * Reconciliation, not coverage. `fixture.json` is generated from the workbook
 * and carries the A4 Promotion sheet's per-vertical totals in
 * `reference_by_vertical`. If a selector ever starts deriving a stored KPI
 * instead of reading it, these comparisons break.
 */

import { describe, expect, it } from "vitest";

import { AGENT_ID, ALL, DEFAULT_SCOPE } from "./contract.js";
import { loadPromotionDashboard } from "./dashboardData.js";
import fixture from "./fixture.json";
import {
  buildDashboardFromFixture,
  computeKpis,
  scopeCampaigns,
  scopeItems,
} from "./selectors.js";

const scopeOf = (overrides) => ({ ...DEFAULT_SCOPE, ...overrides });

describe("fixture integrity", () => {
  it("carries the promo SKUs, campaigns and every vertical's reference totals", () => {
    expect(fixture.items.length).toBeGreaterThan(0);
    expect(fixture.campaigns).toHaveLength(48);
    expect(fixture.reference_by_vertical).toHaveLength(8);
    expect(fixture.is_mock).toBe(true);
    expect(fixture.agent).toBe(AGENT_ID);
  });

  it("carries the two formula expressions the What-If engine needs", () => {
    expect(fixture.formulas["f01-ads-per-store"]).toBeTruthy();
    expect(fixture.formulas["f13-incremental-promotion-margin"]).toBeTruthy();
  });

  it("marks every shipped item promo-eligible", () => {
    for (const item of fixture.items) {
      expect(item.promo_eligible).toBe("Y");
    }
  });
});

describe("KPIs reconcile with the workbook", () => {
  it("active promo SKUs matches the chain total", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    expect(dashboard.kpis.active_promo_skus).toBe(fixture.items.length);
  });

  it("campaign count and pre-buy units come from the campaign rows", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    expect(dashboard.kpis.campaigns).toBe(48);
    const totalPreBuy = fixture.campaigns.reduce(
      (t, c) => t + (Number(c.pre_buy_uplift_units) || 0),
      0,
    );
    expect(dashboard.kpis.pre_buy_uplift_units).toBe(totalPreBuy);
  });

  it("reads uplift and ROI from the reference, not from per-SKU rows", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const expectedUplift =
      fixture.reference_by_vertical.reduce((t, r) => t + r.uplift_pct, 0) /
      fixture.reference_by_vertical.length;
    const expectedRoi =
      fixture.reference_by_vertical.reduce((t, r) => t + r.roi_x, 0) /
      fixture.reference_by_vertical.length;
    expect(dashboard.kpis.uplift_pct).toBeCloseTo(expectedUplift, 1);
    expect(dashboard.kpis.roi_x).toBeCloseTo(expectedRoi, 1);
  });
});

describe("scoping", () => {
  it("narrows to one vertical's promo SKUs", () => {
    const items = scopeItems(fixture.items, { legal_entity_id: "GRC" });
    expect(items.every((i) => i.vertical_id === "GRC")).toBe(true);
    expect(items.length).toBeGreaterThan(0);
  });

  it("narrows campaigns by vertical", () => {
    const campaigns = scopeCampaigns(fixture.campaigns, { legal_entity_id: "GRC" });
    expect(campaigns.every((c) => c.vertical_id === "GRC")).toBe(true);
    expect(campaigns.length).toBeGreaterThan(0);
  });

  it("ALL restores the whole chain", () => {
    const dashboard = buildDashboardFromFixture(fixture, scopeOf({ legal_entity_id: ALL }));
    expect(dashboard.kpis.active_promo_skus).toBe(fixture.items.length);
  });
});

describe("best-action tabs", () => {
  it("partitions every campaign into exactly one tab", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const { high_roi, funding_gap, pre_buy_required } = dashboard.best_actions;
    const total = high_roi.length + funding_gap.length + pre_buy_required.length;
    expect(total).toBe(fixture.campaigns.length);
  });
});

describe("the simulation block", () => {
  it("is inert at baseline (all indices 100)", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE, {
      levers: { demand: 0, promo: 0, markdown: 0, inbound: 0, lead: 0, safety: 0 },
    });
    expect(dashboard.simulation.applied).toBe(false);
    for (const entry of dashboard.simulation.index) {
      expect(entry.baseline_index).toBe(100);
      expect(entry.scenario_index).toBe(100);
    }
  });
});

describe("the data gateway", () => {
  it("loads and normalizes for one vertical", async () => {
    const dashboard = await loadPromotionDashboard({ legal_entity_id: "GRC" });
    expect(dashboard.agent).toBe(AGENT_ID);
    expect(dashboard.is_mock).toBe(true);
    expect(dashboard.kpis.active_promo_skus).toBeGreaterThan(0);
  });
});
