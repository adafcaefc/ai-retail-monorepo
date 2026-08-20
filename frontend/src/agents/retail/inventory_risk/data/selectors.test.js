/**
 * The point of these tests is reconciliation, not coverage.
 *
 * `fixture.json` is generated from the workbook and carries the workbook's own
 * per-vertical totals in `reference_by_vertical`. If a selector ever starts
 * deriving a number instead of reading one, these comparisons break — which is
 * the entire safety net behind putting no thresholds in JavaScript.
 */

import { describe, expect, it } from "vitest";

import {
  ALL,
  DAYS_PER_WEEK,
  DEFAULT_HORIZON_WEEKS,
  DEFAULT_SCOPE,
  PROJECTION_HORIZONS_WEEKS,
  STATE_ORDER,
  resolveHorizonWeeks,
} from "./contract.js";
import { loadInventoryRiskDashboard } from "./dashboardData.js";
import fixture from "./fixture.json";
import {
  buildDashboardFromFixture,
  buildDrilldownFromFixture,
  computeKpis,
  computeProjection,
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

  it("narrows the store chart to the rows in scope, not the whole shelf", () => {
    /*
     * The defect this guards: the store, cluster and legal-entity charts read
     * aggregates summed over a store's entire shelf, so a category filter
     * moved the tiles and left the bars alone. Scoped to GRC-C01, the tiles
     * described 3 at-risk SKUs in S001 while the bar still showed 46.
     *
     * The expected figures are `ENGINE_STORE`'s own, filtered to S001 and
     * cat_id GRC-C01 in the workbook extract: 5 rows, 3 of them below ROP,
     * Rp 8,262,700 at risk.
     */
    const payload = buildDashboardFromFixture(
      fixture,
      scopeOf({ legal_entity_id: "GRC", category_group: "GRC-C01" }),
    );
    const s001 = payload.stockout_by_store.find((row) => row.store_id === "S001");

    expect(s001.sku_count).toBe(5);
    expect(s001.stockout_risk_count).toBe(3);
    expect(s001.at_risk_value).toBeCloseTo(8262700, 2);
  });

  it("gives the same per-store answer as the drill-down drawer", () => {
    // Two panels, one question. The drawer already derived its split from the
    // scoped rows; the chart used to derive nothing at all, so the board
    // answered "at risk in S001" with two different numbers depending on where
    // the reader looked.
    const scope = scopeOf({
      legal_entity_id: "GRC",
      category_group: "GRC-C01",
    });
    const payload = buildDashboardFromFixture(fixture, scope);
    const drawer = buildDrilldownFromFixture(fixture, scope, "stockout_risk_skus");

    for (const bar of payload.stockout_by_store) {
      const split = drawer.by_store.find((row) => row.id === bar.store_id);
      // `ranked` drops zeros, so a store with none is absent from the drawer.
      expect(split?.value ?? 0).toBe(bar.stockout_risk_count);
    }
  });

  it("derives the same totals the workbook aggregated, when nothing narrows", () => {
    /*
     * The two paths have to agree or the filter changes the measurement rather
     * than the scope. A search matching every SKU in the vertical narrows
     * nothing real, but it does force the derivation — so this compares
     * `atStore` against the workbook's own ENGINE_STORE aggregates across all
     * twenty Grocery stores, without hard-coding one of them.
     */
    const stored = buildDashboardFromFixture(
      fixture,
      scopeOf({ legal_entity_id: "GRC" }),
    );
    const derived = buildDashboardFromFixture(
      fixture,
      scopeOf({ legal_entity_id: "GRC", sku: "GRC-" }),
    );

    expect(derived.stockout_by_store).toHaveLength(20);
    for (const [index, row] of derived.stockout_by_store.entries()) {
      const want = stored.stockout_by_store[index];
      expect(row.store_id).toBe(want.store_id);
      expect(row.sku_count).toBe(want.sku_count);
      expect(row.stockout_count).toBe(want.stockout_count);
      expect(row.low_count).toBe(want.low_count);
      expect(row.other_at_risk_count).toBe(want.other_at_risk_count);
      expect(row.healthy_count).toBe(want.healthy_count);
      expect(row.stockout_risk_count).toBe(want.stockout_risk_count);
      expect(row.at_risk_value).toBeCloseTo(want.at_risk_value, 2);
    }
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

  it("lands every open PO, keeps it, and reorders on top of it", () => {
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
    // The longest lead time in the dataset is 7 days, well inside the horizon,
    // so every opening PO has landed. The policy reorders on top of them, so
    // the total landed is at least that — and, on this fixture, more.
    expect(projection.points.at(-1).inbound).toBeGreaterThan(totalInbound);
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

  it("runs to whichever horizon it is asked for, in whole weeks", () => {
    for (const weeks of PROJECTION_HORIZONS_WEEKS) {
      const { projection } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE, {
        horizonWeeks: weeks,
      });

      expect(projection.horizon_weeks).toBe(weeks);
      expect(projection.days).toBe(weeks * DAYS_PER_WEEK);
      expect(projection.points).toHaveLength(weeks * DAYS_PER_WEEK + 1);
      expect(projection.points.at(-1).label).toBe(`D+${weeks * DAYS_PER_WEEK}`);
    }
  });

  it("opens on the default horizon and ignores one it cannot honour", () => {
    const fallbacks = [undefined, 0, 7, "many", -4, null];

    for (const requested of fallbacks) {
      const { projection } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE, {
        horizonWeeks: requested,
      });
      expect(projection.horizon_weeks).toBe(DEFAULT_HORIZON_WEEKS);
    }

    // A horizon arriving as a string is the ordinary case from a query or a
    // stored preference, and is honoured rather than dropped to the default.
    expect(resolveHorizonWeeks("12")).toBe(12);
  });

  it("keeps the whole day-0 position, whatever the horizon", () => {
    const short = buildDashboardFromFixture(fixture, DEFAULT_SCOPE, {
      horizonWeeks: PROJECTION_HORIZONS_WEEKS[0],
    }).projection;
    const long = buildDashboardFromFixture(fixture, DEFAULT_SCOPE, {
      horizonWeeks: PROJECTION_HORIZONS_WEEKS.at(-1),
    }).projection;

    // Lengthening the look-ahead extends the curve; it must not move its
    // opening point or the strip beneath it, which describe today.
    expect(long.points[0].on_hand).toBeCloseTo(short.points[0].on_hand, 6);
    expect(long.metrics.position).toBeCloseTo(short.metrics.position, 6);
    expect(long.days_to_empty).toBe(short.days_to_empty);
  });

  it("offers the horizons through the payload, not through the control", () => {
    const { filter_options: options } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );

    expect(options.horizons_weeks).toEqual([...PROJECTION_HORIZONS_WEEKS]);
  });

  it("draws the scenario against a baseline of the same length", () => {
    const weeks = PROJECTION_HORIZONS_WEEKS.at(-1);
    const { simulation } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE, {
      horizonWeeks: weeks,
      levers: { demand: 20 },
    });

    // Compare Scenarios overlays these two. A baseline drawn over four weeks
    // against a scenario drawn over sixteen would put two different questions
    // on one axis.
    expect(simulation.baseline_projection.days).toBe(weeks * DAYS_PER_WEEK);
    expect(simulation.projection.days).toBe(weeks * DAYS_PER_WEEK);
  });

  /*
   * The demand model, not just the stock model. These four are the reason this
   * panel stopped burning a flat ADS: the shape has to come from the same
   * decomposition Demand Forecasting draws, and it has to roll back up to the
   * workbook's own weekly figure rather than quietly restating it.
   */

  it("burns a week that adds up to the workbook's forecast_7d", () => {
    const { projection } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const week = projection.points
      .slice(0, 7)
      .reduce((running, point) => running + point.demand, 0);

    // f08: forecast_7d = ads * dow_sum. The seven day-of-week factors sum to
    // dow_sum by construction and seasonality is 1.0 at the current month, so
    // the only gap is one week of compounded trend — a few tenths of a
    // percent. A shape that reallocates a measured week, not a new week.
    const forecast7d =
      fixture.items.reduce((running, item) => running + item.ads, 0) *
      fixture.constants.dow_sum;

    expect(week / forecast7d).toBeGreaterThan(0.995);
    expect(week / forecast7d).toBeLessThan(1.005);
  });

  it("moves demand across the week instead of reporting one number", () => {
    const { projection } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const week = projection.points.slice(0, 7).map((point) => point.demand);

    // The old panel published a constant here, so the line was flat by
    // construction and a Saturday cost the same as a Tuesday.
    expect(new Set(week).size).toBe(7);

    const profile = fixture.constants.dow_profile;
    expect(Math.max(...week) / Math.min(...week)).toBeCloseTo(
      Math.max(...profile) / Math.min(...profile),
      2,
    );
  });

  it("reorders at ROP rather than landing one PO and decaying forever", () => {
    const { projection } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE, {
      horizonWeeks: PROJECTION_HORIZONS_WEEKS.at(-1),
    });
    const openingPos = fixture.items.reduce(
      (running, item) => running + item.open_po,
      0,
    );

    // Arrivals on more than one day, and more units than the workbook's own
    // open POs — both impossible under the single-step model this replaced.
    const arrivalDays = projection.points.filter(
      (point, index) =>
        index > 0 && point.inbound > projection.points[index - 1].inbound,
    );
    expect(arrivalDays.length).toBeGreaterThan(1);
    expect(projection.points.at(-1).inbound).toBeGreaterThan(openingPos);

    // A chain that reorders does not run itself dry.
    expect(projection.days_to_empty).toBeNull();
  });

  it("places one order per cycle, not one per day of the lead time", () => {
    // The policy triggers on the inventory position, so an order already in
    // the pipeline suppresses the next. Triggering on on-hand alone would
    // order on all seven days of this SKU's lead time for one shortfall.
    const item = {
      sku_id: "TST-001",
      vertical_id: "GRC",
      on_hand: 100,
      open_po: 0,
      ads: 50,
      rop: 350,
      max: 550,
      lead_days: 7,
      dos: 2,
      at_risk_value: 0,
    };

    const projection = computeProjection([item], 28);
    const arrivals = projection.points.filter(
      (point, index) =>
        index > 0 && point.inbound > projection.points[index - 1].inbound,
    );

    // Four weeks at a seven-day lead time: a handful of cycles, nowhere near
    // the 28 an on-hand trigger would place.
    expect(arrivals.length).toBeGreaterThan(0);
    expect(arrivals.length).toBeLessThanOrEqual(5);
  });

  /*
   * The API path, which the rest of this suite cannot see.
   *
   * `DATA_SOURCE` is pinned to "fixture" under Vitest, so every test above
   * reads a payload that carries the demand model. The real board defaults to
   * "api", and a backend that omits these three blocks gets the flat fallback
   * -- which is exactly how a straight line shipped while 309 tests were
   * green. These two pin the contract from the consuming end.
   */

  it("names the three blocks a provider must send to get a shaped burn", () => {
    // Fixture and API run the SAME selectors over the SAME shape, so whatever
    // the fixture carries here is what the backend has to serve.
    expect(fixture.constants.dow_profile).toHaveLength(7);
    expect(
      fixture.constants.dow_profile.reduce((a, b) => a + b, 0),
    ).toBeCloseTo(fixture.constants.dow_sum, 9);
    expect(Object.keys(fixture.seasonality.by_legal_entity).length).toBeGreaterThan(0);
    for (const row of fixture.reference_by_vertical) {
      expect(typeof row.trend_pct).toBe("number");
    }
  });

  it("degrades to a flat burn when a payload omits them, and not silently wrong", () => {
    // A provider built before the model existed. The projection must still
    // render -- but flat, and identical to the straight-line burn this panel
    // drew before, rather than throwing or inventing a shape.
    const bare = {
      ...fixture,
      constants: { dow_sum: fixture.constants.dow_sum, month_index: 6 },
      seasonality: undefined,
      reference_by_vertical: fixture.reference_by_vertical.map(
        ({ trend_pct: _drop, ...rest }) => rest,
      ),
    };

    const flat = buildDashboardFromFixture(bare, DEFAULT_SCOPE).projection;
    const shaped = buildDashboardFromFixture(fixture, DEFAULT_SCOPE).projection;

    const flatDemand = flat.points.map((point) => point.demand);
    expect(new Set(flatDemand.map((d) => Math.round(d))).size).toBe(1);

    // Same measured level either way: a week of the flat burn still totals
    // what a week of the shaped one does. Only the shape is lost.
    const week = (points) =>
      points.slice(0, 7).reduce((running, point) => running + point.demand, 0);
    expect(week(flat.points) / week(shaped.points)).toBeGreaterThan(0.99);
    expect(week(flat.points) / week(shaped.points)).toBeLessThan(1.01);
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

  it("derives store and cluster charts under the simulation when levers are active", () => {
    const scope = { ...DEFAULT_SCOPE, legal_entity_id: "GRC" };
    const driven = buildDashboardFromFixture(fixture, scope, {
      levers: { demand: 40 },
    });
    const untouched = buildDashboardFromFixture(fixture, scope);

    expect(driven.stockout_by_store).not.toEqual(untouched.stockout_by_store);
    expect(driven.at_risk_by_cluster).not.toEqual(untouched.at_risk_by_cluster);
  });
});

describe("money figures behind the counts", () => {
  it("prices overstock from f23, not the whole position", () => {
    const { kpis } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const overstocked = fixture.items.filter((item) => item.is_overstock);

    // f23-markdown-at-risk-gross's Overstock/Slow-mover branch: excess above
    // Max where there is any, else 30% of position -- never the full
    // position value, which is the distinction A2 spec 10 note 3 draws.
    const atRisk = overstocked.reduce(
      (running, item) => running + item.markdown_at_risk_gross,
      0,
    );
    const fullPosition = overstocked.reduce(
      (running, item) => running + item.position * item.price,
      0,
    );

    expect(kpis.overstock_excess_value).toBeCloseTo(atRisk, 6);
    expect(kpis.overstock_excess_value).toBeLessThan(fullPosition);
  });

  it("prices expiry exposure from f23's Expiry branch", () => {
    const { kpis } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const expected = fixture.items.reduce(
      (running, item) =>
        item.state === "Expiry" ? running + item.markdown_at_risk_gross : running,
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
