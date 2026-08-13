/**
 * Decompose one A3 KPI tile into the breakdowns its drawer shows.
 *
 * Same shape and the same rules as the Inventory Risk drilldown: one reducer
 * per metric, because "contribute" is not one operation. `order_value_cost`
 * sums a column, `skus_to_reorder` counts rows, and `fill_rate_pct` is a
 * proportion that cannot be summed across groups at all.
 *
 * WHAT THE MOCKUP DID THAT THIS DOES NOT
 * Its drawer draws a twelve-period history from a seeded random walk and
 * allocates the per-store panel from `charCodeAt` and a store health factor.
 * Neither is a measurement. This board's per-store figures come from the
 * per-store rows the workbook actually carries (`stores`, aggregated from
 * ENGINE_STORE), and there is no history to draw — so the section says so.
 */

/** How many rows the "top contributing SKUs" list shows. */
export const TOP_SKU_COUNT = 6;

const sum = (rows, key) => rows.reduce((total, row) => total + (row[key] ?? 0), 0);

/**
 * `store` names the field a store row contributes to this metric, or null
 * when the per-store grid cannot answer it.
 *
 * Two of the six are null on purpose. The per-store grid prices at selling
 * price and carries no trade price, so cost and the vendor saving simply do
 * not exist per store — and an allocated guess would be exactly the invention
 * this module refuses elsewhere.
 */
const METRICS = {
  skus_to_reorder: {
    label: "SKUs to reorder",
    reduce: (rows) => rows.filter((row) => row.is_reorder).length,
    unit: "count",
    additive: true,
    store: "reorder_count",
  },
  order_units: {
    label: "Order units",
    reduce: (rows) => sum(rows, "order_qty_sales"),
    unit: "units",
    additive: true,
    store: "order_units",
  },
  order_value_cost: {
    label: "Order value at cost",
    reduce: (rows) => sum(rows, "order_value_cost"),
    unit: "money",
    additive: true,
    // The per-store grid has no trade price. See the note above.
    store: null,
  },
  order_value_retail: {
    label: "Order value at retail",
    reduce: (rows) => sum(rows, "order_value_retail"),
    unit: "money",
    additive: true,
    store: "order_value_retail",
  },
  fill_rate_pct: {
    label: "Fill rate",
    reduce: (rows) =>
      rows.length
        ? (rows.filter((row) => !row.is_reorder).length / rows.length) * 100
        : 0,
    unit: "percent",
    // A proportion. Each group's own rate, never a total.
    additive: false,
    store: null,
  },
  recoverable_saving: {
    label: "Recoverable",
    reduce: (rows) => sum(rows, "saving_vs_designated"),
    unit: "money",
    additive: true,
    // Sourcing is a chain-level decision; the grid holds no vendor split.
    store: null,
  },
};

export function drilldownMetric(id) {
  return METRICS[id] ?? null;
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
 * @param {string} metricId  A key of METRICS.
 * @param {object[]} lines   The scoped order lines the headline was built from.
 * @param {object[]} stores  The scoped per-store aggregates.
 */
export function buildDrilldown(metricId, lines, stores) {
  const metric = drilldownMetric(metricId);
  if (!metric) return null;

  const byCategoryId = new Map();
  for (const line of lines) {
    if (!byCategoryId.has(line.category_id)) {
      byCategoryId.set(line.category_id, {
        id: line.category_id,
        label: line.category_label,
        rows: [],
      });
    }
    byCategoryId.get(line.category_id).rows.push(line);
  }

  /*
   * The store split reads the pre-aggregated store rows rather than
   * re-deriving anything, because A3's per-store figures are ENGINE_STORE's
   * own columns — already summed by the fixture builder and the backend
   * alike. A metric with no per-store column returns an empty list, and the
   * drawer explains the gap instead of allocating one.
   */
  const byStore = metric.store
    ? [...stores]
        .map((store) => ({
          id: store.store_id,
          label: store.name,
          value: store[metric.store] ?? 0,
        }))
        .filter((row) => Math.abs(row.value) > 1e-9)
        .sort((a, b) => b.value - a.value)
    : [];

  const topSkus = lines
    .map((line) => ({ line, value: metric.reduce([line]) }))
    .filter((row) => Math.abs(row.value) > 1e-9)
    .sort((a, b) => b.value - a.value)
    .slice(0, TOP_SKU_COUNT)
    .map(({ line, value }) => ({
      id: line.sku_id,
      name: line.name,
      category_name: line.category_label,
      route: line.route,
      value,
    }));

  return {
    id: metricId,
    label: metric.label,
    unit: metric.unit,
    additive: metric.additive,
    total: metric.reduce(lines),
    line_count: lines.length,
    by_category: ranked([...byCategoryId.values()], metric.reduce),
    by_store: byStore,
    // Null rather than fabricated, and the drawer names the reason. Same
    // stance the whole Retail module takes: no dated source, no trend line.
    store_unavailable_reason: metric.store
      ? null
      : "The per-store grid prices at selling price and holds no vendor split, so this measure has no per-store figure to show.",
    top_skus: topSkus,
    history: null,
  };
}
