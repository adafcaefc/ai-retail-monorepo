/**
 * Derive a Replenishment payload from the workbook fixture.
 *
 * Counts, sums, groups and sorts. Every rule the board depends on — which SKUs
 * need reordering, how much, at what price, on which route — was resolved in
 * `scripts/build_replenishment_fixture.py` against the catalogue formulas and
 * checked line by line against `A3 Replenishment` before the fixture was
 * written. Nothing here re-decides any of it.
 */

import {
  AGENT_ID,
  ALL,
  BASELINE_LEVERS,
  DEFAULT_SCOPE,
  REQUIREMENT_DAYS,
  REQUIREMENT_WEEKS,
  ROUTE_ORDER,
  SCHEMA_VERSION,
  SIMULATION_METRICS,
} from "./contract.js";
import { dosHistogram, topGroups } from "../../common/distributions.js";
import { buildDrilldown } from "./drilldown.js";
import { createEngine, isBaseline } from "./engine.js";

const sum = (rows, key) => rows.reduce((total, row) => total + (row[key] ?? 0), 0);

function matchesSearch(line, term) {
  const needle = term.trim().toLowerCase();
  if (!needle) return true;
  return (
    line.sku_id.toLowerCase().includes(needle) ||
    line.name.toLowerCase().includes(needle)
  );
}

/**
 * Apply the scope.
 *
 * `reorder_only` defaults on, which is the difference between a purchase-order
 * screen and an inventory report: a buyer opening this board is looking at
 * what has to be ordered today, not at all 800 SKUs. The toggle is there
 * because the fill-rate KPI needs the denominator.
 */
export function scopeLines(lines, scope) {
  return lines.filter((line) => {
    if (scope.legal_entity_id !== ALL && line.vertical_id !== scope.legal_entity_id) {
      return false;
    }
    if (scope.category_group !== ALL && line.category_id !== scope.category_group) {
      return false;
    }
    if (scope.route !== ALL && line.route !== scope.route) return false;
    if (scope.reorder_only && !line.is_reorder) return false;
    return matchesSearch(line, scope.sku);
  });
}

function scopeStores(stores, scope) {
  if (scope.legal_entity_id === ALL) return stores;
  return stores.filter((store) => store.vertical_id === scope.legal_entity_id);
}

/**
 * The six A3 KPIs, plus the two figures that make the board actionable.
 *
 * `fill_rate_pct` and `avg_cover_days` are measured over EVERY line in scope,
 * not only the ones being reordered — a fill rate computed over the reorder
 * list alone would always be zero, and a cover average over it would describe
 * the problem rather than the chain.
 */
export function computeKpis(lines, allLines) {
  const need = lines.filter((line) => line.is_reorder);
  const universe = allLines.length ? allLines : lines;
  const healthy = universe.filter((line) => !line.is_reorder).length;

  return {
    skus_to_reorder: need.length,
    order_units: sum(lines, "order_qty_sales"),
    order_value_retail: sum(lines, "order_value_retail"),
    order_value_cost: sum(lines, "order_value_cost"),
    inbound_open_po: sum(lines, "open_po"),
    fill_rate_pct: universe.length ? (healthy / universe.length) * 100 : 0,
    avg_cover_days: universe.length ? sum(universe, "dos") / universe.length : 0,
    // What switching every line to its cheapest quoted vendor would recover.
    // The only number on this board that proposes something.
    recoverable_saving: sum(lines, "saving_vs_designated"),
    line_count: lines.length,
  };
}

function groupBy(rows, key, label, extra = () => ({})) {
  const grouped = new Map();
  for (const row of rows) {
    const id = row[key];
    const bucket = grouped.get(id) || {
      id,
      label: label(row),
      line_count: 0,
      order_units: 0,
      order_value_retail: 0,
      order_value_cost: 0,
      saving: 0,
      ...extra(row),
    };
    bucket.line_count += 1;
    bucket.order_units += row.order_qty_sales ?? 0;
    bucket.order_value_retail += row.order_value_retail ?? 0;
    bucket.order_value_cost += row.order_value_cost ?? 0;
    bucket.saving += row.saving_vs_designated ?? 0;
    grouped.set(id, bucket);
  }
  return [...grouped.values()];
}

/** A3 spec 5a: order value by route, in lead-time order rather than by size. */
export function computeByRoute(lines, routes) {
  const byId = new Map(
    groupBy(lines, "route", (row) => row.route).map((row) => [row.id, row]),
  );

  return ROUTE_ORDER.map((id) => {
    const definition = routes.find((route) => route.id === id);
    const bucket = byId.get(id);
    return {
      id,
      label: definition?.label ?? id,
      added_days: definition?.added_days ?? 0,
      note: definition?.note ?? "",
      line_count: bucket?.line_count ?? 0,
      order_units: bucket?.order_units ?? 0,
      order_value_retail: bucket?.order_value_retail ?? 0,
      order_value_cost: bucket?.order_value_cost ?? 0,
      saving: bucket?.saving ?? 0,
    };
  });
}

/** A3 spec 5b: order value by store, largest first. */
export function computeByStore(stores) {
  return [...stores]
    .map((store) => ({
      id: store.store_id,
      label: store.name,
      legal_entity_id: store.vertical_id,
      cluster: store.cluster,
      line_count: store.reorder_count,
      order_units: store.order_units,
      order_value_retail: store.order_value_retail,
      open_po: store.open_po,
    }))
    .sort((a, b) => b.order_value_retail - a.order_value_retail);
}

export function computeByCategory(lines) {
  return groupBy(lines, "category_id", (row) => row.category_label)
    .map((row) => ({ ...row, legal_entity_id: undefined }))
    .sort((a, b) => b.order_value_retail - a.order_value_retail);
}

export function computeByCluster(stores) {
  const grouped = new Map();
  for (const store of stores) {
    const bucket = grouped.get(store.cluster) || {
      id: store.cluster,
      label: store.cluster,
      store_count: 0,
      order_value_retail: 0,
      order_units: 0,
    };
    bucket.store_count += 1;
    bucket.order_value_retail += store.order_value_retail;
    bucket.order_units += store.order_units;
    grouped.set(store.cluster, bucket);
  }
  return [...grouped.values()].sort(
    (a, b) => b.order_value_retail - a.order_value_retail,
  );
}

/**
 * Order value rolled store -> legal entity (mockup `ch-dim-le`).
 *
 * Summed from the store rows rather than the chain-net lines, so it sits on
 * the same basis as the cluster and store panels beside it — the mockup's own
 * `Σ stores in entity`. That makes it GROSS like those two, and it will
 * therefore exceed the chain-net headline for the same documented reason.
 *
 * Grouping the lines instead would be exact but would put one chart in the
 * grid on a different basis from the other three, which is the harder error to
 * notice: four bars that look comparable and are not.
 */
export function computeByLegalEntity(stores, legalEntities = []) {
  const labelOf = new Map(
    legalEntities.map((entity) => [entity.value, entity.label]),
  );
  const grouped = new Map();

  for (const store of stores) {
    const bucket = grouped.get(store.vertical_id) || {
      id: store.vertical_id,
      label: labelOf.get(store.vertical_id) ?? store.vertical_id,
      store_count: 0,
      order_value_retail: 0,
      order_units: 0,
    };
    bucket.store_count += 1;
    bucket.order_value_retail += store.order_value_retail;
    bucket.order_units += store.order_units;
    grouped.set(store.vertical_id, bucket);
  }

  return [...grouped.values()].sort(
    (a, b) => b.order_value_retail - a.order_value_retail,
  );
}

/**
 * Where the money would go, and where it could go instead.
 *
 * Grouped by the vendor the trade agreement designates, with the part that a
 * cheaper quote would recover shown against it. `saving_vs_designated` is the
 * workbook's own column; nothing here recalculates a price.
 */
export function computeVendorSplit(lines) {
  const grouped = new Map();
  for (const line of lines) {
    const bucket = grouped.get(line.designated_vendor) || {
      vendor: line.designated_vendor,
      line_count: 0,
      order_value_cost: 0,
      saving: 0,
      switchable_lines: 0,
    };
    bucket.line_count += 1;
    bucket.order_value_cost += line.order_value_cost;
    bucket.saving += line.saving_vs_designated;
    if (line.saving_vs_designated > 0) bucket.switchable_lines += 1;
    grouped.set(line.designated_vendor, bucket);
  }
  return [...grouped.values()].sort(
    (a, b) => b.order_value_cost - a.order_value_cost,
  );
}

/**
 * The quotes a saving is a difference between.
 *
 * `computeVendorSplit` above says how much is recoverable per vendor;
 * this says which SKU, at whose price, against whose. Until `trade_agreement`
 * reached a payload, the board could state the saving but not the evidence —
 * a buyer was asked to move a line to a vendor whose price was not on screen.
 *
 * The saving is read off the line rather than recomputed here. `engine.js`
 * already re-derives it from f11 under a lever, and `engine.test.js` holds it
 * to the workbook's stored column at rest, so taking it from the line is what
 * keeps this panel, the KPI tile and the vendor split showing one number.
 *
 * The ranking is by list price, which is the workbook's own basis. Applying
 * `discount_pct` would name a different winner on 159 of 800 SKUs — so the
 * discount is shown as a column and never folded into the comparison. One
 * board cannot carry two answers to "who is cheapest" without saying which.
 */
export function computeSourcing(lines, quotes, terms) {
  if (!quotes?.length) {
    return { terms: terms ?? null, skus: [], switchable_lines: 0, on_best_lines: 0 };
  }

  const bySku = new Map();
  for (const quote of quotes) {
    const offers = bySku.get(quote.sku_id);
    if (offers) offers.push(quote);
    else bySku.set(quote.sku_id, [quote]);
  }

  const skus = [];
  let onBest = 0;
  for (const line of lines) {
    // Lines with nothing on order have no saving to recover, whatever the
    // price gap: the panel proposes a switch, not a purchase.
    if (line.order_qty_buy <= 0) continue;

    const offers = bySku.get(line.sku_id);
    if (!offers) continue;

    if (!(line.saving_vs_designated > 0)) {
      onBest += 1;
      continue;
    }

    skus.push({
      sku_id: line.sku_id,
      name: line.name,
      category_label: line.category_label,
      designated_vendor: line.designated_vendor,
      best_price_vendor: line.best_price_vendor,
      unit_price_trade: line.unit_price_trade,
      best_price: line.best_price,
      order_qty_buy: line.order_qty_buy,
      buy_uom: line.buy_uom,
      // What the saving is priced on: whole packs, not the shortfall.
      order_units: line.order_qty_buy * line.pack_factor,
      saving: line.saving_vs_designated,
      quotes: offers,
    });
  }

  skus.sort((a, b) => b.saving - a.saving);
  return {
    terms: terms ?? null,
    skus,
    switchable_lines: skus.length,
    on_best_lines: onBest,
  };
}

/**
 * A3 spec 5c: the purchase order itself, biggest commitment first.
 *
 * Sorted by cost rather than by shortfall: a buyer works down a PO by what it
 * spends, and the largest shortfall is not always the largest cheque.
 */
export function computePurchaseOrder(lines) {
  return [...lines]
    .filter((line) => line.order_qty_sales > 0)
    .sort((a, b) => b.order_value_cost - a.order_value_cost)
    .map((line) => ({
      sku_id: line.sku_id,
      name: line.name,
      category_label: line.category_label,
      route: line.route,
      on_hand: line.on_hand,
      open_po: line.open_po,
      position: line.position,
      rop: line.rop,
      max: line.max,
      order_qty_sales: line.order_qty_sales,
      order_qty_buy: line.order_qty_buy,
      buy_uom: line.buy_uom,
      pack_factor: line.pack_factor,
      order_value_cost: line.order_value_cost,
      order_value_retail: line.order_value_retail,
      designated_vendor: line.designated_vendor,
      best_price_vendor: line.best_price_vendor,
      saving_vs_designated: line.saving_vs_designated,
      lead_days: line.lead_days,
    }));
}

/**
 * A3 spec section 4: what the chain needs against what is already coming.
 *
 * Two presentations share this one entry point, and the data picks: every
 * line carrying a 32-week `demand_weekly` curve gets the weekly chart (see
 * `computeWeeklyRequirement`); anything else falls back to the daily
 * accumulation the workbook alone supports (`computeDailyRequirement`). A
 * stale fixture or an unseeded synthetic table therefore degrades to the old
 * chart instead of an empty panel.
 *
 * `baselineLines` is the same universe before any lever moved. Under a What-If
 * the weekly branch scales each line's curve by its own ads ratio, so the
 * demand and promo levers bend the backbone exactly as f01 bends ADS — pass
 * the baseline in and that stays a division; leave it out and the lines are
 * their own baseline.
 */
export function computeRequirement(lines, baselineLines = lines) {
  if (lines.length && lines.every((line) => line.demand_weekly)) {
    return computeWeeklyRequirement(lines, baselineLines);
  }
  return computeDailyRequirement(lines);
}

/** `W-16` … `W-1`, `W+1` … `W+16` — the label of curve position `index`. */
function weekLabel(index) {
  return index < REQUIREMENT_WEEKS.actual
    ? `W-${REQUIREMENT_WEEKS.actual - index}`
    : `W+${index - REQUIREMENT_WEEKS.actual + 1}`;
}

/**
 * The weekly chart: a measured demand backbone, split at today.
 *
 * Requirement is the scope's demand curve read straight off the lines — 16
 * actual weeks, then 16 forecast weeks, chain-net — so it rises and dips with
 * the data instead of accumulating a flat ADS into a straight line.
 *
 * Cover is modelled, and has to be: no table in this warehouse records when
 * an inbound order arrives (the same honesty the fallback's caveat states).
 * It is drawn as half this week's and half last week's demand — a supply that
 * replenishes on last week's sales, lagging demand by about half a week. The
 * mockup also dips that curve every fourth week; those shortfalls are
 * invented, and are deliberately not reproduced. Where demand grows, the gap
 * opens on its own, and the first forecast week it opens is the honest
 * headline: `first_shortfall_week`.
 */
function computeWeeklyRequirement(lines, baselineLines) {
  const baseAds = new Map(baselineLines.map((line) => [line.sku_id, line.ads]));

  const actual = Array(REQUIREMENT_WEEKS.actual).fill(0);
  const forecast = Array(REQUIREMENT_WEEKS.forecast).fill(0);
  for (const line of lines) {
    // The scenario's ads against the baseline's own: a lever that lifts a
    // line's ADS by 10% lifts its whole curve by the same 10%, and a promo
    // lever bends only the eligible lines' curves.
    const baseline = baseAds.get(line.sku_id) ?? line.ads;
    const ratio = baseline > 0 ? line.ads / baseline : 1;
    line.demand_weekly.actual.forEach(
      (value, index) => { actual[index] += value * ratio; },
    );
    line.demand_weekly.forecast.forEach(
      (value, index) => { forecast[index] += value * ratio; },
    );
  }

  const demand = [...actual, ...forecast];
  const points = demand.map((value, index) => ({
    label: weekLabel(index),
    kind: index < REQUIREMENT_WEEKS.actual ? "actual" : "forecast",
    requirement: value,
    // The oldest week has no prior week to lag against; its cover is its own
    // demand, which is the neutral choice at a boundary nothing is known past.
    cover: 0.5 * value + 0.5 * (index === 0 ? value : demand[index - 1]),
  }));

  // The divider the mockup draws `splitAt`: on the last actual point, between
  // it and the first forecast week. "Today" is the boundary the table's own
  // column names encode — actual_w1 behind, forecast_w1 ahead.
  const splitIndex = REQUIREMENT_WEEKS.actual - 1;

  let firstShortfall = null;
  for (let index = splitIndex + 1; index < points.length; index += 1) {
    if (points[index].requirement > points[index].cover) {
      firstShortfall = points[index].label;
      break;
    }
  }

  const last = points[points.length - 1];
  return {
    mode: "weekly",
    points,
    split_index: splitIndex,
    weeks: { ...REQUIREMENT_WEEKS },
    // The first forecast week, calibrated on this board: at baseline it is
    // the scope's Σ ADS × dow_sum, so the curve and the tiles state one
    // demand level.
    demand_per_week: forecast[0],
    first_shortfall_week: firstShortfall,
    // The gap at the end of the horizon: what this scope is short by, before
    // any order is raised.
    gap_at_horizon: Math.max(0, last.requirement - last.cover),
  };
}

/**
 * The fallback chart: two cumulative curves over a 28-day horizon.
 *
 * *Requirement* is demand accumulating at a flat ADS per day — flat because
 * one ADS per SKU is all the workbook holds. *Cover* is what is on the shelf
 * now plus each SKU's open PO once it lands on its lead day, which is why
 * that curve steps rather than slopes. Where requirement overtakes cover is
 * the gap a purchase order exists to fill, and the day it happens is the
 * honest headline: `cover_runs_out`.
 */
function computeDailyRequirement(lines, days = REQUIREMENT_DAYS) {
  const demandPerDay = sum(lines, "ads");
  const onHand = sum(lines, "on_hand");
  const points = [];

  for (let day = 0; day <= days; day += 1) {
    let landed = 0;
    for (const line of lines) {
      if (day >= line.lead_days) landed += line.open_po ?? 0;
    }

    points.push({
      day,
      label: day === 0 ? "Today" : `D+${day}`,
      requirement: demandPerDay * day,
      cover: onHand + landed,
      inbound_landed: landed,
    });
  }

  const shortfall = points.find((point) => point.requirement > point.cover);

  return {
    mode: "daily",
    days,
    points,
    demand_per_day: demandPerDay,
    // The first day cumulative demand exceeds everything on hand and inbound.
    cover_runs_out: shortfall ? shortfall.day : null,
    // The gap at the end of the horizon: what this scope is short by, before
    // any order is raised.
    gap_at_horizon: Math.max(
      0,
      points[points.length - 1].requirement - points[points.length - 1].cover,
    ),
  };
}

/**
 * Baseline against scenario, A3 spec section 9.
 *
 * `applyLevers` re-runs the workbook's own expressions per line; everything
 * here counts and sums the two sets exactly as `computeKpis` does, so any
 * difference between the columns can only have come from the formulas.
 *
 * The index bars are the panel's shape: baseline pinned at 100, scenario
 * against it, so four metrics on four different scales share one axis. A
 * baseline of zero has no index and is reported as `null` rather than as a
 * fabricated 100.
 */
export function computeSimulation(lines, universe, levers, applyLevers) {
  const merged = { ...BASELINE_LEVERS, ...levers };
  const applied = !isBaseline(merged);
  const baseline = computeKpis(lines, universe);

  /*
   * At rest the scenario IS the baseline. Re-running the engine here would
   * produce figures differing in the last float digit — 345 re-evaluations
   * summed instead of 345 readings — and the panel would report a delta on a
   * board nobody has touched.
   */
  const scenarioLines = applied ? lines.map((line) => applyLevers(line, merged)) : lines;
  const scenarioUniverse = applied
    ? universe.map((line) => applyLevers(line, merged))
    : universe;

  /*
   * Under a scenario the reorder set itself moves: a line that was healthy at
   * rest can fall below ROP once lead time rises. So the scenario's KPIs are
   * taken over the re-filtered set, not over the baseline's 345 rows — holding
   * the old membership would report a new order value for an old order.
   */
  const scenarioScoped = applied
    ? scenarioLines.filter((line) => line.is_reorder)
    : lines;
  const scenario = applied
    ? computeKpis(scenarioScoped, scenarioUniverse)
    : baseline;

  return {
    applied,
    levers: merged,
    baseline,
    scenario,
    /*
     * Two curves, because Compare Scenarios (A3 spec 9d) needs a reference
     * that does not move. The board's own `requirement` cannot serve: with
     * "levers drive whole page" on it is the simulated one, and a comparison
     * whose baseline shifts with the sliders compares nothing. The scenario's
     * curve is scaled against the baseline universe line by line, so a lever
     * bends the demand backbone by the same ratio it bends ADS.
     */
    baseline_requirement: computeRequirement(universe),
    requirement: applied ? computeRequirement(scenarioUniverse, universe) : null,
    index: SIMULATION_METRICS.map((metric) => ({
      ...metric,
      baseline_value: baseline[metric.id],
      scenario_value: scenario[metric.id],
      baseline_index: 100,
      scenario_index: baseline[metric.id]
        ? (scenario[metric.id] / baseline[metric.id]) * 100
        : null,
      delta: scenario[metric.id] - baseline[metric.id],
    })),
    /*
     * Named so the panel can say why a slider did nothing, rather than leaving
     * a reader to conclude the board is broken. `markdown` reaches no formula
     * in the catalogue — the workbook has no markdown term anywhere.
     */
    unmodelled: ["markdown"],
  };
}

/*
 * One engine per fixture, not one per render.
 *
 * `createEngine` parses nine expressions. A slider drag rebuilds the dashboard
 * every frame, and re-parsing there would turn a smooth control into a
 * stuttering one for nothing — the expressions cannot change between renders.
 */
let cachedFormulas = null;
let cachedEngine = null;

function engineFor(formulas) {
  if (formulas !== cachedFormulas) {
    cachedEngine = createEngine(formulas);
    cachedFormulas = formulas;
  }
  return cachedEngine;
}

/**
 * Decompose one KPI tile, over exactly the lines the board is showing.
 *
 * Note which set each metric gets. Fill rate and cover are measured over the
 * scope WITHOUT the reorder filter — `universe` — because a fill rate computed
 * over the reorder list alone is always zero, which is the same trap
 * `computeKpis` documents. Everything else describes the order itself.
 */
/**
 * A distribution per KPI tile — never a trend. See the Inventory Risk twin for
 * the full reasoning; the short version is that this workbook has no date
 * column, so a sparkline can only honestly describe spread, not movement.
 *
 * `lines` is the order set the headline used; `universe` is the same scope
 * without the reorder filter, which is what fill rate and cover are measured
 * over.
 */
export function computeKpiSparklines(lines, universe) {
  return {
    skus_to_reorder: {
      kind: "distribution",
      caption: "Days of cover, lines to reorder",
      values: dosHistogram(universe.filter((line) => line.is_reorder)),
    },
    order_units: {
      kind: "distribution",
      caption: "Units by category, largest first",
      values: topGroups(lines, "category_id", (rows) =>
        rows.reduce((total, row) => total + (row.order_qty_sales ?? 0), 0),
      ),
    },
    order_value_cost: {
      kind: "distribution",
      caption: "Cost by category, largest first",
      values: topGroups(lines, "category_id", (rows) =>
        rows.reduce((total, row) => total + (row.order_value_cost ?? 0), 0),
      ),
    },
    order_value_retail: {
      kind: "distribution",
      caption: "Retail value by category, largest first",
      values: topGroups(lines, "category_id", (rows) =>
        rows.reduce((total, row) => total + (row.order_value_retail ?? 0), 0),
      ),
    },
    // Fill rate is a property of the whole scope, so its shape is the cover
    // spread of every line — the lines to the left are the ones failing it.
    fill_rate_pct: {
      kind: "distribution",
      caption: "Days of cover, all lines",
      values: dosHistogram(universe),
    },
    recoverable_saving: {
      kind: "distribution",
      caption: "Saving by vendor, largest first",
      values: topGroups(lines, "designated_vendor", (rows) =>
        rows.reduce((total, row) => total + (row.saving_vs_designated ?? 0), 0),
      ),
    },
  };
}

export function buildDrilldownFromFixture(
  fixture,
  scope = {},
  metricId,
  options = {},
) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  const applyLevers = engineFor(fixture.formulas);
  const levers = { ...BASELINE_LEVERS, ...options.levers };
  const simulating = !isBaseline(levers) && options.driveWholePage !== false;

  const universe = scopeLines(fixture.lines, { ...merged, reorder_only: false });
  const live = simulating
    ? universe.map((line) => applyLevers(line, levers))
    : universe;

  const rows =
    metricId === "fill_rate_pct"
      ? live
      : live.filter((line) => !merged.reorder_only || line.is_reorder);

  return buildDrilldown(metricId, rows, scopeStores(fixture.stores, merged));
}

export function buildDashboardFromFixture(fixture, scope = {}, options = {}) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  const lines = scopeLines(fixture.lines, merged);

  // The denominator for fill rate and cover: the same scope, but without the
  // reorder filter, because those two describe the chain rather than the order.
  const universe = scopeLines(fixture.lines, { ...merged, reorder_only: false });
  const stores = scopeStores(fixture.stores, merged);

  const applyLevers = engineFor(fixture.formulas);
  const levers = { ...BASELINE_LEVERS, ...options.levers };
  const simulation = computeSimulation(lines, universe, levers, applyLevers);

  /*
   * "Levers drive whole page" (A3 spec 9b). With it on, every panel below
   * reads the re-simulated lines rather than the workbook's stored ones.
   *
   * Two things it cannot reach, and the board admits as much: the store and
   * cluster charts read `fixture.stores`, already aggregated per store before
   * it arrives here, and `reference_by_vertical` is the workbook's own total,
   * which belongs to the baseline by definition.
   */
  const driveWholePage = options.driveWholePage !== false;
  const simulating = simulation.applied && driveWholePage;

  /*
   * Re-simulate the unfiltered scope, then re-apply the reorder filter — in
   * that order. A lever that lengthens lead time pushes lines below ROP that
   * were healthy at rest, and filtering first would hide exactly the lines the
   * scenario was raised to find.
   */
  const liveUniverse = simulating
    ? universe.map((line) => applyLevers(line, levers))
    : universe;
  const live = simulating
    ? liveUniverse.filter((line) => !merged.reorder_only || line.is_reorder)
    : lines;

  const categories =
    merged.legal_entity_id === ALL
      ? fixture.filter_options.categories
      : fixture.filter_options.categories.filter(
          (category) => category.legal_entity_id === merged.legal_entity_id,
        );
  const storeOptions =
    merged.legal_entity_id === ALL
      ? fixture.filter_options.stores
      : fixture.filter_options.stores.filter(
          (store) => store.legal_entity_id === merged.legal_entity_id,
        );

  return {
    schema_version: SCHEMA_VERSION,
    agent: AGENT_ID,
    as_of: fixture.generated_at,
    is_mock: fixture.is_mock,
    note: fixture.note,
    derivation: fixture.derivation,
    scope: merged,
    routes: fixture.routes,
    filter_options: {
      legal_entities: fixture.filter_options.legal_entities,
      categories,
      stores: storeOptions,
      routes: fixture.filter_options.routes,
    },
    kpis: computeKpis(live, liveUniverse),
    kpi_sparklines: computeKpiSparklines(live, liveUniverse),
    // `universe` is the un-levered reference: under "levers drive whole page"
    // the curve scales itself against it, and at rest the two are the same
    // array and every ratio is one.
    requirement: computeRequirement(liveUniverse, universe),
    simulation,
    by_route: computeByRoute(live, fixture.routes),
    by_store: computeByStore(stores),
    by_category: computeByCategory(live),
    by_cluster: computeByCluster(stores),
    by_legal_entity: computeByLegalEntity(
      stores,
      fixture.filter_options.legal_entities,
    ),
    vendors: fixture.vendors,
    vendor_split: computeVendorSplit(live),
    sourcing: computeSourcing(live, fixture.quotes, fixture.quote_terms),
    purchase_order: computePurchaseOrder(live),
    reference_by_vertical: fixture.reference_by_vertical,
  };
}
