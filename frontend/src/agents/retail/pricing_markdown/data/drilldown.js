/**
 * KPI decomposition for the drill-down drawer — mirrors
 * promotion_effectiveness/data/drilldown.js. One tile opens into a drawer
 * that splits its headline by category and by vertical, and names the
 * largest contributing SKUs.
 */

import { BASELINE_LEVERS, KPI_FORMULAS } from "./contract.js";
import { depthWeightedAvgPct, mean } from "./selectors.js";

export const TOP_SKU_COUNT = 6;

/** @param {string} id */
export function drilldownMetric(id) {
  const metric = METRICS[id];
  if (!metric) {
    throw new Error(`Pricing & Markdown KPI ${id} has no drilldown metric definition`);
  }
  return metric;
}

export function drillableMetrics() {
  return Object.keys(METRICS);
}

/**
 * @param {string} metricId
 * @param {object[]} items  Markdown candidates in scope.
 * @param {object} [context]  Extra inputs a reducer may need (e.g. the
 *   markdown lever), passed through unchanged to every `reduce` call. The
 *   three original (additive) reducers ignore it. `context.stores` (optional,
 *   `filter_options.stores` shape: `{ value, label }`) labels the by-store
 *   breakdown below.
 */
export function buildDrilldown(metricId, items, context = {}) {
  const metric = drilldownMetric(metricId);
  const digits = metric.digits ?? 0;
  const total = round(metric.reduce(items, context), digits);

  const byCategory = topGroups(items, "category_id", (rows) => round(metric.reduce(rows, context), digits)).map(
    (g) => ({
      category_id: g.key,
      label: labelFor(items, g.key, "category_id", "category_label"),
      value: g.value,
    }),
  );

  const byVertical = topGroups(items, "vertical_id", (rows) => round(metric.reduce(rows, context), digits)).map(
    (g) => ({
      vertical_id: g.key,
      label: g.key,
      value: g.value,
    }),
  );

  // Every drillable metric except comp_idx is built from `items` at the same
  // (SKU, store) grain by_category/by_vertical already group above, so the
  // store split reuses the identical topGroups call. comp_idx's own `items`
  // is `sku_index` (one row per distinct SKU, deliberately deduped across a
  // SKU's stores -- see computeKpis in selectors.js), which carries no
  // store_id at all: a per-store split there would either be fabricated
  // (an arbitrary single store per SKU) or meaningless (comp_idx is a
  // SKU_Master attribute, constant across a SKU's own stores), so it is
  // omitted with a reason instead -- same stance replenishment's drilldown
  // takes for the metrics its per-store grid has no column for.
  const storeLabels = new Map((context.stores ?? []).map((s) => [s.value, s.label]));
  const byStore = metric.store
    ? topGroups(items, "store_id", (rows) => round(metric.reduce(rows, context), digits)).map((g) => ({
        store_id: g.key,
        label: storeLabels.get(g.key) ?? g.key,
        value: g.value,
      }))
    : [];

  // Named SKUs, not (SKU, store) rows: `items` is one row per ENGINE_STORE
  // record, so a single SKU present at several candidate stores is grouped
  // back to one entry here, summed across its rows — the same way
  // by_category/by_vertical above already group many rows into one label.
  // Without this, "Top contributing SKUs" could fill its six slots with the
  // same SKU repeated at different stores.
  const topSkus = topGroups(
    items,
    "sku_id",
    (rows) => round(metric.reduce(rows, context), digits),
    TOP_SKU_COUNT,
  ).map((g) => ({
    sku_id: g.key,
    name: labelFor(items, g.key, "sku_id", "name"),
    vertical_id: labelFor(items, g.key, "sku_id", "vertical_id"),
    category_label: labelFor(items, g.key, "sku_id", "category_label"),
    value: g.value,
  }));

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
    by_store: byStore,
    // Null rather than fabricated, and the drawer names the reason. Same
    // stance replenishment's drilldown takes for its store-less metrics.
    store_unavailable_reason: metric.store ? null : metric.storeUnavailableReason,
    top_skus: topSkus,
    // No date column in the workbook — history is unavailable, not hidden.
    history: null,
  };
}

const METRICS = {
  markdown_candidates: {
    label: "Markdown candidates",
    unit: "count",
    additive: true,
    store: true,
    reduce: (rows) => rows.length,
  },
  at_risk_value: {
    label: "At-risk value",
    unit: "IDR",
    additive: true,
    store: true,
    // at_risk_gross, not each row's own at_risk_value (f12) -- same basis
    // as computeKpis in selectors.js, so opening this drawer from the
    // headline tile totals to the number the tile itself just showed.
    reduce: (rows) => sum(rows, "at_risk_gross"),
  },
  recoverable_value: {
    label: "Recoverable value",
    unit: "IDR",
    additive: true,
    store: true,
    reduce: (rows) => sum(rows, "recoverable_value"),
  },
  write_off_value: {
    label: "Write-off value",
    unit: "IDR",
    additive: true,
    store: true,
    reduce: (rows) => sum(rows, "at_risk_gross") - sum(rows, "recoverable_value"),
  },
  // A mean cannot be split across categories/verticals and added back up —
  // each breakdown row below is that group's own average, not a share of the
  // headline. See PricingKpiDrilldown.jsx's `additive` subtitle.
  avg_depth_pct: {
    label: "Avg depth %",
    unit: "percent",
    additive: false,
    digits: 2,
    store: true,
    // Same at-risk-value-weighted formula as the KPI tile (selectors.js's
    // `computeKpis`), re-run on whatever subset of rows this call is scoped
    // to, at the lever the tile itself was showing when the drawer opened.
    reduce: (rows, { markdownLever = BASELINE_LEVERS.markdown } = {}) => depthWeightedAvgPct(rows, markdownLever),
  },
  comp_idx: {
    label: "Comp idx",
    unit: "index",
    additive: false,
    digits: 1,
    // comp_idx's own `items` is sku_index (one row per distinct SKU, no
    // store_id) — see the note above buildDrilldown's byStore.
    store: false,
    storeUnavailableReason:
      "Comp idx is a per-SKU competitiveness figure from SKU_Master with no store dimension, so this measure has no per-store figure to show.",
    reduce: (rows) => mean(rows.map((r) => r.comp_idx)),
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
