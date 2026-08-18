/**
 * KPI decomposition for the drill-down drawer — mirrors
 * pricing_markdown/data/drilldown.js.
 *
 * `additive` matters here more than on the sibling boards: capital freed and
 * contribution/day sum to their headline, but avg GMROI is an
 * inventory-weighted mean and tail share is a ratio — their bars do not add
 * up, and the drawer says so rather than letting a reader assume they do.
 */

import { KPI_FORMULAS } from "./contract.js";

export const TOP_SKU_COUNT = 6;

/** @param {string} id */
export function drilldownMetric(id) {
  const metric = METRICS[id];
  if (!metric) {
    throw new Error(`Assortment Optimization KPI ${id} has no drilldown metric definition`);
  }
  return metric;
}

export function drillableMetrics() {
  return Object.keys(METRICS);
}

/**
 * @param {string} metricId
 * @param {object[]} items  Items in scope (already driven and tabbed).
 */
export function buildDrilldown(metricId, items) {
  const metric = drilldownMetric(metricId);
  const population = metric.population ? items.filter(metric.population) : items;
  const total = round(metric.reduce(population), metric.digits ?? 0);

  const byCategory = topGroups(population, "category_id", (rows) =>
    round(metric.reduce(rows), metric.digits ?? 0),
  ).map((g) => ({
    category_id: g.key,
    label: labelFor(population, g.key, "category_id", "category_label"),
    value: g.value,
  }));

  const byVertical = topGroups(population, "vertical_id", (rows) =>
    round(metric.reduce(rows), metric.digits ?? 0),
  ).map((g) => ({
    vertical_id: g.key,
    label: g.key,
    value: g.value,
  }));

  const topSkus = [...population]
    .map((i) => ({
      sku_id: i.sku_id,
      name: i.name,
      vertical_id: i.vertical_id,
      category_label: i.category_label,
      value: round(metric.reduce([i]), metric.digits ?? 0),
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, TOP_SKU_COUNT);

  return {
    id: metricId,
    label: metric.label,
    formula: KPI_FORMULAS[metricId] ?? "",
    unit: metric.unit,
    additive: metric.additive,
    total,
    sku_count: population.length,
    by_category: byCategory,
    by_vertical: byVertical,
    top_skus: topSkus,
    // No date column in the workbook — history is unavailable, not hidden.
    history: null,
  };
}

const METRICS = {
  capital_freed: {
    label: "Capital freed",
    unit: "IDR",
    additive: true,
    population: (i) => i.classification === "delist",
    reduce: (rows) => sum(rows, "inv_value"),
  },
  contribution_per_day: {
    label: "Contribution/day",
    unit: "IDR",
    additive: true,
    reduce: (rows) => sum(rows, "contribution_per_day"),
  },
  avg_gmroi: {
    label: "Avg GMROI",
    unit: "x",
    additive: false,
    digits: 2,
    reduce: (rows) => weightedMean(rows, "gmroi", "inv_value"),
  },
};

// --------------------------------------------------------------------- helpers

function labelFor(items, key, keyField, labelField) {
  const found = items.find((i) => i[keyField] === key);
  return found?.[labelField] ?? key;
}

function sum(rows, key) {
  return rows.reduce((t, r) => t + (Number(r?.[key]) || 0), 0);
}

function weightedMean(rows, valueKey, weightKey) {
  let totalWeight = 0;
  let totalValue = 0;
  for (const row of rows) {
    const w = Number(row[weightKey]) || 0;
    totalWeight += w;
    totalValue += (Number(row[valueKey]) || 0) * w;
  }
  return totalWeight ? totalValue / totalWeight : 0;
}

function round(value, digits = 0) {
  if (!Number.isFinite(value)) return 0;
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function topGroups(rows, key, reduce, limit = 12) {
  const groups = new Map();
  for (const row of rows) {
    const k = row?.[key];
    if (k == null) continue;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(row);
  }
  return [...groups.entries()]
    .map(([k, rs]) => ({ key: k, value: reduce(rs) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}
