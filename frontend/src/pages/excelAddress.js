/*
 * Workbook cell addresses, and the one link format that opens one.
 *
 * The Formula Manager cites the cell behind every worked-example input
 * ("Stores!E6"); the Data Source page is the viewer that can show it. This
 * module is the seam between them, and the only place an href is built.
 *
 * The app has no router -- navigation is `activeAgent` state in App.jsx -- so
 * the link is a hash:
 *
 *   #main.data_source?cell=Stores%21E6
 *
 * A hash keeps a real <a href>: middle-click, "open in new tab" and copying
 * the address all work, and no dependency is added to do it. App.jsx reads it
 * on load and on `hashchange`; nothing writes it back, so there is no state
 * to keep in sync.
 *
 * Lives beside registry.js rather than inside a page folder because both pages
 * need it, and outside the `./*&#47;*&#47;index.js` page glob so it is never mistaken
 * for a page.
 */

export const WORKSHEET_PAGE_ID = "main.data_source";

// Sheet!Cell, tolerating the $ of an absolute reference. Sheet names are not
// all ASCII (one is "What-If · Per Agent"), so the sheet half stays greedy and
// unvalidated -- only the cell half has a shape worth checking.
const CELL_ADDRESS = /^(.+)!\$?([A-Za-z]{1,3})\$?(\d{1,7})$/;

/** Split "ENGINE_STORE!J4" into its sheet and cell for display. */
export function splitAddress(address) {
  const separator = String(address ?? "").indexOf("!");
  if (separator === -1) {
    return { sheet: "", cell: String(address ?? "") };
  }
  return {
    sheet: address.slice(0, separator),
    cell: address.slice(separator + 1)
  };
}

/**
 * "SKU_Master!AA6" -> { sheet, cell, row: 6, column: 27 }, or null when the
 * text is not a single-cell reference. Row and column are 1-based, matching
 * the workbook payload's own numbering.
 */
export function parseAddress(address) {
  const match = CELL_ADDRESS.exec(String(address ?? "").trim());

  if (!match) {
    return null;
  }

  const [, sheet, letters, digits] = match;
  const cell = `${letters.toUpperCase()}${digits}`;

  let column = 0;
  for (const character of letters.toUpperCase()) {
    column = column * 26 + (character.charCodeAt(0) - 64);
  }

  return { sheet, cell, row: Number(digits), column };
}

/** The deep link that opens `address` in the Data Source viewer. */
export function excelAddressHref(address) {
  if (!parseAddress(address)) {
    return "#";
  }

  return `#${WORKSHEET_PAGE_ID}?cell=${encodeURIComponent(address)}`;
}

/**
 * The reverse, for App.jsx: which page the hash names, and which cell it asks
 * that page to show. Returns null for an empty or malformed hash.
 */
export function parseWorkbookHash(hash) {
  const raw = String(hash ?? "").replace(/^#/, "");

  if (!raw) {
    return null;
  }

  const separator = raw.indexOf("?");
  const pageId = separator === -1 ? raw : raw.slice(0, separator);

  if (!pageId) {
    return null;
  }

  const query = separator === -1 ? "" : raw.slice(separator + 1);

  return {
    pageId,
    address: new URLSearchParams(query).get("cell") || ""
  };
}
