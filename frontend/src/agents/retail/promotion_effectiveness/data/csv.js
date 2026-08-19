/**
 * The promo plan as a file somebody opens in Excel.
 *
 * A4 spec section 7: `exportPromoPlan(k)` for one tab, `exportPromoAll()` for
 * the whole campaign plan. Pure string work, kept out of the component so it
 * can be tested without a DOM and without a download. Modeled directly on
 * `replenishment/data/csv.js` — same field-defusing, same quoting.
 */

/** A4 spec 5c/7, in the order the calendar table and best-action panel list them. */
const CAMPAIGN_COLUMNS = [
  ["promo_id", "Promo ID"],
  ["promo_name", "Name"],
  ["discount_type", "Discount type"],
  ["scope", "Scope"],
  ["vertical_label", "Vertical"],
  ["target_category", "Target category"],
  ["season", "Season"],
  ["peak_month", "Peak month"],
  ["mechanism", "Mechanism"],
  ["discount_pct", "Discount %"],
  ["value_rule", "Value/rule"],
  ["min_qty_threshold", "Min qty/threshold"],
  ["supplier_funding_pct", "Supplier funding %"],
  ["expected_uplift_pct", "Expected uplift %"],
  ["pre_buy_uplift_units", "Pre-buy uplift units"],
  ["valid_from", "Valid from"],
  ["valid_to", "Valid to"],
  ["d365_construct", "D365 construct"],
  ["recommendation", "Recommendation"],
];

/**
 * Quote one field for CSV, and defuse it as a spreadsheet formula.
 *
 * A cell beginning `=`, `+`, `-` or `@` is executed as a formula by Excel and
 * Sheets when the file is opened. Promo and vendor-facing names arrive from
 * data rather than from this codebase, so the export prefixes those with an
 * apostrophe — visible in the cell, which is the point: a name that needed
 * defusing should look different from one that did not.
 */
function field(value) {
  if (value === null || value === undefined) return "";

  const text = String(value);
  const defused = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;

  return /[",\n\r]/.test(defused) ? `"${defused.replaceAll('"', '""')}"` : defused;
}

/**
 * Render campaign rows as CSV text — used for both "export this tab" and
 * "export all campaigns" (same columns, different row sets).
 *
 * Numbers are written unformatted and unrounded — this file is an input to
 * somebody else's arithmetic, and a thousands separator or a "Rp 4,4 M" would
 * make it one they cannot do.
 */
export function buildCampaignsCsv(rows) {
  const header = CAMPAIGN_COLUMNS.map(([, label]) => field(label)).join(",");
  const body = rows.map((row) =>
    CAMPAIGN_COLUMNS.map(([key]) => field(row[key])).join(","),
  );
  // Trailing newline: POSIX text files end with one, and its absence makes the
  // last line invisible to some line-oriented tools.
  return [header, ...body].join("\r\n") + "\r\n";
}

/** `promo-plan-high_roi-2026-08-12.csv` — scope and date, so files sort. */
export function campaignsFilename(scopeId, asOf) {
  const day = String(asOf || "").slice(0, 10) || "export";
  return `promo-plan-${scopeId || "all"}-${day}.csv`;
}

const SCENARIO_METRICS = [
  ["active_promo_skus", "Promo SKUs"],
  ["uplift_pct", "Uplift %"],
  ["incremental_margin", "Incremental margin"],
  ["roi_x", "ROI (x)"],
];

/**
 * Compare Scenarios as CSV — A4 spec section 9d's `exportScenarios()`. One
 * row per metric, one column per series (Baseline + each saved scenario),
 * matching the chart's own shape rather than one row per scenario.
 */
export function buildScenariosCsv(baseline, scenarios) {
  const seriesNames = ["Baseline", ...(scenarios ?? []).map((s) => s.name)];
  const header = ["Metric", ...seriesNames].map(field).join(",");
  const body = SCENARIO_METRICS.map(([key, label]) => {
    const values = seriesNames.map((name) => {
      if (name === "Baseline") return baseline?.[key] ?? "";
      const scenario = scenarios.find((s) => s.name === name);
      return scenario?.kpis?.[key] ?? "";
    });
    return [field(label), ...values.map(field)].join(",");
  });
  return [header, ...body].join("\r\n") + "\r\n";
}

/** `promo-scenarios-2026-08-12.csv` */
export function scenariosFilename(asOf) {
  const day = String(asOf || "").slice(0, 10) || "export";
  return `promo-scenarios-${day}.csv`;
}
