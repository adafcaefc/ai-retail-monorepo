/**
 * Formatting for the Replenishment board.
 *
 * Presentation only: nothing here decides what a number means, and no
 * threshold lives in this file.
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

export function formatIdrExact(value, language) {
  return `Rp ${formatNumber(Number(value) || 0, language, { maximumFractionDigits: 0 })}`;
}

export function formatUnits(value, language) {
  return formatNumber(Number(value) || 0, language, { maximumFractionDigits: 0 });
}

export function formatDays(value, language) {
  return `${formatNumber(Number(value) || 0, language, { maximumFractionDigits: 1 })}d`;
}

export function formatPercent(value, language) {
  return `${formatNumber(Number(value) || 0, language, { maximumFractionDigits: 1 })}%`;
}

/** One accent per route, in lead-time order. */
export function routeColor(routeId) {
  return `var(--po-route-${routeId}, var(--gray-400))`;
}
