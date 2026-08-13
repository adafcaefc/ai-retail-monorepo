/**
 * The purchase order as a file somebody opens in Excel.
 *
 * A3 spec section 7: `exportPOroute(k)` for one route, `exportPOall()` for the
 * whole order. Pure string work, kept out of the component so it can be tested
 * without a DOM and without a download.
 */

/** A3 spec 5c, in the order the spec lists them. */
const COLUMNS = [
  ["sku_id", "SKU"],
  ["name", "Name"],
  ["category_label", "Category"],
  ["route", "Route"],
  ["lead_days", "Lead days"],
  ["on_hand", "On-hand"],
  ["open_po", "Open PO"],
  ["position", "Position"],
  ["rop", "ROP"],
  ["max", "Max"],
  ["order_qty_sales", "Order (sales)"],
  ["pack_factor", "Pack"],
  ["order_qty_buy", "Order (buy)"],
  ["buy_uom", "Buy UOM"],
  ["order_value_cost", "Line value (cost)"],
  ["order_value_retail", "Line value (retail)"],
  ["designated_vendor", "Designated vendor"],
  ["best_price_vendor", "Best price vendor"],
  ["saving_vs_designated", "Saving if switched"],
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

  const text = String(value);
  const defused = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;

  return /[",\n\r]/.test(defused) ? `"${defused.replaceAll('"', '""')}"` : defused;
}

/**
 * Render purchase-order rows as CSV text.
 *
 * Numbers are written unformatted and unrounded — this file is an input to
 * somebody else's arithmetic, and a thousands separator or a "Rp 4,4 M" would
 * make it one they cannot do.
 */
export function buildPurchaseOrderCsv(rows) {
  const header = COLUMNS.map(([, label]) => field(label)).join(",");
  const body = rows.map((row) =>
    COLUMNS.map(([key]) => field(row[key])).join(","),
  );
  // Trailing newline: POSIX text files end with one, and its absence makes the
  // last line invisible to some line-oriented tools.
  return [header, ...body].join("\r\n") + "\r\n";
}

/** `purchase-order-direct-2026-08-12.csv` — scope and date, so files sort. */
export function purchaseOrderFilename(routeId, asOf) {
  const day = String(asOf || "").slice(0, 10) || "export";
  return `purchase-order-${routeId || "all"}-${day}.csv`;
}
