/**
 * Derive a Demand Forecasting payload from the workbook fixture.
 *
 * WHAT IS MEASURED AND WHAT IS MODELLED
 * The A1 sheet computes one of its six KPIs. The rest are constants somebody
 * typed. This file never blurs the two: `fixture.derivation` says which is
 * which, the payload carries it through, and the UI labels accordingly.
 *
 * THE FORECAST MODEL
 * Classical multiplicative decomposition, the ordinary retail one:
 *
 *     demand(d) = ADS x DOW(d) x seasonal(month(d)) x (1 + trend)^(d/365)
 *
 * Every factor traces to something:
 *   ADS       f01, per SKU, summed over the scope
 *   DOW       seven factors summing to `Constants` B7 = 7.45, which is
 *             exactly what f08 multiplies ADS by to get a week
 *   seasonal  twelve indices per vertical, from the monthly GMV profile,
 *             divided by the current month's index so today's factor is 1
 *             and the level stays where f01 put it
 *   trend     the A1 sheet's `Trend %` — a typed constant, compounded daily
 *
 * PREDICTION INTERVAL
 * Forecast error accumulates with the square root of the horizon, so
 *
 *     band(h) = yhat x z x (1 - accuracy/100) x sqrt(h)
 *
 * With the workbook's 92.4% accuracy and z = 1.645, the first period comes out
 * at ±12.5% — which is where the A1 spec's flat "±12%" came from. Written this
 * way the band widens with horizon, which a flat percentage cannot.
 *
 * NO ACTUALS LINE
 * The spec calls the main chart "actual vs AI". There are no actuals: the
 * workbook's only time series repeats one year twice, so it carries no history
 * and no trend. Rather than back-cast a line and let it read as measurement,
 * the series starts at today.
 */

import {
  DEFAULT_DEMAND_LEVERS,
  DEFAULT_DEMAND_QUERY,
  DEMAND_AGENT_ID,
  DEMAND_GRAINS,
  DEMAND_HORIZONS,
  DEMAND_LEVER_DEFINITIONS,
  SCHEMA_VERSION,
  normalizeDemandLevers,
  normalizeDemandQuery,
} from "./contract.js";
import { growthHistogram, topGroups } from "../../common/distributions.js";
import { buildDrilldown } from "./drilldown.js";
import { createDemandEngine, isDemandBaseline } from "./engine.js";

const ALL = "ALL";

/** Days in one period of each grain, and how many periods a horizon buys. */
const GRAIN_DAYS = {
  daily: 1,
  weekly: 7,
  monthly: 30.44,
  quarterly: 91.31,
  yearly: 365,
};

const GRAIN_PREFIX = {
  daily: "D",
  weekly: "W",
  monthly: "M",
  quarterly: "Q",
  yearly: "Y",
};

const DAYS_PER_MONTH = 30.44;

// -- scoping -----------------------------------------------------------

function matchesSearch(item, term) {
  const needle = term.trim().toLowerCase();
  if (!needle) return true;
  return (
    item.sku_id.toLowerCase().includes(needle) ||
    item.name.toLowerCase().includes(needle)
  );
}

export function scopeItems(items, query) {
  return items.filter((item) => {
    if (query.legal_entity_id !== ALL && item.vertical_id !== query.legal_entity_id) {
      return false;
    }
    if (query.category_group !== ALL && item.category_id !== query.category_group) {
      return false;
    }
    return matchesSearch(item, query.sku);
  });
}

function scopeStores(stores, query) {
  if (query.legal_entity_id === ALL) return stores;
  return stores.filter((store) => store.vertical_id === query.legal_entity_id);
}

const sum = (rows, key) => rows.reduce((total, row) => total + (row[key] ?? 0), 0);

/**
 * Blend a per-vertical constant across the scope, weighted by forecast.
 *
 * Accuracy, trend and the seasonality index exist only per vertical. Looking at
 * two verticals at once has to produce one number, and weighting by volume is
 * the only sensible way — an unweighted mean would let a tiny vertical move the
 * chain's reported accuracy as much as the largest one.
 */
function blend(items, referenceBy, key) {
  let weighted = 0;
  let weight = 0;
  for (const item of items) {
    const row = referenceBy[item.vertical_id];
    if (!row) continue;
    weighted += row[key] * item.forecast_7d;
    weight += item.forecast_7d;
  }
  return weight ? weighted / weight : 0;
}

/** The scope's seasonal curve, blended the same way. */
function blendSeasonality(items, seasonality) {
  const curves = seasonality.by_legal_entity;
  const weights = {};
  for (const item of items) {
    weights[item.vertical_id] = (weights[item.vertical_id] || 0) + item.forecast_7d;
  }
  const total = Object.values(weights).reduce((running, value) => running + value, 0);
  if (!total) return new Array(12).fill(100);

  return Array.from({ length: 12 }, (_unused, month) =>
    Object.entries(weights).reduce(
      (running, [vertical, weight]) =>
        running + (curves[vertical]?.[month] ?? 100) * (weight / total),
      0,
    ),
  );
}

// -- KPIs --------------------------------------------------------------

export function computeKpis(items, referenceBy) {
  return {
    forecast_next_7d: sum(items, "forecast_7d"),
    forecast_accuracy: blend(items, referenceBy, "accuracy_pct"),
    demand_trend: blend(items, referenceBy, "trend_pct"),
    stockout_risk_skus: items.filter((item) => item.is_stockout_risk).length,
    predicted_to_trend: items.filter((item) => item.is_trending).length,
    seasonality_index: blend(items, referenceBy, "seasonality_idx"),
    sku_count: items.length,
  };
}

// -- the forecast series ----------------------------------------------

/**
 * Demand for one day out, as the decomposition above.
 *
 * `curve` is the scope's twelve seasonal indices; dividing by the current
 * month's keeps the level where f01 put it, because f01 already evaluated each
 * SKU's seasonality at that month.
 */
function dailyDemand(ads, day, profile, curve, currentMonth, trendPct) {
  const dow = profile[((day % 7) + 7) % 7];
  const month = Math.floor(currentMonth + day / DAYS_PER_MONTH) % 12;
  const seasonal = curve[(month + 12) % 12] / curve[currentMonth % 12];
  const trend = (1 + trendPct / 100) ** (day / 365);
  return ads * dow * seasonal * trend;
}

export function buildForecastSeries(options) {
  const {
    ads,
    grain,
    horizonWeeks,
    profile,
    curve,
    currentMonth,
    trendPct,
    accuracyPct,
    intervalZ,
  } = options;

  const periodDays = GRAIN_DAYS[grain] ?? GRAIN_DAYS.weekly;
  const horizonDays = horizonWeeks * 7;
  const periods = Math.max(1, Math.round(horizonDays / periodDays));
  const prefix = GRAIN_PREFIX[grain] ?? "W";
  // Relative error per period, from the workbook's accuracy figure.
  const relativeError = Math.max(0, 1 - accuracyPct / 100);

  const points = [];
  let day = 0;

  for (let period = 1; period <= periods; period += 1) {
    const end = Math.round(period * periodDays);
    let forecast = 0;
    for (; day < end; day += 1) {
      forecast += dailyDemand(ads, day, profile, curve, currentMonth, trendPct);
    }

    const band = forecast * intervalZ * relativeError * Math.sqrt(period);
    points.push({
      key: `${prefix}+${period}`,
      label: `${prefix}+${period}`,
      actual: null,
      forecast,
      confidence_low: Math.max(0, forecast - band),
      confidence_high: forecast + band,
    });
  }

  return {
    grain,
    history_count: 0,
    horizon_weeks: horizonWeeks,
    horizon_label: `${horizonWeeks} ${horizonWeeks === 1 ? "week" : "weeks"}`,
    points,
    summary: [
      { id: "next_period", label: "Next period", value: points[0]?.forecast ?? 0, unit: "units" },
      {
        id: "horizon_total",
        label: "Horizon total",
        value: points.reduce((running, point) => running + point.forecast, 0),
        unit: "units",
      },
      { id: "interval", label: "Interval", value: `${Math.round(intervalZ * relativeError * 1000) / 10}% at P+1`, unit: null },
      { id: "peak", label: "Peak day", value: "Saturday ×1.35", unit: null },
    ],
  };
}

// -- dimensions --------------------------------------------------------

function groupBy(rows, key, label, valueKey) {
  const grouped = new Map();
  for (const row of rows) {
    const id = row[key];
    const bucket = grouped.get(id) || { id, label: label(row), forecast_units: 0, row_count: 0 };
    bucket.forecast_units += row[valueKey] ?? 0;
    bucket.row_count += 1;
    grouped.set(id, bucket);
  }
  return [...grouped.values()];
}

function withShare(rows) {
  const total = rows.reduce((running, row) => running + row.forecast_units, 0);
  return rows
    .map((row) => ({
      ...row,
      share_pct: total ? (row.forecast_units / total) * 100 : 0,
    }))
    .sort((a, b) => b.forecast_units - a.forecast_units);
}

export function computeDimensions(items, stores, seasonality, curve) {
  const categories = withShare(
    groupBy(items, "category_id", (row) => row.category_label, "forecast_7d"),
  );
  const storeRows = withShare(
    groupBy(stores, "store_id", (row) => row.name, "forecast_7d"),
  ).map((row) => {
    const source = stores.find((store) => store.store_id === row.id);
    return {
      ...row,
      legal_entity_id: source?.vertical_id ?? "",
      cluster: source?.cluster ?? "",
    };
  });

  const clusterRows = withShare(
    groupBy(stores, "cluster", (row) => row.cluster, "forecast_7d"),
  ).map((row) => ({ ...row, store_count: row.row_count }));

  const entityRows = withShare(
    groupBy(stores, "vertical_id", (row) => row.vertical_id, "forecast_7d"),
  ).map((row) => ({ ...row, store_count: row.row_count }));

  return {
    categories,
    stores: storeRows,
    clusters: clusterRows,
    legal_entities: entityRows,
    seasonality: curve.map((index, month) => ({
      month: seasonality.month_labels[month],
      index,
      current: month === seasonality.current_month_index,
    })),
    chain_total: sum(items, "forecast_7d"),
  };
}

// -- trending, details, actions ----------------------------------------

export function computeTrending(items, limit = 8) {
  return items
    .filter((item) => item.is_trending)
    .sort((a, b) => b.growth - a.growth)
    .slice(0, limit)
    .map((item) => ({
      sku_id: item.sku_id,
      sku_name: item.name,
      // Velocity above 1.0 is the uplift the workbook attributes to the SKU.
      predicted_uplift_pct: (item.growth - 1) * 100,
      signals: item.signals,
      ads_units_per_day: item.ads,
    }));
}

export function computeDetails(items, query, periodDays) {
  const sorted = [...items].sort((a, b) => b.forecast_7d - a.forecast_7d);
  const rows = sorted
    .slice(query.detail_offset, query.detail_offset + query.detail_limit)
    .map((item) => ({
      sku_id: item.sku_id,
      sku_name: item.name,
      category_id: item.category_id,
      category_label: item.category_label,
      ads_units_per_day: item.ads,
      forecast_7d_units: item.forecast_7d,
      forecast_units: item.ads * periodDays,
      trend_pct: (item.growth - 1) * 100,
      signals: item.signals,
      // The Inventory Risk state, unchanged. One SKU, one state, both boards.
      supply_state: item.state,
    }));

  return {
    total: items.length,
    offset: query.detail_offset,
    limit: query.detail_limit,
    forecast_total_units: sum(items, "forecast_7d"),
    rows,
  };
}

function computeSuggestedActions(items, kpis) {
  const reorder = items
    .filter((item) => item.is_stockout_risk)
    .sort((a, b) => b.forecast_7d - a.forecast_7d);
  const trending = items
    .filter((item) => item.is_trending)
    .sort((a, b) => b.growth - a.growth);

  return {
    primary: {
      title: "Cover the reorder zone",
      description: `${kpis.stockout_risk_skus} SKUs sit below their reorder point.`,
      // The existing button labels, kept: they are already translated, and the
      // hand-off they name has not changed.
      action_label: "Send to Replenishment",
    },
    secondary: {
      title: "Watch the risers",
      description: `${kpis.predicted_to_trend} SKUs are trending above baseline velocity.`,
      action_label: "Flag to Inventory Risk",
    },
    plan_preview: {
      title: "Worklist",
      description: "Highest-volume SKUs needing a decision first.",
      rows: [...reorder, ...trending].slice(0, 12).map((item) => ({
        sku_id: item.sku_id,
        sku_name: item.name,
        forecast_7d_units: item.forecast_7d,
        signal: item.is_stockout_risk ? "Below ROP" : "Trending",
        route: item.is_stockout_risk ? "Priority review" : "Standard",
      })),
    },
  };
}

// -- simulation --------------------------------------------------------

let cachedFormulas = null;
let cachedEngine = null;

function engineFor(formulas, weekFactor) {
  if (formulas !== cachedFormulas) {
    cachedEngine = createDemandEngine(formulas, weekFactor);
    cachedFormulas = formulas;
  }
  return cachedEngine;
}

/**
 * Baseline against scenario.
 *
 * Two of the four compared metrics move, and only those two: Forecast 7d runs
 * through f01/f08, and Stockout-risk SKUs through f03/f04/f05/f07. Accuracy and
 * Trending do not, because no formula in the workbook takes a lever anywhere
 * near them — see `unmodelled` below, which the panel reads to say so rather
 * than leaving a reader to wonder why a slider did nothing.
 */
export function computeSimulation(items, levers, applyLevers, referenceBy) {
  const merged = normalizeDemandLevers(levers);
  const applied = !isDemandBaseline(merged);
  const baseline = computeKpis(items, referenceBy);
  const scenario = applied
    ? computeKpis(items.map((item) => applyLevers(item, merged)), referenceBy)
    : baseline;

  const shape = (source) => ({
    forecast_next_7d: source.forecast_next_7d,
    stockout_risk_skus: source.stockout_risk_skus,
    forecast_accuracy_pct: source.forecast_accuracy,
    predicted_to_trend: source.predicted_to_trend,
  });

  return {
    applied,
    levers: DEMAND_LEVER_DEFINITIONS.map((lever) => ({ ...lever })),
    scenario_levers: merged,
    baseline: shape(baseline),
    scenario: shape(scenario),
    // Named so the simulator can grey them out honestly.
    unmodelled: ["forecast_accuracy_pct", "predicted_to_trend"],
  };
}

// -- assembly ----------------------------------------------------------

/**
 * Decompose one KPI tile, over exactly the rows the board is showing.
 *
 * It rebuilds the board rather than re-deriving a scope by hand, because three
 * of A1's six headline figures are per-vertical constants blended by forecast
 * weight — reproducing that blend here would be a second implementation of it,
 * and the two would eventually disagree. Taking the total off the finished KPI
 * card keeps the drawer and the tile reading the same number by construction.
 */
export function buildDrilldownFromFixture(fixture, query = {}, metricId, options = {}) {
  const board = buildDashboardFromFixture(fixture, query, options);
  const merged = normalizeDemandQuery({ ...DEFAULT_DEMAND_QUERY, ...query });
  const card = board.kpis.find((kpi) => kpi.id === metricId);

  return buildDrilldown(
    metricId,
    scopeItems(fixture.items, merged),
    scopeStores(fixture.stores, merged),
    card?.value ?? 0,
  );
}

export function buildDashboardFromFixture(fixture, query = {}, options = {}) {
  const merged = normalizeDemandQuery({ ...DEFAULT_DEMAND_QUERY, ...query });
  const referenceBy = Object.fromEntries(
    fixture.reference_by_vertical.map((row) => [row.legal_entity_id, row]),
  );

  const applyLevers = engineFor(fixture.formulas, fixture.constants.dow_sum);
  const levers = normalizeDemandLevers(options.levers ?? DEFAULT_DEMAND_LEVERS);
  const baselineItems = scopeItems(fixture.items, merged);
  const simulation = computeSimulation(
    baselineItems,
    levers,
    applyLevers,
    referenceBy,
  );

  const driveWholePage = options.driveWholePage !== false;
  const items =
    simulation.applied && driveWholePage
      ? baselineItems.map((item) => applyLevers(item, levers))
      : baselineItems;

  const stores = scopeStores(fixture.stores, merged);
  const kpis = computeKpis(items, referenceBy);
  const curve = blendSeasonality(items, fixture.seasonality);
  const periodDays = GRAIN_DAYS[merged.grain] ?? GRAIN_DAYS.weekly;

  const seriesOptions = {
    ads: sum(items, "ads"),
    grain: merged.grain,
    horizonWeeks: merged.horizon_weeks,
    profile: fixture.constants.dow_profile,
    curve,
    currentMonth: fixture.seasonality.current_month_index,
    trendPct: kpis.demand_trend,
    accuracyPct: kpis.forecast_accuracy,
    intervalZ: fixture.constants.interval_z,
  };
  const forecast = buildForecastSeries(seriesOptions);

  const categories =
    merged.legal_entity_id === ALL
      ? fixture.filter_options.categories
      : fixture.filter_options.categories.filter(
          (category) => category.legal_entity_id === merged.legal_entity_id,
        );
  const storeOptions =
    merged.legal_entity_id === ALL
      ? fixture.filter_options.stores
      : fixture.filter_options.stores.filter(
          (store) => store.legal_entity_id === merged.legal_entity_id,
        );

  return {
    schema_version: SCHEMA_VERSION,
    agent: DEMAND_AGENT_ID,
    as_of: fixture.generated_at,
    is_mock: fixture.is_mock,
    note: fixture.note,
    derivation: fixture.derivation,
    scope: merged,
    filter_options: {
      legal_entities: fixture.filter_options.legal_entities,
      categories,
      stores: storeOptions,
      grains: [...DEMAND_GRAINS],
      horizons_weeks: [...DEMAND_HORIZONS],
    },
    kpis: buildKpiCards(kpis, curve, fixture.derivation, items, forecast),
    forecast,
    // Same series, always weekly, so the confidence panel is comparable across
    // grain changes rather than re-scaling under the reader.
    confidence: buildForecastSeries({ ...seriesOptions, grain: "weekly" }),
    dimensions: computeDimensions(items, stores, fixture.seasonality, curve),
    trending_items: computeTrending(items),
    details: computeDetails(items, merged, periodDays),
    simulation: {
      ...simulation,
      baseline_forecast: buildForecastSeries({
        ...seriesOptions,
        ads: sum(baselineItems, "ads"),
      }),
    },
    scenarios: [],
    suggested_actions: computeSuggestedActions(items, kpis),
    reference_by_vertical: fixture.reference_by_vertical,
  };
}

/**
 * The six tiles.
 *
 * A sparkline is only drawn where a real series exists. Four of these KPIs are
 * single typed constants with no history behind them, and inventing a wiggle
 * for them would be decorating a number with a shape that means nothing.
 */
function buildKpiCards(kpis, curve, derivation, items = [], forecast = null) {
  const seasonalSpark = curve.slice(0, 7);

  /*
   * The four tiles that used to sit bare.
   *
   * The note above was right that a TREND could not be drawn for them — three
   * are typed constants and none has a dated source. But two of them do have a
   * real series behind them, and the other two have a real distribution:
   *
   *   accuracy   the prediction band widens as sqrt(horizon), and that width
   *              is computed FROM the accuracy figure — so the band is the
   *              honest picture of what 92.4% buys you further out.
   *   trend      the trend compounds into the forecast curve itself, which is
   *              a real derived series rather than a wiggle.
   *   stockout   cover = position / ADS, bucketed. Says whether the at-risk
   *              SKUs are barely under or already empty.
   *   trending   the growth index those SKUs were ranked on, bucketed.
   *
   * Nothing here is generated; `kind` names which of the two shapes each is.
   */
  const bandSpark = (forecast?.points ?? [])
    .map((point) => (point.confidence_high ?? 0) - (point.confidence_low ?? 0))
    .filter((width) => Number.isFinite(width));
  const forecastSpark = (forecast?.points ?? [])
    .map((point) => point.forecast ?? 0)
    .filter((value) => Number.isFinite(value));

  const cover = (item) => (item.ads > 0 ? item.position / item.ads : 0);
  const coverHistogram = (rows) => {
    const edges = [0.5, 2, 5, 8, 12, 15, 21, 30, Infinity];
    const counts = edges.map(() => 0);
    for (const row of rows) {
      const value = cover(row);
      const index = edges.findIndex((edge) => value <= edge);
      counts[index === -1 ? counts.length - 1 : index] += 1;
    }
    return counts;
  };
  const source = (id) =>
    derivation?.[id] === "typed-constant" ? "Workbook constant" : "Calculated";

  return [
    {
      id: "forecast_next_7d",
      label: "Forecast next 7 days",
      value: kpis.forecast_next_7d,
      unit: "units",
      comparison_label: source("forecast_next_7d"),
      direction: "flat",
      status: "neutral",
      sparkline: seasonalSpark,
    },
    {
      id: "forecast_accuracy",
      label: "Forecast accuracy",
      value: kpis.forecast_accuracy,
      unit: "%",
      comparison_label: source("forecast_accuracy"),
      direction: "flat",
      status: kpis.forecast_accuracy >= 90 ? "good" : "warn",
      sparkline: bandSpark,
      sparkline_kind: "series",
      sparkline_caption: "Prediction band width over the horizon",
    },
    {
      id: "demand_trend",
      label: "Demand trend",
      value: kpis.demand_trend,
      unit: "%",
      comparison_label: source("demand_trend"),
      direction: kpis.demand_trend >= 0 ? "up" : "down",
      status: kpis.demand_trend >= 0 ? "good" : "warn",
      sparkline: forecastSpark,
      sparkline_kind: "series",
      sparkline_caption: "Forecast curve the trend compounds into",
    },
    {
      id: "stockout_risk_skus",
      label: "Stockout-risk SKUs",
      value: kpis.stockout_risk_skus,
      unit: null,
      comparison_label: source("stockout_risk_skus"),
      direction: "flat",
      status: kpis.stockout_risk_skus ? "warn" : "good",
      sparkline: coverHistogram(items.filter((item) => item.is_stockout_risk)),
      sparkline_kind: "distribution",
      sparkline_caption: "Days of cover, at-risk SKUs",
    },
    {
      id: "predicted_to_trend",
      label: "Predicted to trend",
      value: kpis.predicted_to_trend,
      unit: null,
      comparison_label: source("predicted_to_trend"),
      direction: "up",
      status: "good",
      sparkline: growthHistogram(items.filter((item) => item.is_trending)),
      sparkline_kind: "distribution",
      sparkline_caption: "Growth index, trending SKUs",
    },
    {
      id: "seasonality_index",
      label: "Seasonality index",
      value: kpis.seasonality_index,
      unit: null,
      comparison_label: source("seasonality_index"),
      direction: kpis.seasonality_index >= 100 ? "up" : "down",
      status: "neutral",
      sparkline: seasonalSpark,
    },
  ];
}
