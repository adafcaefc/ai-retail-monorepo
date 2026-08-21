/**
 * Derive a Demand Forecasting payload from the workbook fixture.
 *
 * WHAT IS MEASURED AND WHAT IS MODELLED
 * The live Demand Trend KPI is supplied by the backend's aggregate query over
 * `synthetic.demand_store_sku_32w`. The remaining forecast-model trend stays
 * separate below so this focused KPI change does not alter the forecast chart.
 * The fixture has no synthetic SQL aggregate, so its Demand Trend is shown as
 * unavailable rather than falling back to the old workbook reference.
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
 *   trend     the legacy A1 `Trend %`, used only by the existing chart model
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
import {
  blend,
  blendSeasonality,
  dailyDemand,
  peakDay,
} from "../../common/demandModel.js";
import { buildDrilldown } from "./drilldown.js";
import { createDemandEngine, isDemandBaseline } from "./engine.js";
import {
  buildConfidenceSeries,
  buildDemandChartSeries,
} from "./chartSeries.js";

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

// -- KPIs --------------------------------------------------------------

/**
 * The six A1 headline tiles, over exactly the rows in scope.
 *
 * `seasonality_index` is supplied by the backend from the current v8.5
 * `ENGINE_STORE.Seas` aggregate. It is deliberately not read from
 * `reference_by_vertical` or derived from the monthly seasonality curve used
 * by the chart.
 */
export function computeKpis(
  items,
  referenceBy,
  seasonality,
  calculatedDemandTrend = null,
  seasonalityIndex = null,
) {
  return {
    forecast_next_7d: sum(items, "forecast_7d"),
    forecast_accuracy: blend(items, referenceBy, "accuracy_pct"),
    // This is the card value. It is intentionally not blended from
    // reference_by_vertical.trend_pct.
    demand_trend: calculatedDemandTrend?.trend_pct ?? null,
    // The chart remains on its existing typed model until chart integration.
    forecast_model_trend: blend(items, referenceBy, "trend_pct"),
    stockout_risk_skus: items.filter((item) => item.is_stockout_risk).length,
    predicted_to_trend: items.filter((item) => item.is_trending).length,
    seasonality_index: seasonalityIndex,
    sku_count: items.length,
  };
}

// -- the forecast series ----------------------------------------------

// TEMPORARY: there is no real sales history anywhere in this system yet.
// These 12 numbers are made up, on purpose kept as one flat literal list
// (not a formula) so this line is trivial to find and delete once real
// history is wired in. Applied as a multiplier on the same real ads-based
// baseline the forecast side already uses, oldest first.
const FAKE_HISTORY_MULTIPLIERS = [
  0.91, 1.04, 0.97, 1.08, 0.95, 1.12, 1.02, 0.89, 1.06, 0.98, 1.1, 1.0,
];

// TEMPORARY: same reasoning as FAKE_HISTORY_MULTIPLIERS above, applied to the
// forward-looking side instead. Daily grain already varies for real -- the
// day-of-week profile swings day to day -- and monthly/yearly grain varies
// for real as the seasonal curve moves from month to month. Weekly and
// quarterly sit in between: dow averages out over 7 summed days, and the
// seasonal curve barely shifts within a handful of weeks or a couple of
// quarters, so `dailyDemand` summed over those grains comes out nearly flat.
// This wave restores that period-to-period wiggle (same amplitude/frequency
// as the mockup's own genSeriesP() forecast wave -- resources/AI_360_Retail
// _Suite_v8.2_General_9Agents 20260806.html) until a real intra-period demand
// signal exists to drive it instead. `phase` continues the same sine phase
// history's FAKE_HISTORY_MULTIPLIERS implicitly ends on, so the line reads as
// one continuous wiggle through the actual/forecast boundary, not a seam.
// Period 1 is left flat (no wave) on purpose: it's the same "next 7 days"
// figure the `forecast_next_7d` KPI tile, the "Next period" summary stat, and
// (once scoped) `dimensions.chain_total` all reconcile to -- see the data
// contract's reconciliation note in ./README.md. A cosmetic wiggle there
// would make the chart's first point visibly disagree with numbers shown
// elsewhere on the same dashboard for the same quantity.
function illustrativeForecastWave(grain, phase, period) {
  if (period <= 1) return 1;
  if (grain === "weekly") return 1 + 0.1 * Math.sin(phase / 2.3);
  if (grain === "quarterly") return 1 + 0.08 * Math.sin(phase / 1.5);
  return 1;
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

  // Illustrative history: same real ads-based baseline as the forecast below.
  // Daily grain uses that formula untouched -- no fabricated wave. Coarser
  // grains still scale it by the flat fake-multiplier list above, until real
  // history exists at those grains too. See FAKE_HISTORY_MULTIPLIERS.
  const historyPoints = FAKE_HISTORY_MULTIPLIERS.map((multiplier, i) => {
    const index = FAKE_HISTORY_MULTIPLIERS.length - i; // counts down to 1
    // Rounded to whole days, same as the forecast loop's own period
    // boundaries below (`Math.round(period * periodDays)`) -- periodDays is
    // fractional for monthly/quarterly grains, and dailyDemand's day-of-week
    // lookup indexes an array, so a fractional `day` silently reads
    // `undefined` and poisons the sum to NaN.
    const endDay = -Math.round((index - 1) * periodDays);
    const startDay = -Math.round(index * periodDays);
    let total = 0;
    for (let d = startDay; d < endDay; d += 1) {
      total += dailyDemand(ads, d, profile, curve, currentMonth, trendPct);
    }
    const actual = Math.round(total * (grain === "daily" ? 1 : multiplier));
    const isBoundary = index === 1; // the history point right before day 0
    return {
      key: `${prefix}-${index}`,
      label: `${prefix}-${index}`,
      actual,
      // The boundary point also carries `forecast` equal to `actual`, so the
      // dashed forecast line starts exactly where the solid actual line ends
      // -- one continuous line with a style change, not a gap. Mirrors the
      // mockup's own lineBand(), which prepends the last actual point onto
      // the forecast path for the same reason.
      forecast: isBoundary ? actual : null,
      confidence_low: null,
      confidence_high: null,
    };
  });

  const points = [];
  let day = 0;

  for (let period = 1; period <= periods; period += 1) {
    const end = Math.round(period * periodDays);
    let forecast = 0;
    for (; day < end; day += 1) {
      forecast += dailyDemand(ads, day, profile, curve, currentMonth, trendPct);
    }
    forecast *= illustrativeForecastWave(grain, FAKE_HISTORY_MULTIPLIERS.length + period, period);

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

  const peak = peakDay(profile);

  return {
    grain,
    history_count: historyPoints.length,
    horizon_weeks: horizonWeeks,
    horizon_label: `${horizonWeeks} ${horizonWeeks === 1 ? "week" : "weeks"}`,
    points: [...historyPoints, ...points],
    summary: [
      { id: "next_period", label: "Next period", value: points[0]?.forecast ?? 0, unit: "units" },
      {
        id: "horizon_total",
        label: "Horizon total",
        value: points.reduce((running, point) => running + point.forecast, 0),
        unit: "units",
      },
      { id: "interval", label: "Interval", value: `${Math.round(intervalZ * relativeError * 1000) / 10}% at P+1`, unit: null },
      { id: "peak", label: "Peak day", value: `${peak.label} ×${peak.factor}`, unit: null },
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
    .map((item) => {
      const viral = item.signals.includes("viral");
      return {
        sku_id: item.sku_id,
        sku_name: item.name,
        // Uplift = growth + viral signal, per the A1 spec/mockup:
        // (growth-1)*100, plus a flat 18-point bump when the SKU is viral.
        predicted_uplift_pct: (item.growth - 1) * 100 + (viral ? 18 : 0),
        signals: item.signals,
        ads_units_per_day: item.ads,
      };
    });
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
export function computeSimulation(
  items,
  levers,
  applyLevers,
  referenceBy,
  seasonality,
  calculatedDemandTrend = null,
  seasonalityIndex = null,
) {
  const merged = normalizeDemandLevers(levers);
  const applied = !isDemandBaseline(merged);
  const baseline = computeKpis(
    items,
    referenceBy,
    seasonality,
    calculatedDemandTrend,
    seasonalityIndex,
  );
  const scenario = applied
    ? computeKpis(
      items.map((item) => applyLevers(item, merged)),
      referenceBy,
      seasonality,
      calculatedDemandTrend,
      seasonalityIndex,
    )
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
  const baselineItems = scopeItems(fixture.items, merged);
  const levers = normalizeDemandLevers(options.levers ?? DEFAULT_DEMAND_LEVERS);
  const applyLevers = engineFor(fixture.formulas, fixture.constants.dow_sum);
  const items =
    options.driveWholePage !== false && !isDemandBaseline(levers)
      ? baselineItems.map((item) => applyLevers(item, levers))
      : baselineItems;

  return buildDrilldown(
    metricId,
    items,
    scopeStores(fixture.stores, merged),
    card?.value ?? 0,
  );
}

/**
 * Resolve the header value supplied by the backend.
 *
 * The standalone bundle has no SQL endpoint, so its checked-in rows provide a
 * deliberately explicit compatibility source. The live/API path always wins
 * with the backend object and never reaches this fallback. In either case the
 * monthly GMV curve and `reference_by_vertical` are not KPI inputs.
 */
export function resolveSeasonalityIndex(payload, scopedItems) {
  if (Object.prototype.hasOwnProperty.call(payload ?? {}, "seasonality_index")) {
    const source = payload.seasonality_index;
    const rawValue = source && typeof source === "object"
      ? source.value
      : source;
    if (rawValue == null) return null;
    const value = Number(rawValue);
    return Number.isFinite(value) ? value : null;
  }

  if (!payload?.is_mock) return null;
  const values = (scopedItems ?? [])
    .map((item) => Number(item?.seasonality))
    .filter((value) => Number.isFinite(value));
  if (!values.length) return null;
  return (values.reduce((total, value) => total + value, 0) / values.length) * 100;
}

export function buildDashboardFromFixture(fixture, query = {}, options = {}) {
  const merged = normalizeDemandQuery({ ...DEFAULT_DEMAND_QUERY, ...query });
  const calculatedDemandTrend = fixture.demand_trend || null;
  const referenceBy = Object.fromEntries(
    fixture.reference_by_vertical.map((row) => [row.legal_entity_id, row]),
  );

  const applyLevers = engineFor(fixture.formulas, fixture.constants.dow_sum);
  const levers = normalizeDemandLevers(options.levers ?? DEFAULT_DEMAND_LEVERS);
  const baselineItems = scopeItems(fixture.items, merged);
  const seasonalityIndex = resolveSeasonalityIndex(fixture, baselineItems);
  const simulation = computeSimulation(
    baselineItems,
    levers,
    applyLevers,
    referenceBy,
    fixture.seasonality,
    calculatedDemandTrend,
    seasonalityIndex,
  );

  const driveWholePage = options.driveWholePage !== false;
  const items =
    simulation.applied && driveWholePage
      ? baselineItems.map((item) => applyLevers(item, levers))
      : baselineItems;

  const stores = scopeStores(fixture.stores, merged);
  const kpis = computeKpis(
    items,
    referenceBy,
    fixture.seasonality,
    calculatedDemandTrend,
    seasonalityIndex,
  );
  const curve = blendSeasonality(items, fixture.seasonality);
  const periodDays = GRAIN_DAYS[merged.grain] ?? GRAIN_DAYS.weekly;

  const demandForecastSeries = options.demandForecastSeries
    || fixture.demand_forecast_series
    || null;
  if (options.requireDemandForecastSeries && !demandForecastSeries) {
    throw new Error("Demand Forecasting API returned no 104W chart series.");
  }

  const seriesOptions = {
    ads: sum(items, "ads"),
    grain: merged.grain,
    horizonWeeks: merged.horizon_weeks,
    profile: fixture.constants.dow_profile,
    curve,
    currentMonth: fixture.seasonality.current_month_index,
    trendPct: kpis.forecast_model_trend,
    accuracyPct: kpis.forecast_accuracy,
    intervalZ: fixture.constants.interval_z,
  };
  const forecast = demandForecastSeries
    ? buildDemandChartSeries(demandForecastSeries, {
      grain: merged.grain,
      horizonWeeks: merged.horizon_weeks,
      dowProfile: fixture.constants.dow_profile,
    })
    : buildForecastSeries(seriesOptions);

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
  const categoryScopedStoreOptions = storeOptions.filter((store) => (
    merged.category_group === ALL
      || !Array.isArray(store.category_ids)
      || store.category_ids.includes(merged.category_group)
  ));

  return {
    schema_version: SCHEMA_VERSION,
    agent: DEMAND_AGENT_ID,
    as_of: fixture.generated_at,
    is_mock: fixture.is_mock,
    note: fixture.note,
    scope_limitations: Array.isArray(fixture.scope_limitations)
      ? fixture.scope_limitations
      : [],
    derivation: fixture.derivation,
    scope: merged,
    filter_options: {
      legal_entities: fixture.filter_options.legal_entities,
      categories,
      stores: categoryScopedStoreOptions,
      grains: [...DEMAND_GRAINS],
      horizons_weeks: [...DEMAND_HORIZONS],
    },
    kpis: buildKpiCards(
      kpis,
      curve,
      fixture.derivation,
      items,
      forecast,
      calculatedDemandTrend,
    ),
    forecast,
    // Same SQL-backed weekly source, always weekly, so the confidence panel is
    // comparable across grain changes rather than re-scaling under the reader.
    confidence: demandForecastSeries
      ? buildConfidenceSeries(
        demandForecastSeries,
        merged.horizon_weeks,
        kpis.forecast_accuracy,
        fixture.constants.interval_z,
      )
      : buildForecastSeries({ ...seriesOptions, grain: "weekly" }),
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
    demand_trend: calculatedDemandTrend,
    demand_forecast_series: demandForecastSeries,
    seasonality_index: fixture.seasonality_index ?? null,
  };
}

/**
 * The six tiles.
 *
 * A sparkline is only drawn where a real series exists. The live Demand Trend
 * supplies its filtered SQL aggregate series; the remaining typed constants
 * have no history behind them, so inventing a wiggle for them would be
 * decorating a number with a shape that means nothing.
 */
function buildKpiCards(
  kpis,
  curve,
  derivation,
  items = [],
  forecast = null,
  calculatedDemandTrend = null,
) {
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
  const source = (id) => {
    if (id === "demand_trend") {
      return calculatedDemandTrend?.trend_pct == null ? "Unavailable" : "Calculated";
    }
    if (id === "forecast_accuracy") {
      return "Calculated";
    }
    return derivation?.[id] === "typed-constant" ? "Workbook constant" : "Calculated";
  };

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
      direction: kpis.demand_trend == null
        ? "flat"
        : kpis.demand_trend >= 0 ? "up" : "down",
      status: kpis.demand_trend == null
        ? "neutral"
        : kpis.demand_trend >= 0 ? "good" : "warn",
      // SQL aggregates actual W-4..W-1 followed by forecast W+1..W+4 for the
      // selected scope. This is a series, not the old workbook Trend model.
      sparkline: kpis.demand_trend == null
        ? []
        : calculatedDemandTrend?.sparkline ?? [],
      sparkline_kind: "series",
      sparkline_caption: "Actual W-4 to W-1 and forecast W+1 to W+4",
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
