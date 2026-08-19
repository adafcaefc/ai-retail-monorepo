import { describe, expect, it } from "vitest";

import fixture from "./fixture.json";
import {
  assignBestActionTabs,
  buildDashboardFromFixture,
  computeActionPreview,
  computeByCluster,
  computeByVertical,
  computeBestActions,
  computeKpis,
  computeParetoContribution,
  computeQuadrant,
  delistOf,
  delistShare,
  growOf,
  scopeItems,
} from "./selectors.js";
import { ALL, BEST_ACTION_TABS, DELIST_STATES } from "./contract.js";

describe("classification", () => {
  it("splits the range into delist, grow and hold with nothing left over", () => {
    const delist = delistOf(fixture.items).length;
    const grow = growOf(fixture.items).length;
    const hold = fixture.items.filter((i) => i.classification === "hold").length;
    expect(delist + grow + hold).toBe(fixture.items.length);
    expect(delist).toBeGreaterThan(0);
    expect(grow).toBeGreaterThan(0);
  });

  it("never marks a delist-state SKU as grow", () => {
    for (const item of growOf(fixture.items)) {
      expect(DELIST_STATES).not.toContain(item.state);
    }
  });
});

describe("assignBestActionTabs", () => {
  /*
   * The JS assignment and the Python fixture builder's must agree, or a board
   * shows one grouping while the shipped data claims another. This is the
   * assertion that keeps the two definitions honest — see the module
   * docstring in selectors.js for why the rule lives in both places.
   */
  it("reproduces the fixture's own stored tabs at baseline", () => {
    const assigned = assignBestActionTabs(fixture.items);
    for (const [index, item] of assigned.entries()) {
      expect(item.best_action_tab).toBe(fixture.items[index].best_action_tab);
    }
  });

  it("puts every classified SKU in exactly one tab", () => {
    const assigned = assignBestActionTabs(fixture.items);
    const tabbed = assigned.filter((i) => i.best_action_tab !== null).length;
    expect(tabbed).toBe(delistOf(fixture.items).length + growOf(fixture.items).length);
  });
});

describe("computeKpis", () => {
  it("capital freed sums inventory value over delist candidates only", () => {
    const kpis = computeKpis(fixture.items);
    const expected = Math.round(delistOf(fixture.items).reduce((t, i) => t + i.inv_value, 0));
    expect(kpis.capital_freed).toBe(expected);
    expect(kpis.delist_candidates).toBe(delistOf(fixture.items).length);
  });

  it("tail share is a percentage between 0 and 100", () => {
    const kpis = computeKpis(fixture.items);
    expect(kpis.tail_share_pct).toBeGreaterThan(0);
    expect(kpis.tail_share_pct).toBeLessThanOrEqual(100);
  });

  it("the three verdict counts add up to the SKU count", () => {
    const kpis = computeKpis(fixture.items);
    expect(kpis.delist_candidates + kpis.grow_candidates + kpis.hold_count).toBe(kpis.sku_count);
  });
});

describe("scopeItems", () => {
  it("narrows by vertical", () => {
    const vertical = fixture.items[0].vertical_id;
    const scoped = scopeItems(fixture.items, { legal_entity_id: vertical });
    expect(scoped.length).toBeGreaterThan(0);
    expect(scoped.every((i) => i.vertical_id === vertical)).toBe(true);
  });

  it("narrows by classification", () => {
    const scoped = scopeItems(fixture.items, { classification: "grow" });
    expect(scoped.length).toBe(growOf(fixture.items).length);
  });

  it("ALL is a no-op", () => {
    expect(scopeItems(fixture.items, { legal_entity_id: ALL }).length).toBe(fixture.items.length);
  });
});

describe("computeByVertical", () => {
  it("delist counts across verticals sum to the chain total", () => {
    const rows = computeByVertical(fixture.items, fixture.reference_by_vertical);
    const total = rows.reduce((t, r) => t + r.delist_candidates, 0);
    expect(total).toBe(delistOf(fixture.items).length);
  });
});

describe("computeByCluster", () => {
  it("every store is counted in exactly one cluster", () => {
    const rows = computeByCluster(fixture.stores);
    expect(rows.reduce((t, r) => t + r.store_count, 0)).toBe(fixture.stores.length);
  });
});

describe("computeParetoContribution", () => {
  const pareto = computeParetoContribution(fixture.items);

  it("orders every SKU by contribution/day, descending", () => {
    const values = pareto.bars.map((b) => b.contribution_per_day);
    expect(values).toEqual([...values].sort((a, b) => b - a));
    expect(pareto.bars[0].rank).toBe(1);
  });

  it("counts the curve over the whole scope, not just the drawn bars", () => {
    // The head is a rendering limit; every SKU with contribution is ranked.
    expect(pareto.bars.length).toBeLessThan(pareto.sku_count);
    expect(pareto.sku_count).toBe(
      fixture.items.filter((i) => i.contribution_per_day > 0).length,
    );
  });

  it("totals to the contribution/day KPI, which is the workbook's own figure", () => {
    // A6's one measure a prior audit did not flag as pasted. If the Pareto
    // disagrees with it, the chart is ranking something else.
    expect(pareto.total_contribution).toBe(computeKpis(fixture.items).contribution_per_day);
  });

  it("reads the Pareto rank off the data rather than storing it", () => {
    const { pareto_rank: rank, pareto_share_pct: share } = pareto;
    expect(rank).toBeGreaterThan(0);
    expect(rank).toBeLessThanOrEqual(pareto.sku_count);

    // The rank is the FIRST SKU at or past the share: the one before it is
    // still short. That is what makes it a count rather than a threshold.
    const curve = computeParetoContribution(fixture.items, fixture.items.length).bars;
    expect(curve[rank - 1].cumulative_share).toBeGreaterThanOrEqual(share);
    expect(curve[rank - 2].cumulative_share).toBeLessThan(share);
  });

  it("closes the curve at 100%", () => {
    const curve = computeParetoContribution(fixture.items, fixture.items.length).bars;
    expect(curve[curve.length - 1].cumulative_share).toBeCloseTo(100, 1);
  });

  it("narrows with the scope", () => {
    const scoped = computeParetoContribution(scopeItems(fixture.items, { legal_entity_id: "GRC" }));
    expect(scoped.sku_count).toBeLessThan(pareto.sku_count);
    expect(scoped.total_contribution).toBeLessThan(pareto.total_contribution);
  });
});

describe("computeQuadrant", () => {
  it("caps its point count and carries a verdict on every point", () => {
    const points = computeQuadrant(fixture.items, 50);
    expect(points.length).toBeLessThanOrEqual(50);
    for (const p of points) {
      expect(["delist", "grow", "hold"]).toContain(p.classification);
    }
  });
});

describe("computeActionPreview", () => {
  it("excludes hold SKUs — they are not an action", () => {
    const rows = computeActionPreview(fixture.items);
    for (const row of rows) {
      expect(row.classification).not.toBe("hold");
    }
  });
});

describe("computeBestActions", () => {
  it("groups the tabbed population into the four tabs", () => {
    const tabbed = assignBestActionTabs(fixture.items);
    const groups = computeBestActions(tabbed);
    const total = BEST_ACTION_TABS.reduce((t, tab) => t + groups[tab.id].length, 0);
    expect(total).toBe(delistOf(fixture.items).length + growOf(fixture.items).length);
  });
});

describe("buildDashboardFromFixture", () => {
  it("produces a payload with every block the contract declares", () => {
    const built = buildDashboardFromFixture(fixture);
    expect(built.kpis.sku_count).toBe(fixture.items.length);
    expect(built.by_vertical.length).toBeGreaterThan(0);
    expect(built.quadrant.length).toBeGreaterThan(0);
    expect(built.action_preview.length).toBeGreaterThan(0);
    expect(built.simulation.applied).toBe(false);
  });

  it("contribution/day reconciles against the workbook's own A6 column G total", () => {
    const built = buildDashboardFromFixture(fixture);
    const sheetTotal = fixture.reference_by_vertical.reduce((t, r) => t + r.contribution_per_day, 0);
    const drift = Math.abs(built.kpis.contribution_per_day - sheetTotal) / sheetTotal;
    expect(drift).toBeLessThan(0.005);
  });
});

describe("best-action tabs are earned by concentration, not by a stored count", () => {
  const tabs = assignBestActionTabs(fixture.items);
  const count = (id) => tabs.filter((t) => t.best_action_tab === id).length;

  it("fills all four tabs rather than collapsing into one", () => {
    // The rule this replaced used an absolute count, which every vendor in
    // this range cleared, so Vendor Review swallowed all 404 delist rows and
    // two tabs rendered empty. A share cannot do that.
    for (const tab of BEST_ACTION_TABS) {
      expect(count(tab.id), `${tab.id} is empty`).toBeGreaterThan(0);
    }
  });

  it("splits the delist population exactly once, with nothing left over", () => {
    const delist = tabs.filter((t) => t.classification === "delist").length;
    expect(count("delist_tail") + count("rebalance_space") + count("vendor_brand_review"))
      .toBe(delist);
    expect(count("grow_winners")).toBe(growOf(fixture.items).length);
  });

  it("routes a group only when it carries MORE than its share of the delist list", () => {
    const chainRate = delistOf(fixture.items).length / fixture.items.length;
    const vendorRate = delistShare(fixture.items, "vendor");
    for (const row of tabs) {
      if (row.best_action_tab !== "vendor_brand_review") continue;
      expect(vendorRate.get(row.vendor), row.vendor).toBeGreaterThan(chainRate);
    }
  });

  it("re-derives the cutoff for a narrower scope instead of reusing the chain's", () => {
    const scoped = scopeItems(fixture.items, { legal_entity_id: "GRC" });
    const scopedTabs = assignBestActionTabs(scoped);
    const rate = delistOf(scoped).length / scoped.length;
    const vendorRate = delistShare(scoped, "vendor");
    for (const row of scopedTabs) {
      if (row.best_action_tab !== "vendor_brand_review") continue;
      expect(vendorRate.get(row.vendor)).toBeGreaterThan(rate);
    }
  });
});
