/**
 * Formatting for the Replenishment Detail board.
 *
 * Presentation only: nothing here decides what a number means, and no
 * threshold lives in this file. Copied from `replenishment/presentation.js`
 * rather than imported, matching how every sibling board owns its own copy
 * (no board imports another's).
 */

import { formatNumber } from "../../../format.js";

/** Rupiah, abbreviated. A purchase order runs to billions; digits do not help. */
export function formatIdr(value, language) {
  const amount = Number(value) || 0;
  const sign = amount < 0 ? "−" : "";
  const size = Math.abs(amount);

  if (size >= 1e12) return `${sign}Rp ${formatNumber(size / 1e12, language, { maximumFractionDigits: 2 })} T`;
  if (size >= 1e9) return `${sign}Rp ${formatNumber(size / 1e9, language, { maximumFractionDigits: 2 })} M`;
  if (size >= 1e6) return `${sign}Rp ${formatNumber(size / 1e6, language, { maximumFractionDigits: 1 })} jt`;
  return `${sign}Rp ${formatNumber(size, language, { maximumFractionDigits: 0 })}`;
}

/**
 * Rupiah in full, for the inspector and the per-cell tooltips.
 *
 * The grid abbreviates because a column of billions is unreadable otherwise,
 * but a planner checking a line against the workbook needs the digits — an
 * abbreviated figure cannot be reconciled against anything.
 */
export function formatIdrExact(value, language) {
  return `Rp ${formatNumber(Number(value) || 0, language, { maximumFractionDigits: 0 })}`;
}

export function formatUnits(value, language) {
  return formatNumber(Number(value) || 0, language, { maximumFractionDigits: 0 });
}

/** Demand per day carries decimals; the spec asks for 2–4 of them. */
export function formatRate(value, language) {
  return formatNumber(Number(value) || 0, language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatPercent(value, language) {
  return `${formatNumber(Number(value) || 0, language, { maximumFractionDigits: 1 })}%`;
}

/** One accent per KPI tile, resolved to a CSS custom property. */
export function kpiAccent(id) {
  return `var(--rdet-kpi-${String(id).replaceAll("_", "-")}, var(--gray-400))`;
}

/** One accent per row state — see `rowState` in selectors.js. */
export function stateColor(state) {
  return `var(--rdet-state-${state}, var(--gray-300))`;
}
