import {
  CATEGORY_OPTIONS,
  DAY_OF_WEEK_FACTORS,
  DEMAND_SKUS,
  LEGAL_ENTITIES,
  REFERENCE_BASELINE,
  SEASONALITY_BY_ENTITY,
  STORES,
  STORE_CLUSTERS,
} from "./mockDataset.js";
import { DEFAULT_DEMAND_LEVERS, normalizeDemandLevers } from "./contract.js";

const DAY_FACTOR_TOTAL = DAY_OF_WEEK_FACTORS.reduce((sum, value) => sum + value, 0);
const RAW_FORECAST_TOTAL = DEMAND_SKUS.reduce(
  (sum, row) => sum + row.ads_raw * DAY_FACTOR_TOTAL,
  0,
);
const FORECAST_CALIBRATION = REFERENCE_BASELINE.forecast_next_7d / RAW_FORECAST_TOTAL;

function weightedAverage(rows, field, weightField = "ads_raw") {
  const weight = rows.reduce((sum, row) => sum + row[weightField], 0);
  if (!weight) return 0;
  return rows.reduce((sum, row) => sum + row[field] * row[weightField], 0) / weight;
}

const MAPE_OFFSET = 7 - weightedAverage(DEMAND_SKUS, "mape_raw");
const GROWTH_OFFSET = 1.048 - weightedAverage(DEMAND_SKUS, "growth_index");

function round(value, digits = 0) {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

export function scopeDemandRows(query) {
  const needle = query.sku.toLowerCase();
  return DEMAND_SKUS.filter((row) => {
    if (query.legal_entity_id !== "ALL" && row.legal_entity_id !== query.legal_entity_id) return false;
    if (query.category_group !== "ALL" && row.category_id !== query.category_group) return false;
    if (query.store_id !== "ALL" && row.store_id !== query.store_id) return false;
    if (needle && !`${row.sku_id} ${row.sku_name}`.toLowerCase().includes(needle)) return false;
    return true;
  });
}

export function filterOptions(query) {
  const entity = query.legal_entity_id;
  return {
    legal_entities: LEGAL_ENTITIES,
    categories: CATEGORY_OPTIONS
      .filter((option) => entity === "ALL" || option.legal_entity_id === entity)
      .map(({ value, label }) => ({ value, label })),
    stores: STORES
      .filter((option) => entity === "ALL" || option.legal_entity_id === entity)
      .map(({ value, label }) => ({ value, label })),
  };
}

function scenarioForecastFactor(row, levers) {
  const demand = 1 + levers.demand / 100;
  const promo = row.signals.includes("promo")
    ? 1 + ((levers.promo - DEFAULT_DEMAND_LEVERS.promo) / 100) * 0.45
    : 1;
  const markdown = row.stockout_risk
    ? 1 + ((levers.markdown - DEFAULT_DEMAND_LEVERS.markdown) / 100) * 0.08
    : 1;
  return Math.max(0.2, demand * promo * markdown);
}

function rowNextSevenDayForecast(row, levers) {
  return row.ads_raw * DAY_FACTOR_TOTAL * FORECAST_CALIBRATION * scenarioForecastFactor(row, levers);
}

function nextSevenDayForecast(rows, levers) {
  return rows.reduce(
    (sum, row) => sum + rowNextSevenDayForecast(row, levers),
    0,
  );
}

function scenarioRiskLimit(levers) {
  return Math.min(DEMAND_SKUS.length, Math.max(0, Math.round(
    REFERENCE_BASELINE.stockout_risk_skus
      + levers.demand * 1.15
      + (levers.promo - DEFAULT_DEMAND_LEVERS.promo) * 0.35
      + levers.lead * 7
      + levers.safety * 5
      - levers.inbound * 0.48
      - (levers.markdown - DEFAULT_DEMAND_LEVERS.markdown) * 0.12,
  )));
}

function scenarioTrendLimit(levers) {
  return Math.min(DEMAND_SKUS.length, Math.max(0, Math.round(
    REFERENCE_BASELINE.predicted_to_trend
      + levers.demand * 0.35
      + (levers.promo - DEFAULT_DEMAND_LEVERS.promo) * 0.42
      + (levers.markdown - DEFAULT_DEMAND_LEVERS.markdown) * 0.08,
  )));
}

function rowAtRisk(row, levers) {
  return row.risk_rank < scenarioRiskLimit(levers);
}

function rowTrending(row, levers) {
  return row.trend_rank < scenarioTrendLimit(levers);
}

function calculateMetrics(
  rows,
  horizonWeeks,
  seasonalityIndex,
  inputLevers = DEFAULT_DEMAND_LEVERS,
) {
  const levers = normalizeDemandLevers(inputLevers);
  if (!rows.length) {
    return {
      next7: 0,
      accuracy: 0,
      trend: 0,
      risk: 0,
      trending: 0,
      seasonality: 0,
    };
  }

  const accuracy = 100 - (
    weightedAverage(rows, "mape_raw") + MAPE_OFFSET + Math.max(0, horizonWeeks - 8) * 0.22
    + Math.abs(levers.demand) * 0.035
    + Math.abs(levers.promo - DEFAULT_DEMAND_LEVERS.promo) * 0.018
    + Math.max(0, levers.lead) * 0.06
  ) + Math.max(0, levers.inbound) * 0.004;
  const scenarioLift = nextSevenDayForecast(rows, levers) / Math.max(1, nextSevenDayForecast(rows, DEFAULT_DEMAND_LEVERS));
  const trend = ((weightedAverage(rows, "growth_index") + GROWTH_OFFSET) * scenarioLift - 1) * 100;
  return {
    next7: round(nextSevenDayForecast(rows, levers)),
    accuracy: round(accuracy, 1),
    trend: round(trend, 1),
    risk: rows.filter((row) => rowAtRisk(row, levers)).length,
    trending: rows.filter((row) => rowTrending(row, levers)).length,
    seasonality: seasonalityIndex,
  };
}

const HISTORY_SHAPE = [
  0.87, 0.9, 0.885, 0.925, 0.94, 0.955, 0.935, 0.975, 0.99, 1.005, 0.985, 1.015,
];
const FORECAST_SHAPE = [1.02, 1.035, 1.055, 1.045, 1.075, 1.09, 1.11, 1.105, 1.13, 1.145, 1.16, 1.18, 1.19, 1.21, 1.23, 1.245];

function grainConfig(grain, horizonWeeks) {
  const configs = {
    daily: { history: 28, future: horizonWeeks * 7, multiplier: 1 / 7, prefix: "D" },
    weekly: { history: 12, future: horizonWeeks, multiplier: 1, prefix: "W" },
    monthly: { history: 12, future: Math.max(1, Math.ceil(horizonWeeks / 4)), multiplier: 4.345, prefix: "M" },
    quarterly: { history: 8, future: Math.max(1, Math.ceil(horizonWeeks / 13)), multiplier: 13.035, prefix: "Q" },
    yearly: { history: 5, future: 1, multiplier: 52.14, prefix: "Y" },
  };
  return configs[grain] || configs.weekly;
}

function curveValue(shape, index) {
  if (index < shape.length) return shape[index];
  return shape[shape.length - 1] + (index - shape.length + 1) * 0.012;
}

export function buildForecastSeries(
  forecastMetrics,
  grain,
  horizonWeeks,
  actualMetrics = forecastMetrics,
) {
  const config = grainConfig(grain, horizonWeeks);
  const actualBase = actualMetrics.next7 * config.multiplier;
  const forecastBase = forecastMetrics.next7 * config.multiplier;
  const history = Array.from({ length: config.history }, (_, index) => {
    const shapeIndex = Math.floor((index / Math.max(1, config.history - 1)) * (HISTORY_SHAPE.length - 1));
    const actual = round(actualBase * HISTORY_SHAPE[shapeIndex]);
    return {
      key: `${config.prefix}-${config.history - index}`,
      label: `${config.prefix}-${config.history - index}`,
      actual,
      forecast: null,
      confidence_low: null,
      confidence_high: null,
    };
  });
  const future = Array.from({ length: config.future }, (_, index) => {
    const forecast = round(forecastBase * curveValue(FORECAST_SHAPE, Math.floor(index / Math.max(1, config.future / horizonWeeks))));
    return {
      key: `${config.prefix}+${index + 1}`,
      label: `${config.prefix}+${index + 1}`,
      actual: null,
      forecast,
      confidence_low: round(forecast * 0.88),
      confidence_high: round(forecast * 1.12),
    };
  });
  const anchor = history[history.length - 1];
  if (future.length && anchor) future[0] = { ...future[0], actual: anchor.actual };
  return [...history, ...future];
}

function signalsFor(row) {
  return row.signals.filter((signal) => signal !== "stable");
}

function reconcileGroups(groupedRows, target) {
  const values = [...groupedRows.values()].map((group) => ({
    ...group,
    floor: Math.floor(group.raw),
    remainder: group.raw - Math.floor(group.raw),
  }));
  let remaining = target - values.reduce((sum, group) => sum + group.floor, 0);
  values.sort((left, right) => right.remainder - left.remainder || left.id.localeCompare(right.id));
  for (let index = 0; remaining > 0 && values.length; index += 1, remaining -= 1) {
    values[index % values.length].floor += 1;
  }
  values.sort((left, right) => right.floor - left.floor || left.label.localeCompare(right.label));
  return values.map(({ floor, remainder: _remainder, raw: _raw, ...group }) => ({
    ...group,
    forecast_units: floor,
    share_pct: target ? round((floor / target) * 100, 1) : 0,
  }));
}

function aggregateRows(rows, keyFor, labelFor, target, levers, extraFor = () => ({})) {
  const groups = new Map();
  for (const row of rows) {
    const id = keyFor(row);
    const current = groups.get(id) || {
      id,
      label: labelFor(row),
      raw: 0,
      row_count: 0,
      store_ids: new Set(),
      ...extraFor(row),
    };
    current.raw += rowNextSevenDayForecast(row, levers);
    current.row_count += 1;
    current.store_ids.add(row.store_id);
    groups.set(id, current);
  }
  for (const group of groups.values()) {
    group.store_count = group.store_ids.size;
    delete group.store_ids;
  }
  return reconcileGroups(groups, target);
}

function buildSeasonality(rows) {
  const monthLabels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  if (!rows.length) {
    return monthLabels.map((month, index) => ({ month, index: 0, current: index === 6 }));
  }

  /*
   * One seasonality source feeds both the chart and KPI. For a mixed scope,
   * entity curves are weighted by the scoped rows' baseline seven-day demand
   * (ads_raw is sufficient because the common DOW/calibration factors cancel).
   * A single-entity/category/store/SKU scope therefore resolves naturally to
   * that entity's curve, while ALL is a deterministic demand-weighted chain.
   */
  const weights = new Map();
  for (const row of rows) {
    weights.set(
      row.legal_entity_id,
      (weights.get(row.legal_entity_id) || 0) + row.ads_raw,
    );
  }
  const totalWeight = [...weights.values()].reduce((sum, value) => sum + value, 0);

  return monthLabels.map((month, index) => {
    const weightedIndex = [...weights.entries()].reduce((sum, [entityId, weight]) => (
      sum + (SEASONALITY_BY_ENTITY[entityId]?.[index] || 1) * weight
    ), 0) / totalWeight;
    return { month, index: round(weightedIndex * 100), current: index === 6 };
  });
}

function buildDimensions(rows, metrics, levers, seasonality) {
  const category = aggregateRows(
    rows,
    (row) => row.category_id,
    (row) => row.category_label,
    metrics.next7,
    levers,
  );
  const storesById = new Map(STORES.map((store) => [store.value, store]));
  const stores = aggregateRows(
    rows,
    (row) => row.store_id,
    (row) => storesById.get(row.store_id)?.label || row.store_id,
    metrics.next7,
    levers,
    (row) => ({ legal_entity_id: row.legal_entity_id, cluster: row.cluster }),
  );
  const clusters = aggregateRows(
    rows,
    (row) => row.cluster,
    (row) => row.cluster,
    metrics.next7,
    levers,
  );
  const legalEntities = aggregateRows(
    rows,
    (row) => row.legal_entity_id,
    (row) => LEGAL_ENTITIES.find((entity) => entity.value === row.legal_entity_id)?.label || row.legal_entity_id,
    metrics.next7,
    levers,
  );

  return {
    categories: category,
    stores,
    clusters: STORE_CLUSTERS.map((cluster) =>
      clusters.find((row) => row.id === cluster) || {
        id: cluster,
        label: cluster,
        forecast_units: 0,
        share_pct: 0,
        store_count: 0,
        row_count: 0,
      },
    ),
    legal_entities: legalEntities,
    seasonality,
    chain_total: metrics.next7,
  };
}

function periodDays(grain) {
  return { daily: 1, weekly: 7, monthly: 30.4, quarterly: 91.25, yearly: 365 }[grain] || 7;
}

export function buildDemandDashboard(query, inputLevers = DEFAULT_DEMAND_LEVERS) {
  const levers = normalizeDemandLevers(inputLevers);
  const rows = scopeDemandRows(query);
  const seasonality = buildSeasonality(rows);
  const seasonalityIndex = seasonality.find((point) => point.current)?.index || 0;
  const baselineMetrics = calculateMetrics(
    rows,
    query.horizon_weeks,
    seasonalityIndex,
    DEFAULT_DEMAND_LEVERS,
  );
  const metrics = calculateMetrics(rows, query.horizon_weeks, seasonalityIndex, levers);
  const forecastPoints = buildForecastSeries(
    metrics,
    query.grain,
    query.horizon_weeks,
    baselineMetrics,
  );
  const confidencePoints = buildForecastSeries(
    metrics,
    "weekly",
    query.horizon_weeks,
    baselineMetrics,
  );
  const baselineForecastPoints = buildForecastSeries(baselineMetrics, query.grain, query.horizon_weeks);
  const days = periodDays(query.grain);

  const detailRows = rows
    .map((row) => ({
      sku_id: row.sku_id,
      sku_name: row.sku_name,
      category_id: row.category_id,
      category_label: row.category_label,
      ads_units_per_day: round(row.ads_raw * FORECAST_CALIBRATION * scenarioForecastFactor(row, levers), 1),
      forecast_7d_units: round(rowNextSevenDayForecast(row, levers), 0),
      forecast_units: round(rowNextSevenDayForecast(row, levers) * (days / 7), 0),
      trend_pct: round(((row.growth_index + GROWTH_OFFSET) * scenarioForecastFactor(row, levers) - 1) * 100, 1),
      signals: signalsFor(row),
      supply_state: rowAtRisk(row, levers) ? (row.risk_score % 3 === 0 ? "Stockout" : "Low") : "Healthy",
    }))
    .sort((left, right) => right.forecast_units - left.forecast_units);
  const detailTarget = round(metrics.next7 * (days / 7));
  const detailDifference = detailTarget - detailRows.reduce((sum, row) => sum + row.forecast_units, 0);
  if (detailRows.length && detailDifference) {
    detailRows[0].forecast_units += detailDifference;
  }

  const trendingItems = rows
    .filter((row) => rowTrending(row, levers))
    .map((row) => ({
      sku_id: row.sku_id,
      sku_name: row.sku_name,
      predicted_uplift_pct: round(
        Math.max(0, ((row.growth_index + GROWTH_OFFSET) * scenarioForecastFactor(row, levers) - 1) * 100)
          + (row.signals.includes("viral") ? 18 : 0),
        1,
      ),
      signals: signalsFor(row),
      ads_units_per_day: round(row.ads_raw * FORECAST_CALIBRATION * scenarioForecastFactor(row, levers), 1),
    }))
    .sort((left, right) => right.predicted_uplift_pct - left.predicted_uplift_pct)
    .slice(0, 8);

  return {
    metrics,
    baselineMetrics,
    forecastPoints,
    confidencePoints,
    baselineForecastPoints,
    detailRows,
    trendingItems,
    dimensions: buildDimensions(rows, metrics, levers, seasonality),
    detailForecastTotal: detailTarget,
    options: filterOptions(query),
  };
}

export { FORECAST_CALIBRATION };
