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
  computeQuadrant,
  delistOf,
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
