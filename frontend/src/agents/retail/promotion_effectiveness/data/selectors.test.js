/**
 * Reconciliation, not coverage. `fixture.json` is generated from the workbook
 * and carries the A4 Promotion sheet's per-vertical totals in
 * `reference_by_vertical`. If a selector ever starts deriving a stored KPI
 * instead of reading it, these comparisons break.
 */

import { describe, expect, it } from "vitest";

import { AGENT_ID, ALL, BASELINE_LEVERS, DEFAULT_SCOPE } from "./contract.js";
import { loadPromotionDashboard, loadPromotionDrilldown } from "./dashboardData.js";
import fixture from "./fixture.json";
import {
  buildDashboardFromFixture,
  computeByChannel,
  computeByCluster,
  computeBySeason,
  computeByState,
  computeByStore,
  computeKpis,
  computeLargestMarginSkus,
  scopeCampaigns,
  scopeItems,
  scopeStores,
  sum,
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

  it("carries the two KPI rules the tiles are reduced from", () => {
    expect(fixture.formulas["fc11-promo-sku-flag"]).toBeTruthy();
    expect(fixture.formulas["fc12-promo-net-uplift-pct"]).toBeTruthy();
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

  it("reads ROI from the reference, not from per-SKU rows", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const expectedRoi =
      fixture.reference_by_vertical.reduce((t, r) => t + r.roi_x, 0) /
      fixture.reference_by_vertical.length;
    expect(dashboard.kpis.roi_x).toBeCloseTo(expectedRoi, 1);
  });

  it("computes uplift from fc12 and still lands on the workbook's figure", () => {
    // The chain tile is the mean over all 241 promo SKUs; the reference is a
    // mean of eight per-vertical means over unequal SKU counts. Those differ
    // by ~0.001pp, which is why this compares at 1 decimal — the per-vertical
    // check below is the exact one.
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const referenceUplift =
      fixture.reference_by_vertical.reduce((t, r) => t + r.uplift_pct, 0) /
      fixture.reference_by_vertical.length;
    expect(dashboard.kpis.uplift_pct).toBeCloseTo(referenceUplift, 1);
  });

  it("narrows uplift to the scoped category, which a stored KPI cannot do", () => {
    // The point of moving uplift onto a per-row rule: a vertical-grain stored
    // KPI has no category dimension, so this tile used to sit still while the
    // other five narrowed.
    const category = fixture.items[0].category_id;
    const scoped = buildDashboardFromFixture(fixture, scopeOf({ category_group: category }));
    const scopedItems = fixture.items.filter((i) => i.category_id === category);
    const expected =
      scopedItems.reduce((t, i) => t + 0.15 * 2.2 * (1 - i.cannibalisation_pct / 100) * 100, 0) /
      scopedItems.length;
    expect(scoped.kpis.uplift_pct).toBeCloseTo(expected, 2);
  });

  it("counts active promo SKUs by summing fc11, not by row count", () => {
    // Same number today (every shipped row is promo-eligible), but sourced
    // from the catalogue predicate rather than implied by the query.
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const byFlag = fixture.items.filter((i) => i.promo_eligible === "Y").length;
    expect(dashboard.kpis.active_promo_skus).toBe(byFlag);
  });

  it("narrows uplift and ROI to the selected vertical, not the chain average", () => {
    // Regression test: uplift_pct/roi_x used to always average across every
    // vertical in reference_by_vertical regardless of scope, so the Vertical
    // filter silently left these two tiles unchanged while the other four
    // (active_promo_skus, incremental_margin, cannib_pct, funding_pct) did
    // narrow correctly.
    const dashboard = buildDashboardFromFixture(fixture, scopeOf({ legal_entity_id: "GRC" }));
    const groceryReference = fixture.reference_by_vertical.find(
      (r) => r.legal_entity_id === "GRC",
    );
    // Compared at 2 decimals because that is what the selectors round these
    // KPIs to (`round(value, 2)`, as for cannib and funding). This assertion
    // used to demand 6 and failed on the rounding alone. It still discriminates
    // at 2: the chain uplift is 25.60 against Grocery's 25.74.
    expect(dashboard.kpis.uplift_pct).toBeCloseTo(groceryReference.uplift_pct, 2);
    expect(dashboard.kpis.roi_x).toBeCloseTo(groceryReference.roi_x, 2);

    const chainDashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    expect(dashboard.kpis.uplift_pct).not.toBeCloseTo(chainDashboard.kpis.uplift_pct, 3);
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

describe("store, cluster and channel decomposition", () => {
  it("reconciles exactly to the chain-net incremental margin (no netting, unlike inventory position)", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const byStoreTotal = dashboard.by_store.reduce((t, r) => t + r.incremental_margin, 0);
    const byClusterTotal = dashboard.by_cluster.reduce((t, r) => t + r.incremental_margin, 0);
    const byChannelTotal = dashboard.by_channel.reduce((t, r) => t + r.incremental_margin, 0);
    const headline = dashboard.kpis.incremental_margin;

    // Rounding happens per-row (round to whole Rupiah) before summing, so the
    // reconstructed totals agree with the headline to a handful of rupiah on
    // a value in the tens of billions, not to the last digit.
    expect(byStoreTotal).toBeCloseTo(headline, -2);
    expect(byClusterTotal).toBeCloseTo(headline, -2);
    expect(byChannelTotal).toBeCloseTo(headline, -2);
  });

  it("narrows the store dimension list the way scopeItems narrows items", () => {
    const oneStore = scopeStores(fixture.stores, { store_id: fixture.stores[0].store_id });
    expect(oneStore).toEqual([fixture.stores[0]]);

    const vertical = fixture.stores[0].vertical_id;
    const byVertical = scopeStores(fixture.stores, { legal_entity_id: vertical });
    expect(byVertical.every((s) => s.vertical_id === vertical)).toBe(true);
    expect(byVertical.length).toBeGreaterThan(0);

    expect(scopeStores(fixture.stores, {})).toHaveLength(fixture.stores.length);
  });

  it("computeByCluster and computeByChannel group computeByStore's own rows", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const byCluster = computeByCluster(dashboard.by_store);
    const byChannel = computeByChannel(dashboard.by_store);
    expect(byCluster).toEqual(dashboard.by_cluster);
    expect(byChannel).toEqual(dashboard.by_channel);
  });

  it("computeByState sums inventory value, not incremental margin", () => {
    const dashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const expectedTotal = fixture.items.reduce(
      (t, i) => t + (Number(i.inventory_value) || 0),
      0,
    );
    const byStateTotal = dashboard.by_state.reduce((t, r) => t + r.value, 0);
    expect(byStateTotal).toBeCloseTo(expectedTotal, -2);
    // Intentionally does not reconcile against incremental_margin — a
    // different measure, per spec section 11.
    expect(byStateTotal).not.toBeCloseTo(dashboard.kpis.incremental_margin, -2);
  });

  it("computeByStore is directly callable, not only through the dashboard builder", () => {
    const store = fixture.stores.find((s) => s.vertical_id === fixture.items[0].vertical_id);
    const rows = computeByStore(fixture.items, [store]);
    expect(rows.every((r) => r.store_id === store.store_id)).toBe(true);
  });
});

describe("the Store filter", () => {
  it("replaces the item population with that store's own reconstructed position", () => {
    const store = fixture.stores[0];
    const chainDashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const storeDashboard = buildDashboardFromFixture(fixture, scopeOf({ store_id: store.store_id }));

    expect(storeDashboard.scope.store_id).toBe(store.store_id);
    expect(storeDashboard.kpis.active_promo_skus).toBeGreaterThan(0);
    expect(storeDashboard.kpis.incremental_margin).toBeLessThan(
      chainDashboard.kpis.incremental_margin,
    );
  });

  it("does not change campaigns or the season mix — promotion_detail carries no store dimension", () => {
    const store = fixture.stores[0];
    const chainDashboard = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const storeDashboard = buildDashboardFromFixture(fixture, scopeOf({ store_id: store.store_id }));

    expect(storeDashboard.campaigns).toEqual(chainDashboard.campaigns);
    expect(storeDashboard.by_season).toEqual(chainDashboard.by_season);
  });

  // Regression test: selecting a store used to throw "Operator '*' needs a
  // number, got undefined" — every item was missing `arch_horizon_factor`,
  // a real f01 term the Store filter's `atStore`/`applyLevers` re-evaluation
  // always runs, even at baseline levers. See engine.test.js's
  // "arch_horizon_factor" suite for the engine-level coverage.
  it("does not throw for any store, and returns populated KPIs", () => {
    for (const store of fixture.stores) {
      let dashboard;
      expect(() => {
        dashboard = buildDashboardFromFixture(fixture, scopeOf({ store_id: store.store_id }));
      }).not.toThrow();
      expect(dashboard.scope.store_id).toBe(store.store_id);
      expect(Number.isFinite(dashboard.kpis.incremental_margin)).toBe(true);
    }
  });

  it("does not throw when a store is selected and a What-If lever is moved", () => {
    const store = fixture.stores[0];
    expect(() =>
      buildDashboardFromFixture(fixture, scopeOf({ store_id: store.store_id }), {
        levers: { ...BASELINE_LEVERS, promo: 20 },
        driveWholePage: true,
      }),
    ).not.toThrow();
  });
});

describe("the season mix", () => {
  // Regression test: `total` called the keyed `sum` helper on a bare array of
  // numbers, so it read `row[undefined]` and came back 0 for every season.
  it("totals each season's segments, and the seasons total the campaign units", () => {
    const rows = computeBySeason(fixture.campaigns);
    expect(rows.length).toBeGreaterThan(0);

    for (const row of rows) {
      const segments = row.segments.reduce((total, s) => total + s.value, 0);
      expect(row.total).toBeGreaterThan(0);
      expect(row.total).toBeCloseTo(segments, 2);
    }

    const allSeasons = rows.reduce((total, row) => total + row.total, 0);
    expect(allSeasons).toBeCloseTo(sum(fixture.campaigns, "pre_buy_uplift_units"), 2);
  });

  it("carries one segment per discount type on every season, zero-filled", () => {
    const rows = computeBySeason(fixture.campaigns);
    const types = [...new Set(fixture.campaigns.map((c) => c.discount_type))];

    for (const row of rows) {
      expect(row.segments.map((s) => s.discount_type)).toEqual(types);
      for (const segment of row.segments) {
        expect(Number.isFinite(segment.value)).toBe(true);
      }
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

  it("carries category_id on the margin-leaders population the drilldown draws from", () => {
    // Regression test: computeLargestMarginSkus used to omit category_id
    // (only category_label survived), so loadPromotionDrilldown's "by
    // category" section silently showed "Nothing in scope" for every metric,
    // while "by vertical" worked fine because vertical_id was carried.
    const rows = computeLargestMarginSkus(fixture.items);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.category_id).toBeTruthy();
    }
  });

  it("decomposes a drilldown by category, not just by vertical", async () => {
    const drilldown = await loadPromotionDrilldown(DEFAULT_SCOPE, "incremental_margin");
    expect(drilldown.by_category.length).toBeGreaterThan(0);
    expect(drilldown.by_vertical.length).toBeGreaterThan(0);
  });
});
