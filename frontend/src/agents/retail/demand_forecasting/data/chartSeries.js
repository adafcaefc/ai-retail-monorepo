/*
 * Build the two Demand Forecasting chart series from the backend's aggregated
 * 104W SKU × Store quantities. The backend filters rows and sums each weekly
 * column; this module only reshapes those weekly totals for the selected
 * display grain and Horizon.
 */

export const DOW_PROFILE = Object.freeze([0.85, 0.90, 0.95, 1.00, 1.15, 1.35, 1.25]);

const GRAIN_LABELS = Object.freeze({
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  quarterly: "Quarterly",
  yearly: "Yearly",
});

const EMPTY_POINT = {
  confidence_low: null,
  confidence_high: null,
};

const CHART_AXIS_PADDING = 0.10;
const CHART_AXIS_MIN_RANGE = 1;

function numeric(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

/**
 * Calculate a visible-data Y-axis domain for the demand line charts.
 *
 * The chart values are already filtered and aggregated by the backend. This
 * helper only looks at the points currently being rendered, adds breathing
 * room, and keeps the quantity axis non-negative. Confidence bounds are
 * opt-in because the Demand Outlook chart has no interval series.
 */
export function getDemandChartYAxisDomain(
  points = [],
  { includeConfidence = false } = {},
) {
  const values = [];
  const addValue = (value) => {
    if (value == null || value === "") return;
    const parsed = Number(value);
    if (Number.isFinite(parsed)) values.push(parsed);
  };
  points.forEach((item) => {
    [item?.actual, item?.forecast].forEach(addValue);
    if (includeConfidence) {
      [item?.confidence_low, item?.confidence_high].forEach(addValue);
    }
  });

  if (!values.length) return [0, 1];

  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const rawRange = rawMax - rawMin;
  const minimumRange = Math.max(
    CHART_AXIS_MIN_RANGE,
    Math.abs((rawMin + rawMax) / 2) * 0.10,
  );
  const dataRange = Math.max(rawRange, minimumRange);
  const center = (rawMin + rawMax) / 2;
  const expandedMin = rawRange < minimumRange
    ? center - dataRange / 2
    : rawMin;
  const expandedMax = rawRange < minimumRange
    ? center + dataRange / 2
    : rawMax;
  const padding = dataRange * CHART_AXIS_PADDING;
  const lower = Math.max(0, expandedMin - padding);
  const upper = expandedMax + padding;

  return [lower, upper > lower ? upper : lower + Math.max(1, padding)];
}

/**
 * Add a presentation-only transition value at the final actual and first
 * forecast points. No point or period is inserted into the source series.
 */
export function buildDemandTransitionData(points = []) {
  const data = (Array.isArray(points) ? points : []).map((item) => ({
    ...item,
    forecast_transition: null,
  }));
  const firstForecastIndex = data.findIndex(
    (item) => item.actual == null && item.forecast != null,
  );
  if (firstForecastIndex <= 0) {
    return {
      data,
      lastActualKey: null,
      firstForecastKey: firstForecastIndex === 0 ? data[0]?.key : null,
    };
  }

  let lastActualIndex = firstForecastIndex - 1;
  while (lastActualIndex >= 0 && data[lastActualIndex].actual == null) {
    lastActualIndex -= 1;
  }
  if (lastActualIndex < 0) {
    return { data, lastActualKey: null, firstForecastKey: data[firstForecastIndex].key };
  }

  data[lastActualIndex].forecast_transition = data[lastActualIndex].actual;
  data[firstForecastIndex].forecast_transition = data[firstForecastIndex].forecast;
  return {
    data,
    lastActualKey: data[lastActualIndex].key,
    firstForecastKey: data[firstForecastIndex].key,
  };
}

function weeklyValue(source, type, week) {
  return numeric(source?.[`${type}_w${week}`]);
}

function point(label, value, type) {
  return {
    ...EMPTY_POINT,
    key: label,
    label,
    actual: type === "actual" ? value : null,
    forecast: type === "forecast" ? value : null,
  };
}

function sumWeeks(source, type, weeks) {
  return weeks.reduce((total, week) => total + weeklyValue(source, type, week), 0);
}

function range(start, end, step = start <= end ? 1 : -1) {
  const values = [];
  for (let value = start; step > 0 ? value <= end : value >= end; value += step) {
    values.push(value);
  }
  return values;
}

function unavailableSeries(grain, horizonWeeks, source = null) {
  return {
    grain,
    horizon_weeks: horizonWeeks,
    horizon_label: `${horizonWeeks} weeks`,
    history_count: 0,
    points: [],
    summary: [],
    source: source?.source || null,
  };
}

function splitWeek(total, profile = DOW_PROFILE) {
  const weights = profile.map((value) => numeric(value)).filter((value) => value >= 0);
  const denominator = weights.reduce((sum, value) => sum + value, 0);
  if (!weights.length || denominator <= 0) {
    return Array.from({ length: 7 }, () => total / 7);
  }

  const values = [];
  let allocated = 0;
  weights.forEach((weight, index) => {
    if (index === weights.length - 1) {
      values.push(total - allocated);
    } else {
      const value = total * weight / denominator;
      values.push(value);
      allocated += value;
    }
  });
  return values;
}

function dailyPoints(source, profile) {
  const actual = splitWeek(weeklyValue(source, "actual", 1), profile);
  const forecast = splitWeek(weeklyValue(source, "forecast", 1), profile);
  return [
    ...actual.map((value, index) => point(`D-${7 - index}`, value, "actual")),
    ...forecast.map((value, index) => point(`D+${index + 1}`, value, "forecast")),
  ];
}

function weeklyPoints(source, horizonWeeks, historyWeeks) {
  const actual = range(historyWeeks, 1).map((week) => point(`W-${week}`, weeklyValue(source, "actual", week), "actual"));
  const forecast = range(1, horizonWeeks).map((week) => point(`W+${week}`, weeklyValue(source, "forecast", week), "forecast"));
  return { history_count: actual.length, points: [...actual, ...forecast] };
}

function groupedPoints(source, groups, type, prefix) {
  return groups.map((weeks, index) => point(
    `${prefix}${type === "actual" ? "-" : "+"}${type === "actual" ? groups.length - index : index + 1}`,
    sumWeeks(source, type, weeks),
    type,
  ));
}

function monthlyPoints(source, horizonWeeks) {
  const actualGroups = [
    [16, 15, 14, 13],
    [12, 11, 10, 9],
    [8, 7, 6, 5],
    [4, 3, 2, 1],
  ];
  const forecastGroups = Array.from({ length: horizonWeeks / 4 }, (_, index) =>
    range(index * 4 + 1, index * 4 + 4),
  );
  return {
    history_count: actualGroups.length,
    points: [
      ...groupedPoints(source, actualGroups, "actual", "M"),
      ...groupedPoints(source, forecastGroups, "forecast", "M"),
    ],
  };
}

function quarterlyPoints(source, horizonWeeks) {
  if (horizonWeeks !== 16) return unavailableSeries("quarterly", horizonWeeks, source);
  const actualGroups = [
    range(52, 40),
    range(39, 27),
    range(26, 14),
    range(13, 1),
  ];
  return {
    history_count: actualGroups.length,
    points: [
      ...groupedPoints(source, actualGroups, "actual", "Q"),
      point("Q+1", sumWeeks(source, "forecast", range(1, 13)), "forecast"),
    ],
  };
}

function summary(points) {
  const forecast = points
    .filter((item) => item.forecast != null)
    .map((item) => item.forecast);
  return [
    {
      id: "next_period",
      label: "Next period",
      value: forecast[0] ?? 0,
      unit: "units",
    },
    {
      id: "horizon_total",
      label: "Horizon total",
      value: forecast.reduce((total, value) => total + value, 0),
      unit: "units",
    },
  ];
}

export function isDemandGrainEnabled(grain, horizonWeeks) {
  if (grain === "yearly") return false;
  if (grain === "quarterly") return horizonWeeks === 16;
  return ["daily", "weekly", "monthly"].includes(grain);
}

export function buildDemandChartSeries(
  source,
  { grain = "weekly", horizonWeeks = 8, historyWeeks = 4, dowProfile = DOW_PROFILE } = {},
) {
  if (!source || !isDemandGrainEnabled(grain, horizonWeeks)) {
    return unavailableSeries(grain, horizonWeeks, source);
  }

  let built;
  if (grain === "daily") {
    built = { history_count: 7, points: dailyPoints(source, dowProfile) };
  } else if (grain === "weekly") {
    built = weeklyPoints(source, horizonWeeks, historyWeeks);
  } else if (grain === "monthly") {
    built = monthlyPoints(source, horizonWeeks);
  } else {
    built = quarterlyPoints(source, horizonWeeks);
  }

  return {
    grain,
    horizon_weeks: horizonWeeks,
    horizon_label: `${horizonWeeks} weeks`,
    history_count: built.history_count,
    points: built.points,
    summary: summary(built.points),
    source: source.source || "synthetic.demand_store_sku_104w",
    subtitle: grain === "daily"
      ? "Based on current limited 52-week synthetic demand dataset · Daily values derived from the weekly demand profile"
      : "Based on current limited 52-week synthetic demand dataset",
  };
}

export function buildConfidenceSeries(source, horizonWeeks, accuracyPct, intervalZ) {
  const base = buildDemandChartSeries(source, {
    grain: "weekly",
    horizonWeeks,
    historyWeeks: 12,
  });
  let forecastIndex = 0;
  const relativeError = Math.max(0, 1 - numeric(accuracyPct, 0) / 100);
  const z = numeric(intervalZ, 1.645);
  return {
    ...base,
    points: base.points.map((item) => {
      if (item.forecast == null) return item;
      forecastIndex += 1;
      const band = item.forecast * z * relativeError * Math.sqrt(forecastIndex);
      return {
        ...item,
        confidence_low: Math.max(0, item.forecast - band),
        confidence_high: item.forecast + band,
      };
    }),
  };
}

export function chartSourceColumns() {
  return [
    ...range(52, 1).map((week) => `actual_w${week}`),
    ...range(1, 52).map((week) => `forecast_w${week}`),
  ];
}

export { GRAIN_LABELS };
