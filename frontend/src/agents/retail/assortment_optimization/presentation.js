/**
 * Display helpers shared by the Assortment Optimization components — each
 * retail board owns its own copy, matching the sibling convention (no board
 * imports another's).
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

/** Compact rupiah, e.g. `Rp 330.5 bn` / `Rp 330,5 M`. */
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

/** Whole units, e.g. candidate counts. */
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

/** GMROI multiplier, e.g. `5.29x`. */
export function formatGmroi(value, language) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${formatNumber(numeric, language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}x`;
}

/** Growth index, e.g. `1.15`. */
export function formatGrowth(value, language) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return formatNumber(numeric, language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** One accent per KPI tile — custom properties, so the palette lives in `styles.css`. */
export function kpiAccent(id) {
  return `var(--assortment-kpi-${id.replace(/_/g, "-")})`;
}

/** Categorical palette for bar segments. */
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
 * One colour per assortment verdict, so the quadrant, the table badges and
 * the action tabs all agree on what delist/grow/hold look like.
 */
export function classificationColor(classification) {
  const palette = {
    delist: "var(--red-500)",
    grow: "var(--green-500)",
    hold: "var(--gray-400)",
  };
  return palette[classification] ?? "var(--gray-500)";
}

/** One colour per inventory state, shared with the sibling boards. */
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
 * Tone per tile. A large delist count and a high tail share are the warning
 * signs; grow candidates, GMROI, capital freed and contribution are context
 * or upside.
 */
export function kpiTone(id, value) {
  if (value === 0) return "neutral";
  switch (id) {
    case "delist_candidates":
    case "tail_share_pct":
      return "warn";
    default:
      return "neutral";
  }
}
