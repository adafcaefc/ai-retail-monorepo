/**
 * Display helpers shared by the Inventory Risk components.
 *
 * Presentation only — nothing here changes a figure's magnitude, and nothing
 * here decides whether a SKU is at risk. Scaling picks a unit word; it never
 * re-rounds the underlying value, which stays raw in the contract so it can
 * still be summed and sorted.
 */

import { formatNumber, numberLocale } from "../../../format.js";

/**
 * Inventory value runs to hundreds of billions of rupiah, so a bare grouped
 * integer is unreadable on a KPI tile. Step the figure down to the largest
 * unit that leaves at least one significant digit, and name that unit in the
 * reader's language — the same reasoning `millionsSuffix` already applies to
 * "mn"/"juta", extended to the two scales above it that this dataset needs.
 */
const IDR_SCALES = [
  { limit: 1e12, divisor: 1e12, en: "T", id: "T" },
  { limit: 1e9, divisor: 1e9, en: "bn", id: "M" },
  { limit: 1e6, divisor: 1e6, en: "mn", id: "jt" },
  { limit: 1e3, divisor: 1e3, en: "k", id: "rb" },
];

/** Compact rupiah, e.g. `Rp 857.3 T` / `Rp 857,3 T`. */
export function formatIdr(value, language, { digits = 1 } = {}) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";

  const magnitude = Math.abs(numeric);
  const scale = IDR_SCALES.find((step) => magnitude >= step.limit);

  if (!scale) {
    return `Rp ${formatNumber(numeric, language, { maximumFractionDigits: 0 })}`;
  }

  const scaled = numeric / scale.divisor;
  const suffix = language === "id" ? scale.id : scale.en;
  return `Rp ${formatNumber(scaled, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} ${suffix}`;
}

/** Full rupiah with no scaling, for table cells and tooltips. */
export function formatIdrExact(value, language) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `Rp ${formatNumber(numeric, language, { maximumFractionDigits: 0 })}`;
}

/** Whole units, e.g. stock counts. */
export function formatUnits(value, language) {
  return formatNumber(value, language, { maximumFractionDigits: 0 });
}

/** Days of supply, always one decimal so a column of them stays aligned. */
export function formatDays(value, language) {
  return formatNumber(value, language, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

export function formatPercent(value, language, { digits = 1 } = {}) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${formatNumber(numeric * 100, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

/**
 * A CSS class suffix per state, so the palette lives in one place in
 * `styles.css` rather than as inline colours scattered through the charts.
 * Slugified because "Slow-mover" is not a valid class fragment on its own.
 */
export function stateSlug(state) {
  return String(state).toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

/**
 * Chart fills read the same custom properties the CSS classes use, so a
 * palette change lands in both at once. Recharts needs a concrete value for
 * `fill`, and `var()` resolves fine there.
 */
export function stateColor(state) {
  return `var(--risk-${stateSlug(state)})`;
}

/** Categorical palette for the category segments inside a stacked bar. */
export function categoryColor(index) {
  const palette = [
    "var(--blue-500)",
    "var(--green-500)",
    "var(--amber-500)",
    "var(--red-500)",
    "var(--blue-700)",
    "var(--green-600)",
    "var(--gray-500)",
    "var(--amber-600)",
  ];
  return palette[index % palette.length];
}

/**
 * Sort order is severity, so the "worst" tile styling has to follow the same
 * idea: a KPI is bad when its number means more exposure, not when it is
 * simply large. Kept here so every tile agrees on what counts as bad.
 */
export function kpiTone(id, value) {
  if (value === 0) return "neutral";
  switch (id) {
    case "stockout_risk_skus":
    case "expiry_units":
      return "bad";
    case "overstock_skus":
    case "slow_mover_skus":
      return "warn";
    default:
      return "neutral";
  }
}

export { numberLocale };
