import {
  DEMAND_AGENT_ID,
  DEMAND_GRAINS,
  DEMAND_HORIZONS,
  DEFAULT_DEMAND_LEVERS,
  DEMAND_LEVER_DEFINITIONS,
  normalizeDemandDashboard,
  normalizeDemandLevers,
  normalizeDemandQuery,
} from "./contract.js";
import { buildDemandDashboard } from "./mockCalculations.js";
import { REFERENCE_BASELINE } from "./mockDataset.js";

const KPI_PATTERNS = {
  forecast: [0.91, 0.94, 0.93, 0.97, 1, 1.02, 1.04],
  accuracy: [0.97, 0.982, 0.988, 0.993, 0.997, 1, 1],
  trend: [0.45, 0.58, 0.72, 0.82, 0.91, 0.96, 1],
  risk: [1.12, 1.09, 1.07, 1.05, 1.03, 1.01, 1],
  trending: [0.78, 0.82, 0.87, 0.91, 0.95, 0.98, 1],
  seasonality: [0.91, 0.94, 0.97, 1, 1.03, 1.08, 1],
};

function spark(value, pattern) {
  return pattern.map((factor) => Math.round(value * factor * 10) / 10);
}

function simulationMetrics(metrics) {
  return {
    forecast_next_7d: metrics.next7,
    stockout_risk_skus: metrics.risk,
    forecast_accuracy_pct: metrics.accuracy,
    predicted_to_trend: metrics.trending,
  };
}

function isApplied(levers) {
  return Object.keys(DEFAULT_DEMAND_LEVERS).some(
    (key) => levers[key] !== DEFAULT_DEMAND_LEVERS[key],
  );
}

export async function getMockDemandForecastingDashboard(inputQuery = {}, inputLevers = {}) {
  const query = normalizeDemandQuery(inputQuery);
  const levers = normalizeDemandLevers(inputLevers);
  const calculated = buildDemandDashboard(query, levers);
  const { metrics } = calculated;
  const visibleRows = calculated.detailRows.slice(
    query.detail_offset,
    query.detail_offset + query.detail_limit,
  );

  return normalizeDemandDashboard({
    schema_version: 2,
    agent: DEMAND_AGENT_ID,
    as_of: "2026-08-06T03:00:00Z",
    is_mock: true,
    note: "Synthetic AI Retail 360 demonstration data.",
    scope: query,
    filter_options: {
      ...calculated.options,
      grains: DEMAND_GRAINS,
      horizons_weeks: DEMAND_HORIZONS,
    },
    kpis: [
      {
        id: "forecast_next_7d",
        label: "Forecast (next 7d)",
        value: metrics.next7,
        unit: "units",
        comparison_label: "AI demand signal",
        direction: "up",
        status: "good",
        sparkline: spark(metrics.next7, KPI_PATTERNS.forecast),
      },
      {
        id: "forecast_accuracy",
        label: "Forecast accuracy",
        value: metrics.accuracy,
        unit: "%",
        comparison_label: "8-week backtest",
        direction: metrics.accuracy >= 90 ? "up" : "down",
        status: metrics.accuracy >= 90 ? "good" : "warn",
        sparkline: spark(metrics.accuracy, KPI_PATTERNS.accuracy),
      },
      {
        id: "demand_trend",
        label: "Demand trend",
        value: metrics.trend,
        unit: "%",
        comparison_label: "next 7d vs prior 7d",
        direction: metrics.trend >= 0 ? "up" : "down",
        status: metrics.trend >= 0 ? "good" : "warn",
        sparkline: spark(metrics.trend, KPI_PATTERNS.trend),
      },
      {
        id: "stockout_risk_skus",
        label: "Stockout-risk SKUs",
        value: metrics.risk,
        unit: "SKUs",
        comparison_label: "position below ROP",
        direction: "down",
        status: metrics.risk ? "warn" : "good",
        sparkline: spark(metrics.risk, KPI_PATTERNS.risk),
      },
      {
        id: "predicted_to_trend",
        label: "Predicted to trend",
        value: metrics.trending,
        unit: "SKUs",
        comparison_label: "viral and growth signals",
        direction: "up",
        status: "good",
        sparkline: spark(metrics.trending, KPI_PATTERNS.trending),
      },
      {
        id: "seasonality_index",
        label: "Seasonality index",
        value: metrics.seasonality,
        unit: "index",
        comparison_label: "100 = average month",
        direction: metrics.seasonality >= 100 ? "up" : "flat",
        status: "neutral",
        sparkline: spark(metrics.seasonality, KPI_PATTERNS.seasonality),
      },
    ],
    forecast: {
      grain: query.grain,
      history_count: query.grain === "weekly" ? 12 : 0,
      horizon_weeks: query.horizon_weeks,
      horizon_label: `${query.horizon_weeks}-week AI forecast`,
      points: calculated.forecastPoints,
      summary: [
        { id: "next_7d", label: "NEXT 7D", value: metrics.next7, unit: "units" },
        { id: "accuracy", label: "ACCURACY", value: metrics.accuracy, unit: "%" },
        { id: "trend", label: "TREND", value: metrics.trend, unit: "%" },
        { id: "peak", label: "PEAK", value: REFERENCE_BASELINE.peak, unit: null },
      ],
    },
    confidence: {
      grain: "weekly",
      history_count: 12,
      horizon_weeks: query.horizon_weeks,
      horizon_label: `12 weeks actual · ${query.horizon_weeks} weeks forecast · 88–112% confidence envelope`,
      points: calculated.confidencePoints,
      summary: [],
    },
    dimensions: calculated.dimensions,
    trending_items: calculated.trendingItems,
    details: {
      total: calculated.detailRows.length,
      offset: query.detail_offset,
      limit: query.detail_limit,
      forecast_total_units: calculated.detailForecastTotal,
      rows: visibleRows,
    },
    simulation: {
      applied: isApplied(levers),
      levers: DEMAND_LEVER_DEFINITIONS,
      scenario_levers: levers,
      baseline: simulationMetrics(calculated.baselineMetrics),
      scenario: simulationMetrics(calculated.metrics),
      baseline_forecast: {
        grain: query.grain,
        history_count: query.grain === "weekly" ? 12 : 0,
        horizon_weeks: query.horizon_weeks,
        horizon_label: "Baseline forecast",
        points: calculated.baselineForecastPoints,
        summary: [],
      },
    },
    scenarios: [],
    suggested_actions: {
      primary: {
        title: "Send 7-day forecast basket to Replenishment",
        description: `${metrics.next7.toLocaleString("en-US")} units across ${calculated.detailRows.length} SKUs · accuracy ${metrics.accuracy.toFixed(1)}% · includes ${metrics.trending} trending SKUs flagged for uplift.`,
        action_label: "Send to Replenishment",
      },
      secondary: {
        title: `Raise safety stock on ${metrics.risk} stockout-risk SKUs`,
        description: "Forecast exceeds supply within lead time. Recommend one additional safety day, then recalculate replenishment.",
        action_label: "Flag to Inventory Risk",
      },
      plan_preview: {
        title: "Generate forecast basket",
        description: "Read-only preview of the highest forecast lines. Backend generation and handoff are pending.",
        rows: calculated.detailRows.slice(0, 10).map((row) => ({
          sku_id: row.sku_id,
          sku_name: row.sku_name,
          forecast_7d_units: row.forecast_7d_units,
          signal: row.signals[0] || "stable",
          route: row.supply_state === "Healthy" ? "Standard" : "Priority review",
        })),
      },
    },
  });
}
