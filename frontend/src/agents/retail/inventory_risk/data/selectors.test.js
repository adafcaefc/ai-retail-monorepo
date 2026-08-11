/**
 * The point of these tests is reconciliation, not coverage.
 *
 * `fixture.json` is generated from the workbook and carries the workbook's own
 * per-vertical totals in `reference_by_vertical`. If a selector ever starts
 * deriving a number instead of reading one, these comparisons break — which is
 * the entire safety net behind putting no thresholds in JavaScript.
 */

import { describe, expect, it } from "vitest";

import { ALL, DEFAULT_SCOPE, STATE_ORDER } from "./contract.js";
import { loadInventoryRiskDashboard } from "./dashboardData.js";
import fixture from "./fixture.json";
import {
  buildDashboardFromFixture,
  computeKpis,
  scopeItems,
} from "./selectors.js";

const scopeOf = (overrides) => ({ ...DEFAULT_SCOPE, ...overrides });

describe("fixture integrity", () => {
  it("carries the whole chain and every vertical's reference totals", () => {
    expect(fixture.items).toHaveLength(800);
    expect(fixture.stores).toHaveLength(160);
    expect(fixture.reference_by_vertical).toHaveLength(8);
    expect(fixture.is_mock).toBe(true);
  });

  it("resolves every rule upstream, so no item needs re-classifying", () => {
    for (const item of fixture.items) {
      expect(STATE_ORDER).toContain(item.state);
      expect(typeof item.is_stockout_risk).toBe("boolean");
      expect(typeof item.is_overstock).toBe("boolean");
      expect(typeof item.is_slow_mover).toBe("boolean");
      expect(item.severity_rank).toBe(STATE_ORDER.indexOf(item.state));
    }
  });
});

describe("KPIs reconcile with the workbook", () => {
  it.each(fixture.reference_by_vertical)(
    "matches the A2 sheet for $vertical_label",
    (reference) => {
      const items = scopeItems(
        fixture.items,
        scopeOf({ legal_entity_id: reference.legal_entity_id }),
      );
      const kpis = computeKpis(items);

      expect(kpis.stockout_risk_skus).toBe(reference.stockout_risk_skus);
      expect(kpis.overstock_skus).toBe(reference.overstock_skus);
      expect(kpis.expiry_units).toBeCloseTo(reference.expiry_units, 6);
      expect(kpis.inventory_value).toBe(reference.inventory_value);
      expect(kpis.at_risk_value).toBe(reference.at_risk_value);
      expect(Number(kpis.avg_dos.toFixed(1))).toBeCloseTo(
        Number(reference.avg_dos.toFixed(1)),
        6,
      );
    },
  );

  it("totals the whole chain to the sum of its verticals", () => {
    const all = computeKpis(fixture.items);
    const summed = fixture.reference_by_vertical.reduce(
      (running, row) => ({
        stockout_risk_skus: running.stockout_risk_skus + row.stockout_risk_skus,
        inventory_value: running.inventory_value + row.inventory_value,
        at_risk_value: running.at_risk_value + row.at_risk_value,
      }),
      { stockout_risk_skus: 0, inventory_value: 0, at_risk_value: 0 },
    );

    expect(all.stockout_risk_skus).toBe(summed.stockout_risk_skus);
    expect(all.inventory_value).toBe(summed.inventory_value);
    expect(all.at_risk_value).toBe(summed.at_risk_value);
    expect(all.sku_count).toBe(800);
  });
});

describe("scoping", () => {
  it("narrows to one category and keeps its parent vertical's stores", () => {
    const scope = scopeOf({ legal_entity_id: "GRC", category_group: "GRC-C01" });
    const payload = buildDashboardFromFixture(fixture, scope);

    expect(payload.kpis.sku_count).toBeGreaterThan(0);
    expect(payload.kpis.sku_count).toBeLessThan(800);
    for (const row of payload.risk_register) {
      expect(row.category_id).toBe("GRC-C01");
    }
    for (const option of payload.filter_options.categories) {
      expect(option.legal_entity_id).toBe("GRC");
    }
  });

  it("filters by state and by free-text SKU search", () => {
    const byState = buildDashboardFromFixture(
      fixture,
      scopeOf({ state: "Stockout" }),
    );
    for (const row of byState.risk_register) {
      expect(row.state).toBe("Stockout");
    }

    const bySearch = buildDashboardFromFixture(
      fixture,
      scopeOf({ sku: "GRC-001" }),
    );
    expect(bySearch.risk_register).toHaveLength(1);
    expect(bySearch.risk_register[0].sku_id).toBe("GRC-001");
  });

  it("leaves store scoping to the API, without breaking the store charts", () => {
    // See SUPPORTS_STORE_SCOPE: chain-net items carry no store dimension, so
    // a store selection must not silently narrow the KPIs here.
    const unscoped = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const withStore = buildDashboardFromFixture(
      fixture,
      scopeOf({ store_id: "S001" }),
    );

    expect(withStore.kpis).toEqual(unscoped.kpis);
    expect(withStore.scope.store_id).toBe("S001");
    expect(withStore.stockout_by_store).toHaveLength(160);
  });
});

describe("derived views", () => {
  it("orders the risk register by severity, then by value", () => {
    const { risk_register: rows } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );

    for (let index = 1; index < rows.length; index += 1) {
      const previous = rows[index - 1];
      const current = rows[index];
      expect(previous.severity_rank).toBeLessThanOrEqual(current.severity_rank);
      if (previous.severity_rank === current.severity_rank) {
        expect(previous.inv_value).toBeGreaterThanOrEqual(current.inv_value);
      }
    }
  });

  it("keeps category value shares summing to one", () => {
    const { value_by_category: rows } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );
    const total = rows.reduce((running, row) => running + row.share, 0);
    expect(total).toBeCloseTo(1, 9);
  });

  it("splits at-risk value by state into category segments", () => {
    const { at_risk_by_state: rows } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );

    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      const segments = row.segments.reduce(
        (running, segment) => running + segment.value,
        0,
      );
      expect(segments).toBeCloseTo(row.total, 6);
    }
    // States must come out in severity order, not insertion order.
    const ranks = rows.map((row) => STATE_ORDER.indexOf(row.state));
    expect([...ranks].sort((a, b) => a - b)).toEqual(ranks);
  });

  it("buckets expiry units and lists the shortest-dated first", () => {
    const { expiry_timeline: timeline } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );

    expect(timeline.buckets).toHaveLength(4);
    const bucketed = timeline.buckets.reduce(
      (running, bucket) => running + bucket.units,
      0,
    );
    const total = fixture.items.reduce(
      (running, item) => running + item.expiry_units,
      0,
    );
    expect(bucketed).toBeCloseTo(total, 6);

    expect(timeline.watchlist.length).toBeGreaterThan(0);
    for (let index = 1; index < timeline.watchlist.length; index += 1) {
      expect(timeline.watchlist[index - 1].shelf_life_days).toBeLessThanOrEqual(
        timeline.watchlist[index].shelf_life_days,
      );
    }
  });

  it("reports store and cluster figures as gross, above the chain-net headline", () => {
    const payload = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const clusterTotal = payload.at_risk_by_cluster.reduce(
      (running, row) => running + row.value,
      0,
    );

    expect(payload.at_risk_by_cluster).toHaveLength(4);
    expect(payload.at_risk_by_legal_entity).toHaveLength(8);
    // Gross sums local pockets; chain-net nets them off. A2 spec 10 note 1.
    expect(clusterTotal).toBeGreaterThan(payload.kpis.at_risk_value);
  });
});

describe("the data gateway", () => {
  it("returns a normalized payload the components can render", async () => {
    const payload = await loadInventoryRiskDashboard({ legal_entity_id: "GRC" });

    expect(payload.schema_version).toBe(1);
    expect(payload.agent).toBe("retail.inventory_risk");
    expect(payload.is_mock).toBe(true);
    expect(payload.note).not.toBe("");
    expect(payload.scope.legal_entity_id).toBe("GRC");
    expect(payload.scope.category_group).toBe(ALL);
    expect(payload.kpis.sku_count).toBe(100);
  });

  it("defaults to the whole chain when given no scope", async () => {
    const payload = await loadInventoryRiskDashboard();

    expect(payload.scope).toEqual(DEFAULT_SCOPE);
    expect(payload.kpis.sku_count).toBe(800);
  });
});
