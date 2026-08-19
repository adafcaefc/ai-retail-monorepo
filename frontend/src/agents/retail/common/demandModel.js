/**
 * The one daily-demand model both retail boards run.
 *
 * WHY THIS FILE EXISTS
 * Demand Forecasting drew a shaped curve — day-of-week, season, trend — while
 * Inventory Risk burned `ads * day`, a flat line, and published a constant as
 * its "demand per day". Two boards reading the same workbook disagreed about
 * how much stock tomorrow costs. The model lives here now, so they cannot.
 *
 * THE MODEL
 * Classical multiplicative decomposition, the ordinary retail one:
 *
 *     demand(d) = ADS x DOW(d) x seasonal(month(d)) x (1 + trend)^(d/365)
 *
 * Every factor traces to something in the workbook:
 *   ADS       f01, per SKU
 *   DOW       seven factors summing to `Constants` B7 = 7.45, which is exactly
 *             what f08 multiplies ADS by to get a week. A modelled allocation
 *             of a measured total: the week is the workbook's, the shape
 *             inside it is ours.
 *   seasonal  twelve indices per vertical from the monthly GMV profile,
 *             divided by the current month's index so today's factor is 1 and
 *             the level stays where f01 put it
 *   trend     the A1 sheet's `Trend %` — a typed constant, compounded daily
 *
 * WHAT THE SHAPE CAN AND CANNOT DO
 * Because the seven DOW factors sum to `dow_sum` by construction, any whole
 * week of this model totals exactly `ads * 7.45` — f08's own answer — and the
 * shape is invisible in any bucket a whole number of weeks wide. It is a
 * within-week reallocation, not new information about the week's size. That is
 * the honest limit and it belongs in both boards' copy.
 */

/** Days in the seasonal step. Matches the workbook's monthly GMV grain. */
export const DAYS_PER_MONTH = 30.44;

/** Days in the day-of-week cycle. Named so no call site carries a bare 7. */
export const DOW_DAYS = 7;

const WEEKDAY_LABELS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

/**
 * The unitless multiplier on `ads` for one day out.
 *
 * Separate from `dailyDemand` because a projection over hundreds of SKUs
 * sharing one vertical needs the factor once per day, not once per SKU per
 * day: the factor depends only on the vertical, the level only on the SKU.
 *
 * `curve` is the vertical's twelve seasonal indices; dividing by the current
 * month's keeps the level where f01 put it, because f01 already evaluated each
 * SKU's seasonality at that month.
 *
 * @param {number} day Days from today; 0 is today.
 * @param {number[]} profile Seven day-of-week factors, Monday first.
 * @param {number[]} curve Twelve seasonal indices.
 * @param {number} currentMonth Index of the month the workbook says it is.
 * @param {number} trendPct Annual trend, in percent.
 * @returns {number}
 */
export function dailyFactor(day, profile, curve, currentMonth, trendPct) {
  const dow = profile[((day % DOW_DAYS) + DOW_DAYS) % DOW_DAYS];
  const month = Math.floor(currentMonth + day / DAYS_PER_MONTH) % 12;
  const seasonal = curve[(month + 12) % 12] / curve[currentMonth % 12];
  const trend = (1 + trendPct / 100) ** (day / 365);
  return dow * seasonal * trend;
}

/**
 * Demand for one day out, at whatever level `ads` describes.
 *
 * @param {number} ads Average daily sales — one SKU's, or a scope's total.
 * @returns {number}
 */
export function dailyDemand(ads, day, profile, curve, currentMonth, trendPct) {
  return ads * dailyFactor(day, profile, curve, currentMonth, trendPct);
}

/**
 * Every day's factor for one vertical, computed once.
 *
 * @param {number} days Last day to cover, inclusive.
 * @returns {number[]} Indexed by day, length `days + 1`.
 */
export function dailyFactors(days, profile, curve, currentMonth, trendPct) {
  return Array.from({ length: days + 1 }, (_unused, day) =>
    dailyFactor(day, profile, curve, currentMonth, trendPct),
  );
}

/**
 * Blend a per-vertical constant across the scope, weighted by volume.
 *
 * Accuracy, trend and the seasonality index exist only per vertical. Looking at
 * two verticals at once has to produce one number, and weighting by volume is
 * the only sensible way — an unweighted mean would let a tiny vertical move the
 * chain's reported accuracy as much as the largest one.
 *
 * `weightKey` differs by board and does not change the answer. Demand
 * Forecasting weights by `forecast_7d`, Inventory Risk by `ads`, and
 * `forecast_7d = ads * 7.45` (f08) — a constant factor cancels out of a
 * weighted mean. So the two boards blend identically without Inventory Risk
 * having to carry a column it has no other use for.
 *
 * @param {object[]} items Scoped rows.
 * @param {Record<string, object>} referenceBy Per-vertical reference rows.
 * @param {string} key The column to blend.
 * @param {string} [weightKey] The column to weight by.
 * @returns {number}
 */
export function blend(items, referenceBy, key, weightKey = "forecast_7d") {
  let weighted = 0;
  let weight = 0;
  for (const item of items) {
    const row = referenceBy[item.vertical_id];
    if (!row) continue;
    weighted += row[key] * item[weightKey];
    weight += item[weightKey];
  }
  return weight ? weighted / weight : 0;
}

/**
 * The scope's seasonal curve, blended the same way.
 *
 * @param {object[]} items Scoped rows.
 * @param {{ by_legal_entity: Record<string, number[]> }} seasonality
 * @param {string} [weightKey] As `blend`.
 * @returns {number[]} Twelve indices.
 */
export function blendSeasonality(items, seasonality, weightKey = "forecast_7d") {
  const curves = seasonality.by_legal_entity;
  const weights = {};
  for (const item of items) {
    weights[item.vertical_id] =
      (weights[item.vertical_id] || 0) + item[weightKey];
  }
  const total = Object.values(weights).reduce(
    (running, value) => running + value,
    0,
  );
  if (!total) return new Array(12).fill(100);

  return Array.from({ length: 12 }, (_unused, month) =>
    Object.entries(weights).reduce(
      (running, [vertical, weight]) =>
        running + (curves[vertical]?.[month] ?? 100) * (weight / total),
      0,
    ),
  );
}

/**
 * The heaviest day in a day-of-week profile.
 *
 * Read off the profile the payload actually carries rather than typed into a
 * tile, so a different week shape reports a different peak. Ties go to the
 * earlier day, which only matters for a flat profile — where naming any day is
 * arbitrary anyway.
 *
 * @param {number[]} profile Seven factors, Monday first.
 * @returns {{ index: number, label: string, factor: number }}
 */
export function peakDay(profile) {
  let index = 0;
  for (let day = 1; day < profile.length; day += 1) {
    if (profile[day] > profile[index]) index = day;
  }
  return {
    index,
    label: WEEKDAY_LABELS[index] ?? `Day ${index + 1}`,
    factor: profile[index] ?? 1,
  };
}
