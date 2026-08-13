/**
 * Decompose one A1 KPI tile into the breakdowns its drawer shows.
 *
 * A1 is the awkward one of the three, and honestly so. Three of its six
 * headline figures are constants typed into the `A1 Demand Forecasting` sheet
 * — accuracy, trend, seasonality index — which means they cannot be
 * decomposed at all: there is no per-SKU accuracy to sum, only one number per
 * vertical. Those tiles say that rather than splitting a constant across
 * categories and presenting the pieces as findings.
 *
 * `derivation` already carries the measured/typed distinction through the
 * payload; this module is where it stops a drawer inventing detail.
 *
 * WHAT THE MOCKUP DID THAT THIS DOES NOT
 * Its drawer draws a twelve-period history from a seeded random walk. There is
 * no dated source anywhere in this workbook — `derivation.history` has said
 * "unavailable" since A1 was written — so the section says so instead.
 */

export const TOP_SKU_COUNT = 6;

const sum = (rows, key) => rows.reduce((total, row) => total + (row[key] ?? 0), 0);

/**
 * `splittable` is the honest flag. False means the figure is one typed
 * constant per vertical, so a category or store split of it would be a number
 * this board invented.
 */
const METRICS = {
  forecast_next_7d: {
    label: "Forecast next 7 days",
    reduce: (rows) => sum(rows, "forecast_7d"),
    unit: "units",
    splittable: true,
    store: "forecast_7d",
  },
  stockout_risk_skus: {
    label: "Stockout-risk SKUs",
    reduce: (rows) => rows.filter((row) => row.is_stockout_risk).length,
    unit: "count",
    splittable: true,
    // The per-store rows carry a forecast and a SKU count, nothing about
    // position — so there is no per-store reorder figure to show.
    store: null,
  },
  predicted_to_trend: {
    label: "Predicted to trend",
    reduce: (rows) => rows.filter((row) => row.is_trending).length,
    unit: "count",
    splittable: true,
    store: null,
  },
  forecast_accuracy: {
    label: "Forecast accuracy",
    unit: "percent",
    splittable: false,
    typed: true,
  },
  demand_trend: {
    label: "Demand trend",
    unit: "percent",
    splittable: false,
    typed: true,
  },
  seasonality_index: {
    label: "Seasonality index",
    unit: "count",
    splittable: false,
    typed: true,
  },
};

export function drilldownMetric(id) {
  return METRICS[id] ?? null;
}

const TYPED_NOTE =
  "This figure is a constant typed into the A1 sheet, one value per vertical. " +
  "It has no per-SKU basis, so splitting it by category or store would be " +
  "inventing detail the source does not contain.";

/**
 * @param {string} metricId  A key of METRICS.
 * @param {object[]} items   The scoped item rows the headline was built from.
 * @param {object[]} stores  The scoped per-store aggregates.
 * @param {number} total     The headline value, taken from the KPI card so the
 *                           drawer and the tile cannot disagree — necessary
 *                           for the typed constants, which are blended per
 *                           vertical rather than reduced from rows.
 */
export function buildDrilldown(metricId, items, stores, total) {
  const metric = drilldownMetric(metricId);
  if (!metric) return null;

  const base = {
    id: metricId,
    label: metric.label,
    unit: metric.unit,
    splittable: metric.splittable,
    total,
    sku_count: items.length,
    history: null,
  };

  if (!metric.splittable) {
    return {
      ...base,
      typed_note: TYPED_NOTE,
      by_category: [],
      by_store: [],
      top_skus: [],
    };
  }

  const byCategoryId = new Map();
  for (const item of items) {
    if (!byCategoryId.has(item.category_id)) {
      byCategoryId.set(item.category_id, {
        id: item.category_id,
        label: item.category_label,
        rows: [],
      });
    }
    byCategoryId.get(item.category_id).rows.push(item);
  }

  return {
    ...base,
    typed_note: null,
    by_category: [...byCategoryId.values()]
      .map((group) => ({
        id: group.id,
        label: group.label,
        value: metric.reduce(group.rows),
      }))
      .filter((row) => Math.abs(row.value) > 1e-9)
      .sort((a, b) => b.value - a.value),
    by_store: metric.store
      ? [...stores]
          .map((store) => ({
            id: store.store_id,
            label: store.name,
            value: store[metric.store] ?? 0,
          }))
          .filter((row) => Math.abs(row.value) > 1e-9)
          .sort((a, b) => b.value - a.value)
      : [],
    store_unavailable_reason: metric.store
      ? null
      : "The per-store rows carry a forecast and a SKU count only, so this measure has no per-store figure to show.",
    top_skus: items
      .map((item) => ({ item, value: metric.reduce([item]) }))
      .filter((row) => Math.abs(row.value) > 1e-9)
      .sort((a, b) => b.value - a.value)
      .slice(0, TOP_SKU_COUNT)
      .map(({ item, value }) => ({
        id: item.sku_id,
        name: item.name,
        category_name: item.category_label,
        value,
      })),
  };
}
