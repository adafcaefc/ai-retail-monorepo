/**
 * Display helpers shared by the Pricing & Markdown components — copied from
 * promotion_effectiveness/presentation.js rather than imported, matching how
 * every sibling board owns its own copy (no board imports another's).
 *
 * Presentation only — nothing here changes a figure's magnitude.
 */

import { formatNumber } from "../../../format.js";

const IDR_SCALES = [
  { limit: 1e12, divisor: 1e12, en: "T", id: "T" },
  { limit: 1e9, divisor: 1e9, en: "bn", id: "M" },
  { limit: 1e6, divisor: 1e6, en: "mn", id: "jt" },
  { limit: 1e3, divisor: 1e3, en: "k", id: "rb" },
];

/** Compact rupiah, e.g. `Rp 52.0 bn` / `Rp 52,0 M`. */
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

/** Whole units, e.g. candidate counts and position quantities. */
export function formatUnits(value, language) {
  return formatNumber(value, language, { maximumFractionDigits: 0 });
}

export function formatPercent(value, language, { digits = 1 } = {}) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${formatNumber(numeric * 100, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

/** Index value, e.g. a competitive-index reading of `101`. */
export function formatIndex(value, language) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return formatNumber(numeric, language, { minimumFractionDigits: 0, maximumFractionDigits: 1 });
}

/** One accent per KPI tile — custom properties, so the palette lives in `styles.css`. */
export function kpiAccent(id) {
  return `var(--pricing-kpi-${id.replace(/_/g, "-")})`;
}

/** Categorical palette for bar/donut segments. */
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

/** One colour per inventory state, so every chart agrees on what Expiry/Overstock/Slow-mover look like. */
export function stateColor(state) {
  const palette = {
    Stockout: "var(--red-500)",
    Low: "var(--amber-500)",
    Expiry: "var(--red-700)",
    Overstock: "var(--blue-500)",
    "Slow-mover": "var(--amber-600)",
    Healthy: "var(--green-500)",
  };
  return palette[state] ?? "var(--gray-500)";
}

/**
 * Tone per tile. High at-risk/write-off is bad; high recoverable/recovery
 * rate is good; candidate count and comp idx are neutral context.
 */
export function kpiTone(id, value) {
  if (value === 0) return "neutral";
  switch (id) {
    case "at_risk_value":
    case "write_off_value":
      return "warn";
    default:
      return "neutral";
  }
}
