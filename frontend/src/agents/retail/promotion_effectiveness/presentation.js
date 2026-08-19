/**
 * Display helpers shared by the Promotion Effectiveness components.
 *
 * Presentation only — nothing here changes a figure's magnitude. Scaling picks
 * a unit word; it never re-rounds the underlying value, which stays raw in the
 * contract so it can still be summed and sorted.
 */

import { formatNumber } from "../../../format.js";

/**
 * Promotion incremental margin runs to tens of billions of rupiah, so a bare
 * grouped integer is unreadable on a KPI tile. Step the figure down to the
 * largest unit that leaves at least one significant digit.
 */
const IDR_SCALES = [
  { limit: 1e12, divisor: 1e12, en: "T", id: "T" },
  { limit: 1e9, divisor: 1e9, en: "bn", id: "M" },
  { limit: 1e6, divisor: 1e6, en: "mn", id: "jt" },
  { limit: 1e3, divisor: 1e3, en: "k", id: "rb" },
];

/** Compact rupiah, e.g. `Rp 21.0 bn` / `Rp 21,0 M`. */
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

/** Whole units, e.g. campaign counts and pre-buy units. */
export function formatUnits(value, language) {
  return formatNumber(value, language, { maximumFractionDigits: 0 });
}

/** ROI multiplier, e.g. `2.49x`. */
export function formatRoi(value, language) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${formatNumber(numeric, language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}x`;
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
 * One accent per KPI tile. Returned as custom properties so the palette lives
 * in `styles.css` and a theme change reaches the tiles without touching here.
 */
export function kpiAccent(id) {
  return `var(--promo-kpi-${id.replace(/_/g, "-")})`;
}

/**
 * Categorical palette for stacked-bar and donut segments.
 *
 * Eleven entries because the season-mix chart stacks one segment per D365
 * discount type, and there are eleven of those — at eight the palette wrapped
 * and three types repeated a colour already in the same stack. The first eight
 * are unchanged, so the other charts on this board keep the colours they had.
 */
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
    "var(--red-600)",
    "var(--gray-700)",
    "var(--blue-200)",
  ];
  return palette[index % palette.length];
}

/**
 * Tone per tile. For promotion effectiveness, high uplift / margin / ROI are
 * good; high cannibalization is bad; low funding is a warn. Kept here so every
 * tile agrees on what counts as good or bad.
 */
export function kpiTone(id, value) {
  if (value === 0) return "neutral";
  switch (id) {
    case "cannib_pct":
      return "warn";
    case "funding_pct":
      return "neutral";
    default:
      return "neutral";
  }
}
