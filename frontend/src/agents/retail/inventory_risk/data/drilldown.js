/**
 * Decompose one KPI tile into the breakdowns its drill-down drawer shows.
 *
 * WHY EACH METRIC CARRIES ITS OWN REDUCER
 * The drawer asks the same three questions of every tile — by category, by
 * store, which SKUs contribute most — but "contribute" means something
 * different per metric. Stockout-risk counts rows; inventory value sums a
 * product; average days of supply is a mean and cannot be summed at all. A
 * single `sum(item[field])` would quietly give a wrong answer for two of the
 * six, so each metric states its own reducer and whether it is additive.
 *
 * NOTHING HERE RE-CLASSIFIES ANYTHING
 * Same rule as the rest of this folder: `state` and the `is_*` flags arrive
 * resolved, and these reducers only count and sum them. No threshold appears
 * in this file.
 *
 * WHAT THE MOCKUP DID THAT THIS DOES NOT
 * The mockup's drawer draws a "12-period history of THIS metric" from a seeded
 * random walk (`rng(label.length * 97 + i * 131)`), and allocates its per-store
 * panel with `charCodeAt`. Both read as measurement and neither is one. The
 * workbook has no history at any grain -- `derivation.history` says
 * "unavailable" and A1 already refuses to back-cast a line for the same reason
 * -- so this module returns no history at all and the drawer says so. The
 * per-store panel here is real: `atStore` derives each store's own rows, which
 * the fixture builder checks against all 16,000 ENGINE_STORE rows.
 */

import { atStore, BASELINE_LEVERS } from "./engine.js";

/** How many rows the "top contributing SKUs" list shows. */
export const TOP_SKU_COUNT = 6;

/**
 * One entry per KPI tile.
 *
 * `additive` is the honest bit: a mean cannot be split across categories and
 * added back up, so the drawer labels those breakdowns as averages rather than
 * letting a reader sum the bars and wonder why they miss the headline.
 */
const METRICS = {
  stockout_risk_skus: {
    label: "Stockout-risk SKUs",
    reduce: (rows) => rows.filter((row) => row.is_stockout_risk).length,
    unit: "count",
    additive: true,
  },
  overstock_skus: {
    label: "Overstock SKUs",
    reduce: (rows) => rows.filter((row) => row.is_overstock).length,
    unit: "count",
    additive: true,
  },
  expiry_units: {
    label: "Expiry-risk units",
    reduce: (rows) => rows.reduce((total, row) => total + row.expiry_units, 0),
    unit: "units",
    additive: true,
  },
  slow_mover_skus: {
    label: "Slow-moving SKUs",
    reduce: (rows) => rows.filter((row) => row.is_slow_mover).length,
    unit: "count",
    additive: true,
  },
  avg_dos: {
    label: "Avg days of supply",
    reduce: (rows) =>
      rows.length ? rows.reduce((total, row) => total + row.dos, 0) / rows.length : 0,
    unit: "days",
    // A mean. The bars below are each group's own average, and they do not
    // add up to the headline -- which is why they are not presented as if
    // they might.
    additive: false,
  },
  inventory_value: {
    label: "Inventory value",
    reduce: (rows) => rows.reduce((total, row) => total + row.inv_value, 0),
    unit: "money",
    additive: true,
  },
};

export function drilldownMetric(id) {
  return METRICS[id] ?? null;
}

/** Every tile the drawer knows how to open. */
export function drillableMetrics() {
  return Object.keys(METRICS);
}

function groupBy(rows, key, label) {
  const grouped = new Map();
  for (const row of rows) {
    const id = row[key];
    if (!grouped.has(id)) grouped.set(id, { id, label: label(row), rows: [] });
    grouped.get(id).rows.push(row);
  }
  return [...grouped.values()];
}

function ranked(groups, reduce) {
  return groups
    .map((group) => ({
      id: group.id,
      label: group.label,
      value: reduce(group.rows),
    }))
    .filter((row) => Math.abs(row.value) > 1e-9)
    .sort((a, b) => b.value - a.value);
}

/**
 * Build the drawer payload for one metric, over the rows already in scope.
 *
 * @param {string} metricId   A key of METRICS.
 * @param {object[]} items    The scoped, already-simulated item rows.
 * @param {object[]} stores   The scoped store rows, for the store split.
 * @param {object} [options]
 * @param {Function} [options.applyLevers] Bound engine. Required for the store
 *   split: `atStore` only re-points a row's INPUTS, and the metrics read
 *   `state`, `dos` and the `is_*` flags, which exist only after the formula
 *   chain has run. Without it the store split is omitted rather than computed
 *   from chain-net values wearing a store's name.
 * @param {object[]} [options.allItems] Unscoped items for the store split, so a
 *   store's bar covers its whole shelf rather than the current filter.
 */
export function buildDrilldown(metricId, items, stores, options = {}) {
  const metric = drilldownMetric(metricId);
  if (!metric) return null;

  const { applyLevers = null, allItems = items } = options;

  const byCategory = ranked(
    groupBy(items, "category_id", (row) => row.category_name),
    metric.reduce,
  );

  /*
   * The store split is DERIVED, not allocated.
   *
   * Each store's rows are regenerated with `atStore` and run through the
   * engine at rest, exactly as a store-scoped board does — so a bar here is
   * that store's own position, and selecting that store in the filter bar
   * reproduces the same figure. The mockup allocated this from `charCodeAt`
   * and a health factor; that reads as measurement and is not one.
   *
   * The cost is real: one engine pass per SKU per store, so a whole-chain
   * scope is ~16,000 evaluations. It runs on a click rather than a render,
   * and the What-If slider already sustains 800 per frame, so this lands well
   * inside a frame budget it never has to meet.
   */
  const byStore = applyLevers
    ? ranked(
        stores.map((store) => ({
          id: store.store_id,
          label: store.name,
          rows: allItems
            .filter((item) => item.vertical_id === store.vertical_id)
            .map((item) => applyLevers(atStore(item, store), BASELINE_LEVERS)),
        })),
        metric.reduce,
      )
    : [];

  const topSkus = items
    .map((item) => ({ item, value: metric.reduce([item]) }))
    .filter((row) => Math.abs(row.value) > 1e-9)
    .sort((a, b) => b.value - a.value)
    .slice(0, TOP_SKU_COUNT)
    .map(({ item, value }) => ({
      id: item.sku_id,
      name: item.name,
      category_name: item.category_name,
      state: item.state,
      value,
    }));

  return {
    id: metricId,
    label: metric.label,
    unit: metric.unit,
    additive: metric.additive,
    total: metric.reduce(items),
    sku_count: items.length,
    by_category: byCategory,
    by_store: byStore,
    top_skus: topSkus,
    /*
     * No history, and not an oversight.
     *
     * The workbook stores one snapshot per SKU and no date column anywhere, so
     * a 12-period series would have to be generated -- which is what the
     * mockup does. `derivation.history` has said "unavailable" since A1 was
     * written; the drawer renders that as an empty state rather than a chart
     * nobody can tell is fictional. It fills in when a dated source lands.
     */
    history: null,
  };
}
