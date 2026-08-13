/**
 * Real distributions for the KPI tiles' mini-charts.
 *
 * WHY DISTRIBUTIONS AND NOT TRENDS
 * The mockup puts a sparkline on every tile and fills the ones with no series
 * from a seeded random walk. This dataset holds one snapshot per SKU and no
 * date column, so a trend on most of these tiles could only be fabricated.
 *
 * A histogram of the rows behind the number needs no history at all, and
 * answers a question the bare figure cannot: 302 SKUs below reorder point is
 * one situation if they are all barely under and quite another if half are at
 * zero cover. Every function here is a count or a sum over rows already in
 * scope — nothing is generated, nothing is smoothed.
 *
 * Each returns a plain `number[]`, lowest bucket first, for `KpiSparkline`.
 */

/** Days-of-cover buckets, in the order the histogram draws them. */
export const DOS_BUCKETS = [
  { id: "d0", label: "0", max: 0.5 },
  { id: "d1", label: "≤2d", max: 2 },
  { id: "d2", label: "≤5d", max: 5 },
  { id: "d3", label: "≤8d", max: 8 },
  { id: "d4", label: "≤12d", max: 12 },
  { id: "d5", label: "≤15d", max: 15 },
  { id: "d6", label: "≤21d", max: 21 },
  { id: "d7", label: "≤30d", max: 30 },
  { id: "d8", label: ">30d", max: Infinity },
];

/**
 * How the rows in scope spread across days of cover.
 *
 * The natural shape for anything about stock position: stockout risk piles up
 * on the left, overstock on the right, and a healthy chain is a hump in the
 * middle. Reading the same axis under several tiles is what makes them
 * comparable at a glance.
 */
export function dosHistogram(rows, field = "dos") {
  const counts = DOS_BUCKETS.map(() => 0);
  for (const row of rows) {
    const value = Number(row[field]);
    if (!Number.isFinite(value)) continue;
    const index = DOS_BUCKETS.findIndex((bucket) => value <= bucket.max);
    counts[index === -1 ? counts.length - 1 : index] += 1;
  }
  return counts;
}

/**
 * The metric's own weight per group, biggest first, capped.
 *
 * Capped rather than scrolled because a sparkline is 100 units wide: past
 * about a dozen bars each one is a hairline and the shape stops meaning
 * anything. The drawer shows the full ranking.
 */
export function topGroups(rows, key, reduce, limit = 12) {
  const grouped = new Map();
  for (const row of rows) {
    const id = row[key];
    if (!grouped.has(id)) grouped.set(id, []);
    grouped.get(id).push(row);
  }
  return [...grouped.values()]
    .map(reduce)
    .filter((value) => Number.isFinite(value) && Math.abs(value) > 1e-9)
    .sort((a, b) => b - a)
    .slice(0, limit);
}

/** Growth-index buckets, for anything about velocity. */
export const GROWTH_BUCKETS = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, Infinity];

export function growthHistogram(rows, field = "growth") {
  const counts = GROWTH_BUCKETS.map(() => 0);
  for (const row of rows) {
    const value = Number(row[field]);
    if (!Number.isFinite(value)) continue;
    const index = GROWTH_BUCKETS.findIndex((edge) => value <= edge);
    counts[index === -1 ? counts.length - 1 : index] += 1;
  }
  return counts;
}
