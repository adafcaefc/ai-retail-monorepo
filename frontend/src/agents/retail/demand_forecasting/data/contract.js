export const DEMAND_AGENT_ID = "retail.demand_forecasting";

export const DEMAND_GRAINS = [
  "daily",
  "weekly",
  "monthly",
  "quarterly",
  "yearly",
];

export const DEMAND_HORIZONS = [4, 8, 12, 16];

export const DEFAULT_DEMAND_QUERY = Object.freeze({
  legal_entity_id: "ALL",
  category_group: "ALL",
  store_id: "ALL",
  sku: "",
  grain: "weekly",
  horizon_weeks: 8,
  detail_offset: 0,
  detail_limit: 100,
});

/** @typedef {typeof DEFAULT_DEMAND_QUERY} DemandDashboardQuery */

function finiteNumber(value, fallback = null) {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function boundedInteger(value, fallback, min, max) {
  const numeric = Math.trunc(finiteNumber(value, fallback));
  return Math.min(max, Math.max(min, numeric));
}

export function normalizeDemandQuery(query = {}) {
  const horizon = Number(query.horizon_weeks);
  const grain = String(query.grain || "").toLowerCase();

  return {
    legal_entity_id: String(query.legal_entity_id || "ALL"),
    category_group: String(query.category_group || "ALL"),
    store_id: String(query.store_id || "ALL"),
    sku: String(query.sku || "").trim().slice(0, 120),
    grain: DEMAND_GRAINS.includes(grain) ? grain : "weekly",
    horizon_weeks: DEMAND_HORIZONS.includes(horizon) ? horizon : 8,
    detail_offset: boundedInteger(query.detail_offset, 0, 0, 1000000),
    detail_limit: boundedInteger(query.detail_limit, 100, 1, 100),
  };
}

function normalizeOptions(options) {
  return (Array.isArray(options) ? options : [])
    .filter((option) => option && option.value != null)
    .map((option) => ({
      value: String(option.value),
      label: String(option.label ?? option.value),
    }));
}

function normalizePoint(point, index) {
  return {
    key: String(point?.key ?? index),
    label: String(point?.label ?? point?.key ?? index),
    actual: finiteNumber(point?.actual),
    forecast: finiteNumber(point?.forecast),
    confidence_low: finiteNumber(point?.confidence_low),
    confidence_high: finiteNumber(point?.confidence_high),
  };
}

function normalizeSeries(series = {}) {
  return {
    grain: DEMAND_GRAINS.includes(series.grain) ? series.grain : "weekly",
    history_count: boundedInteger(series.history_count, 0, 0, 1000),
    horizon_weeks: boundedInteger(series.horizon_weeks, 8, 1, 52),
    horizon_label: String(series.horizon_label || ""),
    points: (Array.isArray(series.points) ? series.points : []).map(normalizePoint),
    summary: (Array.isArray(series.summary) ? series.summary : []).map((item) => ({
      id: String(item?.id || ""),
      label: String(item?.label || ""),
      value: typeof item?.value === "string" ? item.value : finiteNumber(item?.value),
      unit: item?.unit == null ? null : String(item.unit),
    })),
  };
}

/**
 * Normalize both mock and API payloads at the feature boundary. Presentation
 * components only receive this shape and never need to know which provider ran.
 */
export function normalizeDemandDashboard(payload) {
  if (!payload || payload.agent !== DEMAND_AGENT_ID) {
    throw new Error("Demand Forecasting returned an invalid dashboard contract.");
  }

  const scope = normalizeDemandQuery(payload.scope);
  const forecast = normalizeSeries(payload.forecast);
  if (!forecast.points.length) {
    throw new Error("Demand Forecasting returned no forecast series.");
  }

  return {
    schema_version: boundedInteger(payload.schema_version, 1, 1, 100),
    agent: DEMAND_AGENT_ID,
    as_of: String(payload.as_of || ""),
    is_mock: Boolean(payload.is_mock),
    note: String(payload.note || ""),
    scope,
    filter_options: {
      legal_entities: normalizeOptions(payload.filter_options?.legal_entities),
      categories: normalizeOptions(payload.filter_options?.categories),
      stores: normalizeOptions(payload.filter_options?.stores),
      grains: (payload.filter_options?.grains || DEMAND_GRAINS).filter((grain) =>
        DEMAND_GRAINS.includes(grain),
      ),
      horizons_weeks: (payload.filter_options?.horizons_weeks || DEMAND_HORIZONS)
        .map(Number)
        .filter((horizon) => DEMAND_HORIZONS.includes(horizon)),
    },
    kpis: (Array.isArray(payload.kpis) ? payload.kpis : []).map((kpi) => ({
      id: String(kpi?.id || ""),
      label: String(kpi?.label || ""),
      value: finiteNumber(kpi?.value, 0),
      unit: kpi?.unit == null ? null : String(kpi.unit),
      comparison_label: String(kpi?.comparison_label || ""),
      direction: ["up", "down", "flat"].includes(kpi?.direction)
        ? kpi.direction
        : "flat",
      status: ["good", "warn", "bad", "neutral"].includes(kpi?.status)
        ? kpi.status
        : "neutral",
      sparkline: (Array.isArray(kpi?.sparkline) ? kpi.sparkline : [])
        .map((value) => finiteNumber(value))
        .filter((value) => value != null),
    })),
    forecast,
    confidence: normalizeSeries(payload.confidence || payload.forecast),
    trending_items: (Array.isArray(payload.trending_items)
      ? payload.trending_items
      : []).map((item) => ({
      sku_id: String(item?.sku_id || ""),
      sku_name: String(item?.sku_name || ""),
      predicted_uplift_pct: finiteNumber(item?.predicted_uplift_pct, 0),
      signals: (Array.isArray(item?.signals) ? item.signals : []).map(String),
      ads_units_per_day: finiteNumber(item?.ads_units_per_day, 0),
    })),
    details: {
      total: boundedInteger(payload.details?.total, 0, 0, 10000000),
      offset: boundedInteger(payload.details?.offset, scope.detail_offset, 0, 1000000),
      limit: boundedInteger(payload.details?.limit, scope.detail_limit, 1, 100),
      rows: (Array.isArray(payload.details?.rows) ? payload.details.rows : [])
        .slice(0, 100)
        .map((row) => ({
          sku_id: String(row?.sku_id || ""),
          sku_name: String(row?.sku_name || ""),
          category_id: String(row?.category_id || ""),
          category_label: String(row?.category_label || ""),
          ads_units_per_day: finiteNumber(row?.ads_units_per_day, 0),
          forecast_units: finiteNumber(row?.forecast_units, 0),
          trend_pct: finiteNumber(row?.trend_pct, 0),
          signals: (Array.isArray(row?.signals) ? row.signals : []).map(String),
          supply_state: String(row?.supply_state || "Healthy"),
        })),
    },
  };
}
