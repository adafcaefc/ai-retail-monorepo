const FORECAST_BASKET_ENDPOINT =
  "/api/html/dashboard/retail.demand_forecasting/forecast-basket";

const SCOPE_KEYS = [
  "legal_entity_id",
  "category_group",
  "store_id",
  "sku",
];

const ROW_FIELDS = [
  "store_id",
  "store_name",
  "sku_id",
  "item_name",
  "category_id",
  "category",
  "target",
  "forecast_7d",
  "rop",
  "max",
  "position",
  "suggestion",
  "signal",
  "route",
  "lead_time_days",
  "eta",
  "eta_status",
  "perishable",
  "vendor",
];

function contractError(field, detail = "is required") {
  throw new Error(`Forecast basket API contract field ${field} ${detail}.`);
}

function numeric(value, field, { integer = false, fallback = null } = {}) {
  if (value === null || value === undefined || value === "") {
    if (fallback !== null) return fallback;
    contractError(field, "must be numeric");
  }

  const result = Number(value);
  if (!Number.isFinite(result) || (integer && !Number.isInteger(result))) {
    contractError(field, "must be numeric");
  }
  return result;
}

function normalizeScope(scope) {
  const source = scope && typeof scope === "object" ? scope : {};
  return Object.fromEntries(SCOPE_KEYS.map((key) => [
    key,
    source[key] == null || source[key] === "" ? null : String(source[key]),
  ]));
}

function normalizeTarget(target, rowIndex) {
  if (!target || typeof target !== "object") {
    contractError(`rows[${rowIndex}].target`);
  }
  return {
    value: numeric(target.value, `rows[${rowIndex}].target.value`),
    unit: String(target.unit || ""),
    basis: String(target.basis || ""),
  };
}

function normalizeRow(row, index) {
  if (!row || typeof row !== "object") {
    contractError(`rows[${index}]`);
  }
  ROW_FIELDS.forEach((field) => {
    if (!(field in row)) contractError(`rows[${index}].${field}`);
  });

  return {
    store_id: String(row.store_id),
    store_name: String(row.store_name),
    sku_id: String(row.sku_id),
    item_name: String(row.item_name),
    category_id: String(row.category_id),
    category: String(row.category),
    target: normalizeTarget(row.target, index),
    forecast_7d: numeric(row.forecast_7d, `rows[${index}].forecast_7d`),
    rop: numeric(row.rop, `rows[${index}].rop`),
    max: numeric(row.max, `rows[${index}].max`),
    position: numeric(row.position, `rows[${index}].position`),
    suggestion: numeric(row.suggestion, `rows[${index}].suggestion`),
    signal: Array.isArray(row.signal) ? row.signal.map(String) : contractError(`rows[${index}].signal`, "must be an array"),
    route: String(row.route),
    lead_time_days: numeric(row.lead_time_days, `rows[${index}].lead_time_days`),
    eta: row.eta == null ? null : String(row.eta),
    eta_status: String(row.eta_status),
    perishable: Boolean(row.perishable),
    vendor: String(row.vendor),
  };
}

function assertUniqueStoreSku(rows) {
  const keys = new Set();
  rows.forEach((row) => {
    const key = `${row.store_id}\u0000${row.sku_id}`;
    if (keys.has(key)) {
      throw new Error(`Forecast basket contains duplicate Store × SKU key ${row.store_id} + ${row.sku_id}.`);
    }
    keys.add(key);
  });
}

/**
 * Normalize the additive basket response at the feature boundary. The table
 * receives these values as returned by the backend; it never recalculates the
 * suggestion or forecast totals in the browser.
 */
export function normalizeForecastBasket(payload) {
  if (!payload || typeof payload !== "object") {
    throw new Error("Forecast basket returned an invalid response.");
  }
  if (Number(payload.schema_version) < 1) {
    contractError("schema_version", "must be 1 or newer");
  }
  if (payload.grain !== "sku_store") {
    contractError("grain", "must be sku_store");
  }
  if (payload.source !== "retail.fact_inventory_daily.forecast_7d") {
    contractError("source", "must be retail.fact_inventory_daily.forecast_7d");
  }
  if (!Array.isArray(payload.rows)) contractError("rows", "must be an array");
  if (typeof payload.reconciles !== "boolean") {
    contractError("reconciles", "must be boolean");
  }

  const rows = payload.rows.map(normalizeRow);
  const rowCount = numeric(payload.row_count, "row_count", { integer: true });
  if (rowCount !== rows.length) {
    throw new Error(`Forecast basket row_count ${rowCount} does not match ${rows.length} returned rows.`);
  }

  assertUniqueStoreSku(rows);

  return {
    schema_version: numeric(payload.schema_version, "schema_version", { integer: true }),
    agent: String(payload.agent || ""),
    as_of: String(payload.as_of || ""),
    scope: normalizeScope(payload.scope),
    grain: "sku_store",
    source: String(payload.source || ""),
    source_import_batch_id: payload.source_import_batch_id == null
      ? null
      : numeric(payload.source_import_batch_id, "source_import_batch_id", { integer: true }),
    row_count: rowCount,
    action_row_count: numeric(payload.action_row_count, "action_row_count", { integer: true }),
    dashboard_forecast_7d: numeric(payload.dashboard_forecast_7d, "dashboard_forecast_7d"),
    basket_forecast_7d: numeric(payload.basket_forecast_7d, "basket_forecast_7d"),
    reconciles: payload.reconciles,
    suggestion_units: numeric(payload.suggestion_units, "suggestion_units"),
    rows,
  };
}

/** Serialize only the four supported operational basket filters. */
export function serializeForecastBasketScope(query = {}) {
  const params = new URLSearchParams();
  SCOPE_KEYS.forEach((key) => {
    const value = query[key];
    if (value != null && String(value).trim() && value !== "ALL") {
      params.set(key, String(value).trim());
    }
  });
  return params;
}

async function responseError(response) {
  let detail = "";
  try {
    const payload = await response.json();
    detail = typeof payload?.detail === "string" ? payload.detail : "";
  } catch {
    // The status text below is still useful when a gateway returns non-JSON.
  }
  return new Error(detail || `Forecast basket request failed (${response.status}).`);
}

export async function fetchForecastBasket(query = {}, { signal } = {}) {
  const params = serializeForecastBasketScope(query);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${FORECAST_BASKET_ENDPOINT}${suffix}`, { signal });
  if (!response.ok) throw await responseError(response);
  return normalizeForecastBasket(await response.json());
}

export { FORECAST_BASKET_ENDPOINT };
