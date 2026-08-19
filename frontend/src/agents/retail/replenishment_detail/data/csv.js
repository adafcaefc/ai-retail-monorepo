/**
 * The detail grid as a file somebody opens in Excel.
 *
 * Spec section 15: the nineteen visible fields plus Position, Pack factor,
 * ordered sales units, currency, saving percentage and the exception state.
 * Pure string work, kept out of the component so it can be tested without a
 * DOM and without a download.
 */

/** Spec section 15, in the order the grid shows them. */
const COLUMNS = [
  ["sku_id", "Item"],
  ["name", "Item name"],
  ["category_label", "Category"],
  ["vertical_id", "Vertical"],
  ["qty_on_hand", "Qty on hand"],
  ["open_po", "Open PO"],
  ["position", "Position"],
  ["demand_per_day", "Demand/day"],
  ["rop", "ROP"],
  ["max", "Max"],
  ["is_reorder", "Reorder?"],
  ["required_qty_sales", "Required (sales)"],
  ["order_qty_sales", "Order qty (sales)"],
  ["buy_uom", "Buy UOM"],
  ["pack_factor", "Pack factor"],
  ["order_qty_buy", "Order qty (buy)"],
  ["ordered_sales_units", "Ordered sales units"],
  ["rounding_uplift", "Rounding uplift"],
  ["designated_vendor", "Designated vendor"],
  ["unit_price_ta", "Unit price (TA, per sales unit)"],
  ["amount", "Amount"],
  ["best_price_vendor", "Best-price vendor"],
  ["best_price", "Best price (per sales unit)"],
  ["saving_vs_designated", "Saving vs designated"],
  ["saving_pct", "Saving %"],
  ["currency", "Currency"],
  ["action_eligibility", "Eligibility"],
  ["exception_codes", "Exceptions"],
];

/**
 * Quote one field for CSV, and defuse it as a spreadsheet formula.
 *
 * A cell beginning `=`, `+`, `-` or `@` is executed as a formula by Excel and
 * Sheets when the file is opened. Vendor and product names arrive from data
 * rather than from this codebase, so the export prefixes those with an
 * apostrophe — visible in the cell, which is the point: a name that needed
 * defusing should look different from one that did not.
 */
function field(value) {
  if (value === null || value === undefined) return "";

  const text = Array.isArray(value) ? value.join(" ") : String(value);
  const defused = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;

  return /[",\n\r]/.test(defused) ? `"${defused.replaceAll('"', '""')}"` : defused;
}

/** `Reorder?` is YES / — on screen, and must be the same in the file. */
function cell(row, key, currency) {
  if (key === "currency") return currency || "IDR";
  if (key === "is_reorder") return row.is_reorder ? "YES" : "—";
  return row[key];
}

/**
 * Render detail lines as CSV text.
 *
 * Numbers are written unformatted and unrounded — spec section 15 is explicit
 * that exported values stay raw, with currency labels and separators left to
 * presentation. This file is an input to somebody else's arithmetic, and a
 * "Rp 4,4 M" would make it one they cannot do.
 */
export function buildDetailCsv(rows, currency = "IDR") {
  const header = COLUMNS.map(([, label]) => field(label)).join(",");
  const body = (rows || []).map((row) =>
    COLUMNS.map(([key]) => field(cell(row, key, currency))).join(","),
  );
  // Trailing newline: POSIX text files end with one, and its absence makes the
  // last line invisible to some line-oriented tools.
  return [header, ...body].join("\r\n") + "\r\n";
}

/** Spec section 15: `replenishment-detail_{vertical-or-all}_{timestamp}.csv`. */
export function detailFilename(verticalId, asOf) {
  const scope = !verticalId || verticalId === "ALL" ? "all" : verticalId;
  const day = String(asOf || "").slice(0, 10) || "export";
  return `replenishment-detail_${scope}_${day}.csv`;
}
