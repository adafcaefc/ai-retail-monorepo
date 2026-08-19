/**
 * Presentation helpers for the Demand Forecasting What-If comparison.
 *
 * The simulator compares unlike metrics on one chart, so the chart uses an
 * index rather than the KPI's displayed value. The baseline is always 100;
 * a zero baseline has no mathematically meaningful ratio and is represented
 * by a missing scenario index instead of an invented value.
 */

export const DEMAND_SIMULATION_METRICS = Object.freeze([
  ["forecast_next_7d", "Forecast 7d", "number"],
  ["stockout_risk_skus", "Stockout SKUs", "number"],
  ["forecast_accuracy_pct", "Accuracy %", "percent"],
  ["predicted_to_trend", "Trending", "number"],
]);

const DEFAULT_AXIS_DOMAIN = Object.freeze([0, 100]);
const AXIS_STEP = 10;

function finite(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Return a non-negative normalized scenario index, or null when the ratio is
 * undefined/invalid. Demand KPI metrics have a non-negative domain, so a
 * negative scenario value is clipped at zero defensively.
 */
export function normalizedDemandScenarioIndex(baseline, scenario) {
  const base = finite(baseline);
  const value = finite(scenario);
  if (base === null || value === null || base <= 0) return null;
  return Math.max(0, (value / base) * 100);
}

/**
 * Build the exact rows consumed by the paired Baseline/Scenario bar chart.
 */
export function buildDemandComparisonChartData(simulation, translate = (label) => label) {
  return DEMAND_SIMULATION_METRICS.map(([id, label]) => ({
    id,
    label: translate(label),
    baseline: 100,
    scenario: normalizedDemandScenarioIndex(
      simulation?.baseline?.[id],
      simulation?.scenario?.[id],
    ),
  }));
}

/**
 * Calculate a useful Y-axis domain from the values actually plotted.
 *
 * Values are rounded out to ten-unit boundaries. A value exactly on a
 * boundary gets one interval of breathing room on that side. The index is a
 * non-negative domain, so the lower bound is never allowed below zero.
 */
export function getDemandComparisonYAxisDomain(values) {
  const plotted = (Array.isArray(values) ? values : [])
    .map(finite)
    .filter((value) => value !== null);

  if (!plotted.length) return [...DEFAULT_AXIS_DOMAIN];

  const rawMin = Math.min(...plotted);
  const rawMax = Math.max(...plotted);
  let axisMin = Math.floor(rawMin / AXIS_STEP) * AXIS_STEP;
  let axisMax = Math.ceil(rawMax / AXIS_STEP) * AXIS_STEP;

  if (rawMin === axisMin) axisMin -= AXIS_STEP;
  if (rawMax === axisMax) axisMax += AXIS_STEP;

  axisMin = Math.max(0, axisMin);
  if (axisMax <= axisMin) axisMax = axisMin + AXIS_STEP;

  return [axisMin, axisMax];
}

