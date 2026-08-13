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

  /*
   * The KPI flags and the state must describe the same SKU, because the board
   * shows both at once: the tiles count flags, the state panel and the register
   * group by state. They used to disagree — `is_slow_mover` was a raw
   * `growth < 1 && DoS > 10`, which matched 62 SKUs while only 51 carried the
   * Slow-mover state, the other 11 having been claimed by a more urgent one.
   * The card read 62 and the chart under it read 51.
   */
  it("keeps every KPI flag in step with the state it reports on", () => {
    for (const item of fixture.items) {
      expect(item.is_overstock).toBe(item.state === "Overstock");
      expect(item.is_slow_mover).toBe(item.state === "Slow-mover");
      // Stockout-risk is the reorder zone, so it spans two states rather than
      // one. A2 sheet column B counts exactly Position < ROP.
      expect(item.is_stockout_risk).toBe(
        item.state === "Stockout" || item.state === "Low",
      );
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

  it("scopes to one store by re-deriving that store's rows", () => {
    const unscoped = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const withStore = buildDashboardFromFixture(
      fixture,
      scopeOf({ store_id: "S001" }),
    );

    expect(withStore.scope.store_id).toBe("S001");
    // S001 is a Grocery store and Grocery stocks 100 SKUs, so the register is
    // that store's shelf rather than the chain's 800.
    expect(withStore.kpis.sku_count).toBe(100);
    expect(withStore.kpis.sku_count).toBeLessThan(unscoped.kpis.sku_count);
    // Charts follow the tiles: one store selected, one bar.
    expect(withStore.stockout_by_store).toHaveLength(1);
    expect(unscoped.stockout_by_store).toHaveLength(160);
  });

  it("reproduces the workbook's own ENGINE_STORE figures for that store", () => {
    /*
     * The claim `SUPPORTS_STORE_SCOPE` makes is that a store's rows are
     * DERIVED exactly, not estimated. These are `ENGINE_STORE`'s own values
     * for S001, read out of the workbook extract — if the derivation drifts,
     * the store filter is quietly showing invented numbers and this fails.
     *
     * The fixture builder asserts the same thing over all 16,000 rows; this
     * asserts it survives the trip through the engine and the selectors.
     */
    const withStore = buildDashboardFromFixture(
      fixture,
      scopeOf({ store_id: "S001" }),
    );
    const row = withStore.risk_register.find((item) => item.sku_id === "GRC-001");

    expect(row).toBeDefined();
    expect(row.position).toBe(68);
    expect(row.rop).toBe(88);
    expect(row.max).toBe(204);
    expect(row.state).toBe("Low");
    expect(row.ads).toBeCloseTo(29.1668846784, 6);
    expect(row.on_hand).toBeCloseTo(66.79353298333037, 6);
    expect(row.dos).toBeCloseTo(2.3314111448576638, 6);

    // The whole store, against ENGINE_STORE's own state tally for S001.
    const states = withStore.risk_register.reduce((tally, item) => {
      tally[item.state] = (tally[item.state] ?? 0) + 1;
      return tally;
    }, {});
    expect(states).toEqual({
      Stockout: 19,
      Low: 27,
      Expiry: 8,
      "Slow-mover": 4,
      Healthy: 42,
    });
    expect(withStore.kpis.stockout_risk_skus).toBe(46);
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

  it("stacks every SKU a store carries, leaving none outside a segment", () => {
    // The defect this guards: an earlier chart stacked only part of the
    // breakdown, so a dozen SKUs per store sat in no bar at all and the column
    // silently understated the store.
    const { stockout_by_store: rows } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );

    expect(rows).toHaveLength(160);
    for (const row of rows) {
      const segments =
        row.stockout_count +
        row.low_count +
        row.other_at_risk_count +
        row.healthy_count;
      expect(segments).toBe(row.sku_count);
      // The reorder zone is exactly the first two segments.
      expect(row.stockout_count + row.low_count).toBe(row.stockout_risk_count);
    }
  });
});

describe("the projection", () => {
  it("starts at today's stock and never lets a SKU go negative", () => {
    const { projection } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const openingStock = fixture.items.reduce(
      (running, item) => running + item.on_hand,
      0,
    );

    expect(projection.points).toHaveLength(projection.days + 1);
    expect(projection.points[0].label).toBe("Today");
    // Day 0 has no arrivals yet for anything with a lead time, so opening
    // on-hand is the chain's on-hand, not its position.
    expect(projection.points[0].on_hand).toBeCloseTo(openingStock, 6);

    for (const point of projection.points) {
      expect(point.on_hand).toBeGreaterThanOrEqual(0);
    }
  });

  it("lands each open PO once, and never takes it back", () => {
    const { projection } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const totalInbound = fixture.items.reduce(
      (running, item) => running + item.open_po,
      0,
    );

    for (let index = 1; index < projection.points.length; index += 1) {
      expect(projection.points[index].inbound).toBeGreaterThanOrEqual(
        projection.points[index - 1].inbound,
      );
    }
    // The longest lead time in the dataset is 7 days, well inside the horizon.
    expect(projection.points.at(-1).inbound).toBeCloseTo(totalInbound, 6);
  });

  it("reports the strip figures the panel prints under the chart", () => {
    const { projection, kpis } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );

    expect(projection.metrics.at_risk_value).toBeCloseTo(kpis.at_risk_value, 6);
    expect(projection.metrics.avg_dos).toBeCloseTo(kpis.avg_dos, 9);
    expect(projection.metrics.inbound).toBeGreaterThan(0);
  });
});

describe("the simulation block", () => {
  it("reads as unapplied while every lever sits at zero", () => {
    const { simulation } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);

    expect(simulation.applied).toBe(false);
    expect(simulation.scenario).toEqual(simulation.baseline);
    for (const metric of simulation.index) {
      expect(metric.scenario_index).toBeCloseTo(100, 9);
      expect(metric.delta).toBe(0);
    }
  });

  it("compares the four metrics the A2 simulator panel shows", () => {
    const { simulation } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE, {
      levers: { demand: 20 },
    });

    expect(simulation.index.map((metric) => metric.id)).toEqual([
      "stockout_risk_skus",
      "expiry_units",
      "overstock_skus",
      "at_risk_value",
    ]);
    expect(simulation.applied).toBe(true);
    // A demand surge empties shelves: more SKUs below ROP than before.
    const stockout = simulation.index[0];
    expect(stockout.scenario_value).toBeGreaterThan(stockout.baseline_value);
  });

  it("only reaches the rest of the board when told to drive the whole page", () => {
    const scope = { ...DEFAULT_SCOPE, legal_entity_id: "GRC" };
    const levers = { demand: 40 };

    const driven = buildDashboardFromFixture(fixture, scope, { levers });
    const contained = buildDashboardFromFixture(fixture, scope, {
      levers,
      driveWholePage: false,
    });
    const untouched = buildDashboardFromFixture(fixture, scope);

    // Both know the scenario; only one lets it out of the panel.
    expect(driven.simulation.scenario).toEqual(contained.simulation.scenario);
    expect(driven.kpis).toEqual(driven.simulation.scenario);
    expect(contained.kpis).toEqual(untouched.kpis);
  });

  it("leaves the store charts on the baseline, because they arrive aggregated", () => {
    // Honest limit rather than a bug: `fixture.stores` is summed per store
    // before it reaches the selectors, so there are no rows left to re-run.
    const scope = { ...DEFAULT_SCOPE, legal_entity_id: "GRC" };
    const driven = buildDashboardFromFixture(fixture, scope, {
      levers: { demand: 40 },
    });
    const untouched = buildDashboardFromFixture(fixture, scope);

    expect(driven.stockout_by_store).toEqual(untouched.stockout_by_store);
    expect(driven.at_risk_by_cluster).toEqual(untouched.at_risk_by_cluster);
  });
});

describe("money figures behind the counts", () => {
  it("prices overstock as the excess above Max, not the whole position", () => {
    const { kpis } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const overstocked = fixture.items.filter((item) => item.is_overstock);

    const excess = overstocked.reduce(
      (running, item) =>
        item.position > item.max
          ? running + (item.position - item.max) * item.price
          : running,
      0,
    );
    const fullPosition = overstocked.reduce(
      (running, item) => running + item.position * item.price,
      0,
    );

    expect(kpis.overstock_excess_value).toBeCloseTo(excess, 6);
    // A2 spec 10 note 3: the two senses of "overstock" must not be conflated.
    expect(kpis.overstock_excess_value).toBeLessThan(fullPosition);
  });

  it("prices expiry exposure from the units already past cover", () => {
    const { kpis } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const expected = fixture.items.reduce(
      (running, item) => running + item.expiry_units * item.price,
      0,
    );

    expect(kpis.expiry_value).toBeCloseTo(expected, 6);
    expect(kpis.expiry_value).toBeGreaterThan(0);
  });
});

describe("suggested best action", () => {
  it("routes every non-healthy SKU to exactly one owning agent", () => {
    const { best_actions: routes, kpis } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );

    const routed = routes.reduce((running, route) => running + route.sku_count, 0);
    expect(routed).toBe(kpis.sku_count - kpis.healthy_skus);

    const names = routes.map((route) => route.next_agent).sort();
    expect(names).toEqual(["3 Replenish", "5 Markdown"]);
  });

  it("sends the reorder states to Agent 3 and the rest to Agent 5", () => {
    const { best_actions: routes } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );
    const byAgent = new Map(routes.map((route) => [route.next_agent, route]));

    expect(byAgent.get("3 Replenish").states).toEqual(["Stockout", "Low"]);
    for (const state of byAgent.get("5 Markdown").states) {
      expect(["Expiry", "Overstock", "Slow-mover"]).toContain(state);
    }
    // Ranked by exposure, and each route offers a short worklist.
    expect(routes[0].value).toBeGreaterThanOrEqual(routes[1].value);
    for (const route of routes) {
      expect(route.top_skus.length).toBeGreaterThan(0);
      expect(route.top_skus.length).toBeLessThanOrEqual(3);
    }
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
