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
 * per-store panel here is real: the rows ARE the 16,000 ENGINE_STORE rows, so a
 * store's bar is that store's own, grouped rather than derived or allocated.
 */

/** How many rows the "top contributing SKUs" list shows. */
export const TOP_SKU_COUNT = 6;

/**
 * Distinct SKUs among the rows a predicate accepts — the same rule the tiles
 * follow (see `selectors.js`'s `computeKpis`). Counting rows here would make
 * every bar disagree with the headline it decomposes, by roughly 10x.
 */
function countSkus(rows, predicate) {
  const seen = new Set();
  for (const row of rows) {
    if (predicate(row)) seen.add(row.sku_id);
  }
  return seen.size;
}

/**
 * One entry per KPI tile.
 *
 * `additive` is the honest bit: a mean cannot be split across categories and
 * added back up, so the drawer labels those breakdowns as averages rather than
 * letting a reader sum the bars and wonder why they miss the headline.
 *
 * It stays true for the counts, because a SKU belongs to exactly one category
 * and one vertical, so those bars still sum to the tile. The STORE split is
 * the exception this grain forces — a SKU slow-moving at six stores appears in
 * six bars — which is the same gross-versus-net caveat the board already
 * carries for its store charts.
 */
const METRICS = {
  stockout_skus: {
    label: "Stockout SKUs",
    reduce: (rows) => countSkus(rows, (row) => row.state === "Stockout"),
    unit: "count",
    additive: true,
  },
  stockout_risk_skus: {
    label: "Stockout-risk SKUs",
    reduce: (rows) => countSkus(rows, (row) => row.is_stockout_risk),
    unit: "count",
    additive: true,
  },
  overstock_skus: {
    label: "Overstock SKUs",
    reduce: (rows) => countSkus(rows, (row) => row.is_overstock),
    unit: "count",
    additive: true,
  },
  expiry_units: {
    label: "Expiry-risk units",
    reduce: (rows) =>
      rows.reduce(
        (total, row) => (row.state === "Expiry" ? total + row.expiry_units : total),
        0,
      ),
    unit: "units",
    additive: true,
  },
  slow_mover_skus: {
    label: "Slow-moving SKUs",
    reduce: (rows) => countSkus(rows, (row) => row.is_slow_mover),
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
 * @param {object[]} [options.allItems] Unscoped items for the store split, so a
 *   store's bar covers its whole shelf rather than the current filter.
 */
export function buildDrilldown(metricId, items, stores, options = {}) {
  const metric = drilldownMetric(metricId);
  if (!metric) return null;

  const { allItems = items } = options;

  const byCategory = ranked(
    groupBy(items, "category_id", (row) => row.category_name),
    metric.reduce,
  );

  /*
   * The store split is READ, not derived.
   *
   * Rows arrive at ENGINE_STORE grain, so a store's bar is just its own rows
   * grouped by `store_id`. This used to regenerate every store's shelf with
   * `atStore` and a full engine pass — ~16,000 evaluations per click — to
   * rebuild exactly what the fixture now ships.
   */
  const rowsByStore = new Map();
  for (const item of allItems) {
    const bucket = rowsByStore.get(item.store_id);
    if (bucket) bucket.push(item);
    else rowsByStore.set(item.store_id, [item]);
  }
  const byStore = ranked(
    stores.map((store) => ({
      id: store.store_id,
      label: store.name,
      rows: rowsByStore.get(store.store_id) ?? [],
    })),
    metric.reduce,
  );

  /*
   * Ranked by SKU, not by row. A SKU sits in ~20 stores, so ranking rows would
   * fill all six slots with one SKU's worst stores and call it a top-six.
   * Values are summed across the SKU's rows, matching how the tile above
   * counts SKUs and sums money.
   */
  const bySku = new Map();
  for (const item of items) {
    const existing = bySku.get(item.sku_id);
    const value = metric.reduce([item]);
    if (existing) {
      existing.value += value;
      existing.stores += 1;
    } else {
      bySku.set(item.sku_id, { item, value, stores: 1 });
    }
  }
  const topSkus = [...bySku.values()]
    .filter((row) => Math.abs(row.value) > 1e-9)
    .sort((a, b) => b.value - a.value)
    .slice(0, TOP_SKU_COUNT)
    .map(({ item, value, stores: storeCount }) => ({
      id: item.sku_id,
      name: item.name,
      category_name: item.category_name,
      state: item.state,
      store_count: storeCount,
      value,
    }));

  return {
    id: metricId,
    label: metric.label,
    unit: metric.unit,
    additive: metric.additive,
    total: metric.reduce(items),
    // DISTINCT SKUs, not `items.length` — the drawer prints this beside a
    // tile that counts SKUs, and rows would read ~20x higher.
    sku_count: countSkus(items, () => true),
    row_count: items.length,
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
