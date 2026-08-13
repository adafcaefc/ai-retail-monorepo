export const DEMAND_AGENT_ID = "retail.demand_forecasting";

export const DEMAND_GRAINS = [
  "daily",
  "weekly",
  "monthly",
  "quarterly",
  "yearly",
];

export const DEMAND_HORIZONS = [4, 8, 12, 16];

export const DEFAULT_DEMAND_LEVERS = Object.freeze({
  demand: 0,
  promo: 15,
  markdown: 25,
  inbound: 0,
  lead: 0,
  safety: 0,
});

export const DEMAND_LEVER_DEFINITIONS = Object.freeze([
  { id: "demand", label: "Demand shift", unit: "%", min: -30, max: 40, step: 1, effect: "Moves the whole forecast curve" },
  { id: "promo", label: "Promo intensity", unit: "%", min: 0, max: 50, step: 1, effect: "Lifts promo-SKU demand" },
  { id: "markdown", label: "Markdown depth", unit: "%", min: 0, max: 60, step: 1, effect: "Accelerates at-risk demand" },
  { id: "inbound", label: "Extra inbound", unit: "%", min: -40, max: 60, step: 1, effect: "Changes supply cover" },
  { id: "lead", label: "Vendor lead time", unit: "d", min: -2, max: 6, step: 1, effect: "Changes supply exposure" },
  { id: "safety", label: "Safety stock", unit: "d", min: -2, max: 5, step: 1, effect: "Buffers forecast error" },
]);

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

export const DEMAND_SCENARIO_CONTEXT_KEYS = Object.freeze([
  "legal_entity_id",
  "category_group",
  "store_id",
  "sku",
  "grain",
  "horizon_weeks",
]);

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

export function demandScenarioContext(query = {}) {
  const normalized = normalizeDemandQuery(query);
  return Object.fromEntries(
    DEMAND_SCENARIO_CONTEXT_KEYS.map((key) => [key, normalized[key]]),
  );
}

export function isDemandScenarioCompatible(scenario, query) {
  const saved = demandScenarioContext(scenario?.context || {});
  const current = demandScenarioContext(query);
  return DEMAND_SCENARIO_CONTEXT_KEYS.every((key) => {
    if (key === "sku") {
      return saved[key].toLowerCase() === current[key].toLowerCase();
    }
    return saved[key] === current[key];
  });
}

export function normalizeDemandLevers(levers = {}) {
  return Object.fromEntries(DEMAND_LEVER_DEFINITIONS.map((definition) => {
    const fallback = DEFAULT_DEMAND_LEVERS[definition.id];
    const value = finiteNumber(levers[definition.id], fallback);
    const clamped = Math.min(definition.max, Math.max(definition.min, value));
    return [definition.id, clamped];
  }));
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

function normalizeDimensionRows(rows, extra = () => ({})) {
  return (Array.isArray(rows) ? rows : []).map((row) => ({
    id: String(row?.id || ""),
    label: String(row?.label || row?.id || ""),
    forecast_units: finiteNumber(row?.forecast_units, 0),
    share_pct: finiteNumber(row?.share_pct, 0),
    ...extra(row),
  }));
}

function normalizeSimulation(simulation = {}, fallbackForecast) {
  const baseline = simulation.baseline || {};
  const scenario = simulation.scenario || baseline;
  const metrics = (source) => ({
    forecast_next_7d: finiteNumber(source?.forecast_next_7d, 0),
    stockout_risk_skus: finiteNumber(source?.stockout_risk_skus, 0),
    forecast_accuracy_pct: finiteNumber(source?.forecast_accuracy_pct, 0),
    predicted_to_trend: finiteNumber(source?.predicted_to_trend, 0),
  });

  return {
    applied: Boolean(simulation.applied),
    levers: (simulation.levers || DEMAND_LEVER_DEFINITIONS).map((lever) => ({
      id: String(lever.id || ""),
      label: String(lever.label || ""),
      unit: String(lever.unit || ""),
      min: finiteNumber(lever.min, 0),
      max: finiteNumber(lever.max, 100),
      step: finiteNumber(lever.step, 1),
      effect: String(lever.effect || ""),
    })),
    scenario_levers: normalizeDemandLevers(simulation.scenario_levers),
    baseline: metrics(baseline),
    scenario: metrics(scenario),
    baseline_forecast: normalizeSeries(simulation.baseline_forecast || fallbackForecast),
  };
}

function demandContractError(field, detail = "is required") {
  throw new Error(`Demand Forecasting API contract field ${field} ${detail}.`);
}

/**
 * API mode is strict about the Phase 2 panels. Empty arrays are valid for an
 * empty business scope, but the fields themselves must be present so a partial
 * backend response cannot silently render as a successful empty dashboard.
 */
export function validateDemandDashboardV2(payload) {
  if (Number(payload?.schema_version) < 2) {
    demandContractError("schema_version", "must be 2 or newer");
  }

  const dimensionArrays = [
    "categories",
    "stores",
    "clusters",
    "legal_entities",
    "seasonality",
  ];
  if (!payload?.dimensions || typeof payload.dimensions !== "object") {
    demandContractError("dimensions");
  }
  dimensionArrays.forEach((field) => {
    if (!Array.isArray(payload.dimensions[field])) {
      demandContractError(`dimensions.${field}`);
    }
  });
  if (payload.dimensions.seasonality.length !== 12) {
    demandContractError("dimensions.seasonality", "must contain exactly 12 points");
  }
  if (payload.dimensions.chain_total == null
    || !Number.isFinite(Number(payload.dimensions.chain_total))) {
    demandContractError("dimensions.chain_total", "must be numeric");
  }
  if (!payload.dimensions.seasonality.some((point) => point?.current)) {
    demandContractError("dimensions.seasonality", "must identify the current month");
  }
  if (payload.dimensions.seasonality.some((point) => !Number.isFinite(Number(point?.index)))) {
    demandContractError("dimensions.seasonality[].index", "must be numeric");
  }

  if (!payload?.simulation || typeof payload.simulation !== "object") {
    demandContractError("simulation");
  }
  if (!Array.isArray(payload.simulation.levers)
    || !DEMAND_LEVER_DEFINITIONS.every((definition) =>
      payload.simulation.levers.some((lever) => lever?.id === definition.id))) {
    demandContractError("simulation.levers");
  }
  ["baseline", "scenario", "scenario_levers", "baseline_forecast"].forEach((field) => {
    if (!payload.simulation[field] || typeof payload.simulation[field] !== "object") {
      demandContractError(`simulation.${field}`);
    }
  });
  if (!Array.isArray(payload.simulation.baseline_forecast.points)
    || !payload.simulation.baseline_forecast.points.length) {
    demandContractError("simulation.baseline_forecast.points", "must contain forecast data");
  }
  const simulationMetrics = [
    "forecast_next_7d",
    "stockout_risk_skus",
    "forecast_accuracy_pct",
    "predicted_to_trend",
  ];
  ["baseline", "scenario"].forEach((section) => {
    simulationMetrics.forEach((metric) => {
      if (payload.simulation[section][metric] == null
        || !Number.isFinite(Number(payload.simulation[section][metric]))) {
        demandContractError(`simulation.${section}.${metric}`, "must be numeric");
      }
    });
  });
  DEMAND_LEVER_DEFINITIONS.forEach((definition) => {
    const value = payload.simulation.scenario_levers[definition.id];
    if (value == null || !Number.isFinite(Number(value))) {
      demandContractError(
        `simulation.scenario_levers.${definition.id}`,
        "must be numeric",
      );
    }
  });

  if (!payload?.suggested_actions || typeof payload.suggested_actions !== "object") {
    demandContractError("suggested_actions");
  }
  ["primary", "secondary", "plan_preview"].forEach((field) => {
    if (!payload.suggested_actions[field]
      || typeof payload.suggested_actions[field] !== "object") {
      demandContractError(`suggested_actions.${field}`);
    }
  });
  if (!Array.isArray(payload.suggested_actions.plan_preview.rows)) {
    demandContractError("suggested_actions.plan_preview.rows");
  }
  payload.suggested_actions.plan_preview.rows.forEach((row, index) => {
    if (row?.forecast_7d_units == null
      || !Number.isFinite(Number(row.forecast_7d_units))) {
      demandContractError(
        `suggested_actions.plan_preview.rows[${index}].forecast_7d_units`,
        "must be numeric",
      );
    }
  });
  ["primary", "secondary"].forEach((section) => {
    ["title", "description", "action_label"].forEach((field) => {
      if (typeof payload.suggested_actions[section][field] !== "string") {
        demandContractError(`suggested_actions.${section}.${field}`);
      }
    });
  });
  ["title", "description"].forEach((field) => {
    if (typeof payload.suggested_actions.plan_preview[field] !== "string") {
      demandContractError(`suggested_actions.plan_preview.${field}`);
    }
  });
}

/**
 * Normalize both mock and API payloads at the feature boundary. Presentation
 * components only receive this shape and never need to know which provider ran.
 */
export function normalizeDemandDashboard(payload, { requirePhase2 = false } = {}) {
  if (!payload || payload.agent !== DEMAND_AGENT_ID) {
    throw new Error("Demand Forecasting returned an invalid dashboard contract.");
  }
  if (requirePhase2) validateDemandDashboardV2(payload);

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
    dimensions: {
      categories: normalizeDimensionRows(payload.dimensions?.categories),
      stores: normalizeDimensionRows(payload.dimensions?.stores, (row) => ({
        legal_entity_id: String(row?.legal_entity_id || ""),
        cluster: String(row?.cluster || ""),
      })),
      clusters: normalizeDimensionRows(payload.dimensions?.clusters, (row) => ({
        store_count: boundedInteger(row?.store_count, 0, 0, 100000),
      })),
      legal_entities: normalizeDimensionRows(payload.dimensions?.legal_entities, (row) => ({
        store_count: boundedInteger(row?.store_count, 0, 0, 100000),
      })),
      seasonality: (Array.isArray(payload.dimensions?.seasonality)
        ? payload.dimensions.seasonality
        : []).map((point, index) => ({
        month: String(point?.month || index + 1),
        index: finiteNumber(point?.index, 100),
        current: Boolean(point?.current),
      })),
      chain_total: finiteNumber(payload.dimensions?.chain_total, 0),
    },
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
      forecast_total_units: finiteNumber(payload.details?.forecast_total_units, 0),
      rows: (Array.isArray(payload.details?.rows) ? payload.details.rows : [])
        .slice(0, 100)
        .map((row) => ({
          sku_id: String(row?.sku_id || ""),
          sku_name: String(row?.sku_name || ""),
          category_id: String(row?.category_id || ""),
          category_label: String(row?.category_label || ""),
          ads_units_per_day: finiteNumber(row?.ads_units_per_day, 0),
          forecast_7d_units: finiteNumber(row?.forecast_7d_units, 0),
          forecast_units: finiteNumber(row?.forecast_units, 0),
          trend_pct: finiteNumber(row?.trend_pct, 0),
          signals: (Array.isArray(row?.signals) ? row.signals : []).map(String),
          supply_state: String(row?.supply_state || "Healthy"),
        })),
    },
    simulation: normalizeSimulation(payload.simulation, payload.forecast),
    scenarios: (Array.isArray(payload.scenarios) ? payload.scenarios : []).map((scenario) => ({
      id: String(scenario?.id || ""),
      name: String(scenario?.name || ""),
      levers: normalizeDemandLevers(scenario?.levers),
      context: demandScenarioContext(scenario?.context || scenario?.scope),
      baseline_forecast: normalizeSeries(
        scenario?.baseline_forecast || payload.simulation?.baseline_forecast || payload.forecast,
      ),
      forecast: normalizeSeries(scenario?.forecast || payload.forecast),
      saved_at: String(scenario?.saved_at || ""),
    })),
    suggested_actions: {
      primary: {
        title: String(payload.suggested_actions?.primary?.title || ""),
        description: String(payload.suggested_actions?.primary?.description || ""),
        action_label: String(payload.suggested_actions?.primary?.action_label || ""),
      },
      secondary: {
        title: String(payload.suggested_actions?.secondary?.title || ""),
        description: String(payload.suggested_actions?.secondary?.description || ""),
        action_label: String(payload.suggested_actions?.secondary?.action_label || ""),
      },
      plan_preview: {
        title: String(payload.suggested_actions?.plan_preview?.title || ""),
        description: String(payload.suggested_actions?.plan_preview?.description || ""),
        rows: (Array.isArray(payload.suggested_actions?.plan_preview?.rows)
          ? payload.suggested_actions.plan_preview.rows
          : []).slice(0, 12).map((row) => ({
          sku_id: String(row?.sku_id || ""),
          sku_name: String(row?.sku_name || ""),
          forecast_7d_units: finiteNumber(row?.forecast_7d_units, 0),
          signal: String(row?.signal || ""),
          route: String(row?.route || ""),
        })),
      },
    },
  };
}
