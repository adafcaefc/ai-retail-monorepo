import {
  DEMAND_AGENT_ID,
  DEMAND_GRAINS,
  DEMAND_HORIZONS,
  normalizeDemandDashboard,
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

export async function getMockDemandForecastingDashboard(inputQuery = {}) {
  const query = normalizeDemandQuery(inputQuery);
  const calculated = buildDemandDashboard(query);
  const { metrics } = calculated;
  const visibleRows = calculated.detailRows.slice(
    query.detail_offset,
    query.detail_offset + query.detail_limit,
  );

  return normalizeDemandDashboard({
    schema_version: 1,
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
    trending_items: calculated.trendingItems,
    details: {
      total: calculated.detailRows.length,
      offset: query.detail_offset,
      limit: query.detail_limit,
      rows: visibleRows,
    },
  });
}

