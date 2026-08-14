/**
 * KPI decomposition for the drill-down drawer.
 *
 * One tile opens into a drawer that splits its headline by category, by
 * vertical, and names the largest contributing SKUs. `additive` flags whether
 * the bars in the drawer sum to the headline: incremental margin and counts do;
 * uplift and ROI (means over verticals) do not.
 */

import { KPI_FORMULAS } from "./contract.js";

export const TOP_SKU_COUNT = 6;

/**
 * @param {string} id
 * @returns {{ label: string, unit: string, additive: boolean, reduce: (rows: object[]) => number }}
 */
export function drilldownMetric(id) {
  const metric = METRICS[id];
  if (!metric) {
    throw new Error(`Promotion KPI ${id} has no drilldown metric definition`);
  }
  return metric;
}

/** Every KPI the drawer can open from. */
export function drillableMetrics() {
  return Object.keys(METRICS);
}

/**
 * Build the drawer payload for one metric.
 *
 * @param {string} metricId
 * @param {object[]} items   Promo-eligible items in scope.
 * @returns {object}
 */
export function buildDrilldown(metricId, items) {
  const metric = drilldownMetric(metricId);
  const total = round(metric.reduce(items));

  const byCategory = topGroups(
    items,
    "category_id",
    (rows) => round(metric.reduce(rows)),
  ).map((g) => ({
    category_id: g.key,
    label: labelFor(items, g.key, "category_id", "category_label"),
    value: g.value,
  }));

  const byVertical = topGroups(
    items,
    "vertical_id",
    (rows) => round(metric.reduce(rows)),
  ).map((g) => ({
    vertical_id: g.key,
    label: labelFor(items, g.key, "vertical_id", "vertical_id"),
    value: g.value,
  }));

  const topSkus = [...items]
    .map((i) => ({
      sku_id: i.sku_id,
      name: i.name,
      vertical_id: i.vertical_id,
      category_label: i.category_label,
      value: round(Number(i[metricId]) || metric.reduce([i])),
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
    sku_count: items.length,
    by_category: byCategory,
    by_vertical: byVertical,
    top_skus: topSkus,
    // No date column in the workbook — history is unavailable, not hidden.
    history: null,
  };
}

// The per-metric reducers. `incremental_margin` and the counts are additive
// (bars sum to the headline); `cannibalisation_pct` is a mean (they do not).
const METRICS = {
  incremental_margin: {
    label: "Incremental margin",
    unit: "IDR",
    additive: true,
    reduce: (rows) => sum(rows, "incremental_margin"),
  },
  cannibalisation_pct: {
    label: "Cannibalization %",
    unit: "%",
    additive: false,
    reduce: (rows) => mean(rows.map((r) => Number(r.cannibalisation_pct) || 0)),
  },
  supplier_funding: {
    label: "Supplier funding",
    unit: "IDR",
    additive: true,
    reduce: (rows) => sum(rows, "supplier_funding"),
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

function mean(values) {
  const present = values.map((v) => Number(v) || 0);
  return present.length ? present.reduce((a, b) => a + b, 0) / present.length : 0;
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
    .map(([k, rs]) => ({ key, value: reduce(rs) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}
