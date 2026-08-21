const COLUMNS = [
  ["store_name", "Store"],
  ["sku_id", "SKU"],
  ["item_name", "Item"],
  ["category", "Category"],
  ["target", "Target"],
  ["forecast_7d", "Forecast 7d"],
  ["rop", "ROP"],
  ["max", "Max"],
  ["position", "Position"],
  ["suggestion", "Suggestion"],
  ["signal", "Signal"],
  ["route", "Route"],
  ["eta", "ETA"],
];

function field(value) {
  if (value === null || value === undefined) return "";

  const text = String(value);
  // Keep finite numbers numeric in the file. Text beginning with a spreadsheet
  // formula marker is defused with the same visible apostrophe convention used
  // by the Replenishment export helper.
  const isNumber = typeof value === "number" && Number.isFinite(value);
  const defused = !isNumber && /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;

  return /[",\n\r]/.test(defused)
    ? `"${defused.replaceAll('"', '""')}"`
    : defused;
}

function cell(row, key) {
  if (key === "target") return row.target?.value ?? null;
  if (key === "signal") return Array.isArray(row.signal) ? row.signal.join(" | ") : row.signal;
  if (key === "eta") return row.eta == null ? "Unavailable" : row.eta;
  return row[key];
}

/** Render backend rows as a safe, raw-value Demand Forecasting CSV. */
export function buildForecastBasketCsv(rows = []) {
  const header = COLUMNS.map(([, label]) => field(label)).join(",");
  const body = rows.map((row) => COLUMNS.map(([key]) => field(cell(row, key))).join(","));
  return [header, ...body].join("\r\n") + "\r\n";
}

function safeToken(value) {
  return String(value || "")
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "all";
}

export function forecastBasketScopeToken(scope = {}) {
  const parts = [
    scope.store_id && scope.store_id !== "ALL" ? scope.store_id : "all-stores",
    scope.legal_entity_id && scope.legal_entity_id !== "ALL" ? scope.legal_entity_id : "",
    scope.category_group && scope.category_group !== "ALL" ? scope.category_group : "",
    scope.sku || "",
  ].filter(Boolean);
  return parts.map(safeToken).join("_");
}

export function forecastBasketFilename(scope, asOf, mode = "actionable") {
  const day = String(asOf || "").slice(0, 10) || "export";
  return `demand_forecast_basket_${forecastBasketScopeToken(scope)}_${day}_${mode}.csv`;
}

