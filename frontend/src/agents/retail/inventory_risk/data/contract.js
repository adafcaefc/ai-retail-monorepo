/**
 * Inventory Risk (Agent 2) dashboard data contract.
 *
 * This is the single shape both data sources must produce: the local fixture
 * today, and `GET /api/html/dashboard/retail.inventory_risk` later. Every
 * presentation component reads this shape and nothing else, so the cutover to
 * the API changes one file (`dashboardData.js`) and no component.
 *
 * NUMBERS ARE RAW. Components format at render time using the shared
 * formatters and the active language. Never store a formatted string here —
 * a formatted number cannot be summed, sorted, or compared.
 *
 * NO THRESHOLD LIVES IN JAVASCRIPT. The state classification and the KPI
 * predicates (`Position < ROP`, `DoS > 15`, `growth < 1.0 && DoS > 10`) are
 * resolved upstream into `state` and the `is_*` booleans on each item. This
 * module and its selectors only count flags and sum columns. If you find
 * yourself typing a threshold into this folder, the rule belongs upstream —
 * in `scripts/build_inventory_risk_fixture.py` now, in the backend builder
 * later — so that one definition stays traceable to the workbook.
 */

export const AGENT_ID = "retail.inventory_risk";
export const SCHEMA_VERSION = 1;

/** The dropdowns' "clear" option, matching the backend's server-filter value. */
export const ALL = "ALL";

/**
 * Severity ordering for the risk register and the at-risk-by-state chart.
 * A2 spec section 5c. Anything not `Healthy` counts as at risk.
 */
export const STATE_ORDER = Object.freeze([
  "Stockout",
  "Low",
  "Expiry",
  "Overstock",
  "Slow-mover",
  "Healthy",
]);

export const HEALTHY_STATE = "Healthy";

/**
 * The reorder zone: exactly the states `Position < ROP` produces.
 *
 * f07 assigns Stockout below `0.6 × ROP` and Low below ROP, so these two
 * states and that comparison select the same rows by construction. Naming the
 * set once keeps the tiles, the register and the What-If engine from each
 * deciding it separately.
 */
export const REPLENISH_STATES = Object.freeze(["Stockout", "Low"]);

/**
 * What-If levers, A2 spec section 8a → `Constants` B16–B21.
 *
 * `effect` is what the reader is told the lever does. It is not decoration:
 * `markdown` is listed with no effect because the workbook's formulas carry no
 * markdown term, and a slider that silently does nothing is worse than one
 * that says so.
 */
export const LEVER_DEFINITIONS = Object.freeze([
  {
    id: "demand",
    label: "Demand surge",
    unit: "%",
    min: -30,
    max: 40,
    step: 1,
    cell: "B16",
    effect: "ADS × (1 + demand/100) — DoS falls, stockouts rise",
  },
  {
    id: "promo",
    label: "Promo pull",
    unit: "%",
    min: 0,
    max: 50,
    step: 1,
    cell: "B17",
    effect: "Promo-eligible SKUs deplete faster",
  },
  {
    id: "markdown",
    label: "Markdown clear",
    unit: "%",
    min: 0,
    max: 60,
    step: 1,
    cell: "B18",
    effect: "No modelled effect — the workbook has no markdown term",
    modelled: false,
  },
  {
    id: "inbound",
    label: "Inbound cover",
    unit: "%",
    min: -40,
    max: 60,
    step: 5,
    cell: "B19",
    effect: "Open PO × (1 + inbound/100) — fills Position",
  },
  {
    id: "lead",
    label: "Lead time",
    unit: "d",
    min: -2,
    max: 6,
    step: 1,
    cell: "B20",
    effect: "ROP = ADS × (Lead + Δ + Safety) — pushes ROP up",
  },
  {
    id: "safety",
    label: "Safety days",
    unit: "d",
    min: -2,
    max: 5,
    step: 1,
    cell: "B21",
    effect: "ROP += safety — fewer stockouts, more capital",
  },
]);

/**
 * Every lever at rest, which is the setting the workbook was calculated at
 * (`Constants` B16–B21 are all zero).
 *
 * Deliberately not the mockup's `baseOv()`, which opens promo at 15 and
 * markdown at 25. Those are the values of the *scenario* the workbook
 * publishes on `What-If · Per Agent`, not of its baseline — starting the
 * sliders there would show a scenario while the board claimed to show the
 * workbook.
 */
export const BASELINE_LEVERS = Object.freeze(
  Object.fromEntries(LEVER_DEFINITIONS.map((lever) => [lever.id, 0])),
);

/**
 * Shelf-life buckets for the expiry timeline (A2 spec section 6,
 * `#ch-dim-sea`). Upper bound is inclusive; `null` means unbounded.
 */
export const EXPIRY_BUCKETS = Object.freeze([
  { id: "d1", label: "≤ 1 day", max: 1 },
  { id: "d2_3", label: "2–3 days", max: 3 },
  { id: "d4_7", label: "4–7 days", max: 7 },
  { id: "d8p", label: "> 7 days", max: null },
]);

/** How many SKUs the expiry watchlist shows (A2 spec section 6). */
export const EXPIRY_WATCHLIST_SIZE = 4;

/**
 * Horizons the projection offers, in weeks (A2 spec section 7a, `f-hz`).
 *
 * Declared once, here, and served to the board inside
 * `filter_options.horizons_weeks` — the filter bar renders whatever the
 * payload offers rather than a list typed into the control. A provider that
 * can only honour a shorter look-ahead ships a shorter array and the UI
 * follows it; nothing in a component has to change.
 */
export const PROJECTION_HORIZONS_WEEKS = Object.freeze([4, 8, 12, 16]);

/**
 * Days in a week. Exported because the chart's axis has to space its labels a
 * week apart and would otherwise carry its own 7.
 */
export const DAYS_PER_WEEK = 7;

/**
 * The horizon the board opens on, in weeks.
 *
 * Four: long enough for the longest lead time in the dataset (7 days) plus a
 * full replenishment cycle after it, and long enough for the reorder policy to
 * complete a cycle. Longer horizons are offered, not recommended — `ads` is
 * one number per SKU, so every extra week compounds further on a level the
 * workbook measured once. The panel says so.
 */
export const DEFAULT_HORIZON_WEEKS = 4;

/**
 * Coerce anything into a horizon this board actually offers.
 *
 * A value arriving from a saved scenario, a query string or a backend is a
 * string, a stale number, or absent. Resolving in one place means the fallback
 * is decided once rather than at each call site that needs it.
 *
 * @param {unknown} weeks
 * @returns {number} A member of `PROJECTION_HORIZONS_WEEKS`.
 */
export function resolveHorizonWeeks(weeks) {
  const value = Number(weeks);
  return PROJECTION_HORIZONS_WEEKS.includes(value)
    ? value
    : DEFAULT_HORIZON_WEEKS;
}

/**
 * The horizon in days, which is the unit the projection loop counts in.
 *
 * @param {unknown} weeks
 * @returns {number}
 */
export function horizonDays(weeks) {
  return resolveHorizonWeeks(weeks) * DAYS_PER_WEEK;
}

/**
 * How far the projection chart looks ahead by default, in days (A2 spec
 * section 4). Derived, not typed: the default horizon is stated once above and
 * this follows it.
 */
export const PROJECTION_DAYS = DEFAULT_HORIZON_WEEKS * DAYS_PER_WEEK;

/**
 * Resolve the daily-demand model's inputs out of a payload, with fallbacks.
 *
 * The projection shapes its burn with a day-of-week profile, twelve seasonal
 * indices per vertical and A1's typed trend. All three are new to this board,
 * so a provider built before them has to keep working rather than throw:
 * a flat profile summing to `dow_sum`, flat seasonality and zero trend
 * reproduce exactly the straight-line burn this panel drew before, which is
 * the honest degradation — less shape, never a different total.
 *
 * @param {object} payload A fixture or a dashboard payload.
 * @returns {{ profile: number[], curves: Record<string, number[]>,
 *   currentMonth: number, trendByVertical: Record<string, number> }}
 */
export function resolveDemandModel(payload) {
  const dowSum = payload?.constants?.dow_sum ?? DAYS_PER_WEEK;
  const profile = payload?.constants?.dow_profile;

  const trendByVertical = {};
  for (const row of payload?.reference_by_vertical ?? []) {
    trendByVertical[row.legal_entity_id] = row.trend_pct ?? 0;
  }

  return {
    profile:
      Array.isArray(profile) && profile.length === DAYS_PER_WEEK
        ? profile
        : new Array(DAYS_PER_WEEK).fill(dowSum / DAYS_PER_WEEK),
    curves: payload?.seasonality?.by_legal_entity ?? {},
    currentMonth: payload?.seasonality?.current_month_index ?? 0,
    trendByVertical,
  };
}

/** Twelve flat indices, for a vertical the payload carries no curve for. */
export const FLAT_SEASONALITY = Object.freeze(new Array(12).fill(100));

/**
 * The projection has no history to show, and the chart says so rather than
 * drawing one. A2 spec section 4 puts a split line between past and forecast;
 * the workbook stores a single on-hand position per SKU and no time series at
 * all, so anything to the left of today would be a back-cast — a straight line
 * drawn by assuming the past looked like the future.
 */
export const PROJECTION_NOTE =
  "Projected forward from today's position. The workbook holds one on-hand " +
  "reading per SKU and no history, so there is nothing to plot before day 0. " +
  "Demand is the measured ADS spread across the week by the same day-of-week " +
  "and seasonal model the Demand Forecasting board draws, and stock is " +
  "reordered at ROP up to Max.";

/**
 * Shown only past the default horizon.
 *
 * Offering sixteen weeks and saying nothing would imply the curve is four
 * times as informative as the four-week one. It is not: the same single ADS
 * carries it, so the extra twelve weeks are extrapolation, not forecast. The
 * control stays available — a reader comparing a long lead time against cover
 * has a real use for it — but the panel stops short of implying more than the
 * workbook holds.
 */
export const LONG_HORIZON_NOTE =
  "Past four weeks the curve keeps its shape from the seasonal profile and " +
  "the reorder policy, but its level still rests on one measured ADS per " +
  "SKU — a longer horizon adds structure, not more measurement.";

/**
 * @typedef {object} InventoryRiskScope
 * @property {string} legal_entity_id Vertical, or `ALL`.
 * @property {string} category_group  Category id, or `ALL`.
 * @property {string} store_id        Store id, or `ALL`.
 * @property {string} state           One of STATE_ORDER, or `ALL`.
 * @property {string} sku             Case-insensitive id/name search, or "".
 */

/** @type {Readonly<InventoryRiskScope>} */
export const DEFAULT_SCOPE = Object.freeze({
  legal_entity_id: ALL,
  category_group: ALL,
  store_id: ALL,
  state: ALL,
  sku: "",
});

/**
 * @typedef {object} InventoryRiskKpis
 * @property {number} stockout_risk_skus Count of `Position < ROP`.
 * @property {number} overstock_skus     Count of state Overstock.
 * @property {number} expiry_units       Sum of units past shelf-life cover.
 * @property {number} slow_mover_skus    Count of state Slow-mover.
 * @property {number} avg_dos            Mean days of supply.
 * @property {number} inventory_value    Sum of `Position × price`.
 * @property {number} at_risk_value      Sum of value where state is not Healthy.
 * @property {number} healthy_skus       Count of Healthy.
 * @property {number} sku_count          Rows in scope.
 */

/**
 * @typedef {object} InventoryRiskDashboard
 * @property {number} schema_version
 * @property {string} agent
 * @property {string} as_of                ISO timestamp of the source data.
 * @property {boolean} is_mock             True while the source is the workbook.
 * @property {string} note                 Why the numbers are illustrative.
 * @property {InventoryRiskScope} scope    Scope actually applied.
 * @property {object} filter_options
 * @property {InventoryRiskKpis} kpis
 * @property {Array<object>} at_risk_by_state      Stacked bar, one per state.
 * @property {Array<object>} value_by_category     Donut, inventory value share.
 * @property {Array<object>} at_risk_by_category   Vertical bar.
 * @property {Array<object>} stockout_by_store     Stacked bar, gross per store.
 * @property {Array<object>} at_risk_by_cluster    Vertical bar, gross.
 * @property {Array<object>} at_risk_by_legal_entity Vertical bar.
 * @property {object} expiry_timeline      `{ buckets, watchlist }`.
 * @property {Array<object>} risk_register Severity-sorted rows.
 * @property {Array<object>} reference_by_vertical Workbook totals, for tests.
 */

/**
 * Chain-net headline versus gross breakdowns.
 *
 * A2 spec section 10 note 1: `kpis` are chain-net — surplus in one store nets
 * off shortage in another. `stockout_by_store` and `at_risk_by_cluster` are
 * gross: they add up local pockets of risk and will therefore total HIGHER
 * than the headline. That gap is intentional and is not a reconciliation bug.
 * Any UI that shows both must say so, or a reader will report it as an error.
 */
export const GROSS_VS_NET_NOTE =
  "Store and cluster breakdowns are gross: they sum local risk pockets and " +
  "exceed the chain-net headline, which nets surplus against shortage across " +
  "stores.";

/**
 * A2 spec section 10 note 2. `at_risk_value` is the full position value of
 * every non-Healthy SKU, not the value genuinely at risk of being lost. It
 * overstates exposure next to unit measures like `expiry_units`, so it needs
 * a label rather than a bare currency figure.
 */
export const AT_RISK_VALUE_NOTE =
  "At-risk value is the full position value of every non-healthy SKU, not an " +
  "expected loss.";

/**
 * The healthy band for average days of supply (A2 spec section 3). Outside it
 * the tile is flagged: below means the scope is running thin, above means
 * capital is sitting still.
 */
export const DOS_TARGET = Object.freeze({ min: 7, max: 21 });

/**
 * The formula behind each tile, shown on hover.
 *
 * These are labels, not logic — every one of them is already resolved upstream
 * (see the note at the top of this file). They exist so a reader can see what
 * a number means without leaving the board, which is what the mockup's
 * `data-fx` attributes did.
 */
export const KPI_FORMULAS = Object.freeze({
  stockout_risk_skus: "count( Position < ROP )",
  overstock_skus:
    "count( state = Overstock: non-perishable, DoS > 15 )" +
    " · at-risk = Σ (Position − Max) × price, or 30% × Position × price" +
    " where Position ≤ Max",
  expiry_units: "Σ max(0, Position − ADS × shelf-life)",
  expiry_value: "Σ Expiry-units at-risk value, state = Expiry",
  // "not already worse off" is the whole difference between this count and a
  // bare growth/DoS predicate: a slow SKU that is also short of stock is
  // counted once, under the more urgent state. Reading 37 here and 43 from the
  // raw predicate is not a discrepancy — states are exclusive by severity.
  // (The gap is a property of the dataset, not a fixed number; it was 51 vs 62
  // before the fixture was regenerated. The argument is what matters.)
  slow_mover_skus:
    "count( state = Slow-mover: growth < 1.0, DoS > 10," +
    " not already worse off )",
  avg_dos: "mean( Position ÷ ADS )",
  inventory_value: "Σ Position × unit price",
});

/** Column formulas for the risk register, shown on hover per cell. */
export const REGISTER_FORMULAS = Object.freeze({
  on_hand: "On-hand = Position − Open PO",
  open_po: "Open PO = ordered, not yet received",
  position: "Position = On-hand + Open PO",
  rop: "ROP = ADS × (Lead + Safety)",
  dos: "DoS = Position ÷ ADS",
  inv_value: "Value = Position × price",
});

/**
 * Validate and fill a dashboard payload from either source.
 *
 * Throws on a shape the components cannot render, rather than letting an
 * undefined propagate into a chart and surface as an unreadable render error.
 *
 * @param {unknown} payload
 * @returns {InventoryRiskDashboard}
 */
export function normalizeInventoryRiskDashboard(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Inventory Risk dashboard payload must be an object");
  }

  const { schema_version: version, agent } = payload;

  if (version !== SCHEMA_VERSION) {
    throw new Error(
      `Inventory Risk dashboard schema_version ${version} is not supported ` +
        `(expected ${SCHEMA_VERSION})`,
    );
  }
  if (agent !== AGENT_ID) {
    throw new Error(
      `Inventory Risk dashboard is for ${AGENT_ID}, received ${agent}`,
    );
  }

  /*
   * A provider may offer fewer horizons than this board knows about, but never
   * one it cannot compute — anything outside the list is dropped. Falling back
   * to the full list when nothing survives is deliberate: an empty array would
   * render a segmented control with no segments, which reads as a broken
   * filter rather than as a provider that declined to offer the choice.
   */
  const offeredHorizons = (
    payload.filter_options?.horizons_weeks ?? PROJECTION_HORIZONS_WEEKS
  )
    .map(Number)
    .filter((weeks) => PROJECTION_HORIZONS_WEEKS.includes(weeks));

  return {
    schema_version: SCHEMA_VERSION,
    agent: AGENT_ID,
    as_of: payload.as_of ?? "",
    is_mock: payload.is_mock === true,
    note: payload.note ?? "",
    scope: { ...DEFAULT_SCOPE, ...(payload.scope ?? {}) },
    filter_options: {
      legal_entities: payload.filter_options?.legal_entities ?? [],
      categories: payload.filter_options?.categories ?? [],
      stores: payload.filter_options?.stores ?? [],
      states: payload.filter_options?.states ?? [...STATE_ORDER],
      horizons_weeks: offeredHorizons.length
        ? offeredHorizons
        : [...PROJECTION_HORIZONS_WEEKS],
    },
    /*
     * Declared, or it is dropped. This normalizer returns an explicit object,
     * so any block the selectors add and this list omits never reaches a
     * component — which is exactly how the KPI charts went missing on this
     * board while working on the other two.
     */
    kpi_sparklines: payload.kpi_sparklines ?? {},
    kpis: {
      stockout_risk_skus: 0,
      overstock_skus: 0,
      overstock_excess_value: 0,
      expiry_units: 0,
      expiry_value: 0,
      slow_mover_skus: 0,
      avg_dos: 0,
      inventory_value: 0,
      at_risk_value: 0,
      healthy_skus: 0,
      sku_count: 0,
      ...(payload.kpis ?? {}),
    },
    /*
     * `projection` and `simulation` default to empty rather than throwing, and
     * `schema_version` stays at 1 because of it: a backend built before these
     * existed renders a board with two quiet panels, not a crash. Version 2 is
     * for a field being removed or changing type.
     */
    projection: {
      days: payload.projection?.days ?? 0,
      /*
       * Echoed so the chart can space its axis labels a week apart without
       * dividing `days` by seven itself, and so a payload built at a
       * non-default horizon still says which one. Derived from `days` when a
       * provider omits it, rather than silently reporting the default over a
       * curve that is plainly longer than four weeks.
       */
      horizon_weeks: resolveHorizonWeeks(
        payload.projection?.horizon_weeks ??
          (payload.projection?.days ?? 0) / DAYS_PER_WEEK,
      ),
      points: payload.projection?.points ?? [],
      metrics: {
        position: 0,
        inbound: 0,
        avg_dos: 0,
        at_risk_value: 0,
        ...(payload.projection?.metrics ?? {}),
      },
      days_to_empty: payload.projection?.days_to_empty ?? null,
    },
    simulation: {
      applied: payload.simulation?.applied === true,
      levers: { ...BASELINE_LEVERS, ...(payload.simulation?.levers ?? {}) },
      baseline: payload.simulation?.baseline ?? null,
      scenario: payload.simulation?.scenario ?? null,
      baseline_projection: payload.simulation?.baseline_projection ?? null,
      projection: payload.simulation?.projection ?? null,
      index: payload.simulation?.index ?? [],
    },
    at_risk_by_state: payload.at_risk_by_state ?? [],
    value_by_category: payload.value_by_category ?? [],
    at_risk_by_category: payload.at_risk_by_category ?? [],
    stockout_by_store: payload.stockout_by_store ?? [],
    at_risk_by_cluster: payload.at_risk_by_cluster ?? [],
    at_risk_by_legal_entity: payload.at_risk_by_legal_entity ?? [],
    expiry_timeline: {
      buckets: payload.expiry_timeline?.buckets ?? [],
      watchlist: payload.expiry_timeline?.watchlist ?? [],
    },
    best_actions: payload.best_actions ?? [],
    risk_register: payload.risk_register ?? [],
    reference_by_vertical: payload.reference_by_vertical ?? [],
  };
}

/**
 * Serialize a scope into the query the backend route will accept.
 * `ALL` and empty search are omitted so the URL stays readable and the
 * backend's own "no filter" default applies.
 *
 * @param {Partial<InventoryRiskScope>} scope
 * @returns {Record<string, string>}
 */
export function serializeScope(scope) {
  const merged = { ...DEFAULT_SCOPE, ...(scope ?? {}) };
  const query = {};

  for (const key of ["legal_entity_id", "category_group", "store_id", "state"]) {
    if (merged[key] && merged[key] !== ALL) {
      query[key] = merged[key];
    }
  }
  if (merged.sku && merged.sku.trim()) {
    query.sku = merged.sku.trim();
  }

  return query;
}
