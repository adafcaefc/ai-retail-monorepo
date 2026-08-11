import {
  CATEGORY_OPTIONS,
  DAY_OF_WEEK_FACTORS,
  DEMAND_SKUS,
  LEGAL_ENTITIES,
  REFERENCE_BASELINE,
  STORES,
} from "./mockDataset.js";

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
const SEASONALITY_OFFSET = 1.14 - weightedAverage(DEMAND_SKUS, "seasonality_raw");

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

function nextSevenDayForecast(rows) {
  return rows.reduce(
    (sum, row) => sum + row.ads_raw * DAY_FACTOR_TOTAL * FORECAST_CALIBRATION,
    0,
  );
}

function calculateMetrics(rows, horizonWeeks) {
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
  );
  const trend = (weightedAverage(rows, "growth_index") + GROWTH_OFFSET - 1) * 100;
  const seasonality = (weightedAverage(rows, "seasonality_raw") + SEASONALITY_OFFSET) * 100;

  return {
    next7: round(nextSevenDayForecast(rows)),
    accuracy: round(accuracy, 1),
    trend: round(trend, 1),
    risk: rows.filter((row) => row.stockout_risk).length,
    trending: rows.filter((row) => row.predicted_to_trend).length,
    seasonality: round(seasonality),
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

export function buildForecastSeries(metrics, grain, horizonWeeks) {
  const config = grainConfig(grain, horizonWeeks);
  const base = metrics.next7 * config.multiplier;
  const history = Array.from({ length: config.history }, (_, index) => {
    const shapeIndex = Math.floor((index / Math.max(1, config.history - 1)) * (HISTORY_SHAPE.length - 1));
    const actual = round(base * HISTORY_SHAPE[shapeIndex]);
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
    const forecast = round(base * curveValue(FORECAST_SHAPE, Math.floor(index / Math.max(1, config.future / horizonWeeks))));
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

function kpiSparkline(value, pattern) {
  return pattern.map((factor) => round(value * factor, value < 100 ? 1 : 0));
}

function signalsFor(row) {
  return row.signals.filter((signal) => signal !== "stable");
}

function periodDays(grain) {
  return { daily: 1, weekly: 7, monthly: 30.4, quarterly: 91.25, yearly: 365 }[grain] || 7;
}

export function buildDemandDashboard(query) {
  const rows = scopeDemandRows(query);
  const metrics = calculateMetrics(rows, query.horizon_weeks);
  const forecastPoints = buildForecastSeries(metrics, query.grain, query.horizon_weeks);
  const confidencePoints = buildForecastSeries(metrics, "weekly", query.horizon_weeks);
  const days = periodDays(query.grain);

  const detailRows = rows
    .map((row) => ({
      sku_id: row.sku_id,
      sku_name: row.sku_name,
      category_id: row.category_id,
      category_label: row.category_label,
      ads_units_per_day: round(row.ads_raw * FORECAST_CALIBRATION, 1),
      forecast_units: round(row.ads_raw * FORECAST_CALIBRATION * days * 1.007),
      trend_pct: round((row.growth_index + GROWTH_OFFSET - 1) * 100, 1),
      signals: signalsFor(row),
      supply_state: row.stockout_risk ? (row.risk_score % 3 === 0 ? "Stockout" : "Low") : "Healthy",
    }))
    .sort((left, right) => right.forecast_units - left.forecast_units);

  const trendingItems = rows
    .filter((row) => row.predicted_to_trend)
    .map((row) => ({
      sku_id: row.sku_id,
      sku_name: row.sku_name,
      predicted_uplift_pct: round(
        Math.max(0, (row.growth_index - 1) * 100) + (row.signals.includes("viral") ? 18 : 0),
        1,
      ),
      signals: signalsFor(row),
      ads_units_per_day: round(row.ads_raw * FORECAST_CALIBRATION, 1),
    }))
    .sort((left, right) => right.predicted_uplift_pct - left.predicted_uplift_pct)
    .slice(0, 8);

  return {
    metrics,
    forecastPoints,
    confidencePoints,
    detailRows,
    trendingItems,
    options: filterOptions(query),
  };
}

export { FORECAST_CALIBRATION };

