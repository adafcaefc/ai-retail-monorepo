/**
 * The shape Replenishment renders, whichever side produced it.
 *
 * Same discipline as the other two Retail boards: one normalizer at the
 * boundary, presentation components downstream of it, and no component that
 * knows whether a fixture or an API answered.
 */

export const AGENT_ID = "retail.replenishment";
export const SCHEMA_VERSION = 1;

export const ALL = "ALL";

/**
 * The three purchase routes (A3 spec section 7).
 *
 * Ordered by lead time, which is also how the fixture assigns them — see
 * `scripts/build_replenishment_fixture.py` for why lead time rather than the
 * spec's `catId in {BEV, HOU}`, which names categories this dataset has never
 * had.
 */
export const ROUTE_ORDER = Object.freeze(["direct", "flow", "cross"]);

/**
 * The six What-If levers, A3 spec section 9a — `Constants` B16–B21.
 *
 * The same six the other two boards carry, because they are the same six
 * cells. What differs is what they reach on this board: an order quantity
 * rather than a risk state, so the effect text names the order.
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
    effect: "ADS × (1 + demand/100) — lifts ROP, Max and the order",
  },
  {
    id: "promo",
    label: "Promo pull",
    unit: "%",
    min: 0,
    max: 50,
    step: 1,
    cell: "B17",
    effect: "Promo-eligible SKUs order more",
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
    effect: "Open PO × (1 + inbound/100) — more inbound, smaller order",
  },
  {
    id: "lead",
    label: "Lead time",
    unit: "d",
    min: -2,
    max: 6,
    step: 1,
    cell: "B20",
    effect: "Longer lead raises Max, so each line orders further ahead",
  },
  {
    id: "safety",
    label: "Safety days",
    unit: "d",
    min: -2,
    max: 5,
    step: 1,
    cell: "B21",
    effect: "Safety days raise Max — bigger order, more capital",
  },
]);

/**
 * Every lever at rest, which is the setting the workbook was calculated at
 * (`Constants` B16–B21 are all zero).
 *
 * Not the mockup's `baseOv()`, which opens promo at 15 and markdown at 25.
 * Those are the values of a published *scenario*; opening there would show a
 * simulation while the board claimed to show the workbook.
 */
export const BASELINE_LEVERS = Object.freeze({
  demand: 0,
  promo: 0,
  markdown: 0,
  inbound: 0,
  lead: 0,
  safety: 0,
});

/** The four figures the simulator compares, chosen for a buyer's decision. */
export const SIMULATION_METRICS = Object.freeze([
  { id: "skus_to_reorder", label: "SKUs to reorder" },
  { id: "order_units", label: "Order units" },
  { id: "order_value_cost", label: "Order value (cost)" },
  { id: "avg_cover_days", label: "Avg cover days" },
]);

/** How many saved scenarios the comparison chart will overlay. */
export const MAX_SAVED_SCENARIOS = 4;

/**
 * How far the requirement chart looks ahead, in days (A3 spec section 4).
 *
 * The fallback horizon, used only when the lines carry no 32-week demand
 * curve — an unseeded `synthetic.demand_store_sku_32w` or a stale fixture.
 * The same horizon Inventory Risk projects over, so a reader moving between
 * the two boards is comparing the same window. Four times the longest lead in
 * the dataset (7 days, cross-dock), which is enough for every route to land
 * at least once and for the gap the PO fills to be visible.
 */
export const REQUIREMENT_DAYS = 28;

/**
 * The weekly chart's span: 16 measured weeks, then 16 forecast weeks.
 *
 * "Today" is the boundary the synthetic table encodes in its column names —
 * `actual_w1` is the most recent actual week, `forecast_w1` the next one
 * ahead — so the divider sits between W-1 and W+1 with no date arithmetic
 * anywhere.
 */
export const REQUIREMENT_WEEKS = Object.freeze({ actual: 16, forecast: 16 });

/**
 * The assumption behind the requirement-versus-inbound chart, A3 spec 4.
 *
 * The workbook stores how much is on order per SKU, and never when it lands.
 * There is no arrival date in any of the 30 tables. So the inbound line places
 * each SKU's whole open PO on its own lead day — 2, 4 or 7, by route — which is
 * the earliest it could arrive and therefore the most optimistic reading of
 * cover. A real receiving calendar would spread it; this one steps.
 */
export const REQUIREMENT_NOTE =
  "Inbound is placed on each SKU's lead day because the workbook records how " +
  "much is on order but never when it arrives. Requirement is a flat ADS per " +
  "day, which is all one ADS per SKU can support.";

/**
 * The weekly chart's assumption, when the lines carry a 32-week curve.
 *
 * The demand backbone is measured. The cover curve cannot be: no table in
 * this warehouse records when an inbound order arrives, so cover is modelled
 * as half this week's and half last week's demand — a supply that replenishes
 * on last week's sales and therefore lags demand by about half a week. The
 * mockup also dips that curve every fourth week; those shortfalls are
 * invented, and inventing a shortfall on a measured board is how a prototype
 * ornament starts reading as a delivery record.
 */
export const REQUIREMENT_CURVE_NOTE =
  "Demand is the measured 32-week curve — 16 weeks of actuals, then 16 of " +
  "forecast — with today between W-1 and W+1. No table records when an " +
  "inbound order arrives, so cover is modelled as half this week's and half " +
  "last week's demand: supply that lags demand by about half a week. Where " +
  "requirement stands above cover is the gap a purchase order exists to close.";

/** @typedef {object} ReplenishmentScope */
export const DEFAULT_SCOPE = Object.freeze({
  legal_entity_id: ALL,
  category_group: ALL,
  store_id: ALL,
  route: ALL,
  sku: "",
  reorder_only: true,
});

/**
 * The formula behind each tile, shown on hover.
 *
 * "Position", "ROP" and "cover" mean different things in different retail
 * systems, and a reader who cannot check what a number counts will eventually
 * assume the wrong one.
 */
export const KPI_FORMULAS = Object.freeze({
  skus_to_reorder: "count( Position < ROP )",
  order_units: "Σ max(0, Max − Position), sales units",
  order_value_retail: "Σ order units × selling price",
  order_value_cost: "Σ buy units × pack × trade-agreement price",
  inbound_open_po: "Σ Open PO units",
  fill_rate_pct: "SKUs at or above ROP ÷ all SKUs",
  avg_cover_days: "mean( Position ÷ ADS )",
  recoverable_saving: "Σ (designated price − best price) × buy units",
});

/** Column formulas for the purchase-order preview, shown per cell. */
export const LINE_FORMULAS = Object.freeze({
  on_hand: "On-hand = Position − Open PO",
  open_po: "Open PO = ordered, not yet received",
  position: "Position = On-hand + Open PO",
  rop: "ROP = ADS × (Lead + Safety)",
  max: "Max = ADS × (Lead + Safety + 4)",
  order_qty_sales: "Order = max(0, Max − Position)",
  order_qty_buy: "Buy = CEILING(Order ÷ pack factor)",
  order_value_cost: "Line cost = Buy × pack × trade price",
});

/**
 * The two order values, and why the board never shows one alone.
 *
 * A buyer approving the PO needs the cost. A merchandiser sizing the
 * commitment needs the retail value. They differ by roughly a fifth on this
 * dataset, so naming either one simply "order value" invites the wrong
 * decision from whichever reader was thinking of the other.
 */
export const ORDER_VALUE_NOTE =
  "Order value is shown twice: at selling price, which is what the A3 sheet " +
  "totals, and at trade-agreement price, which is what the purchase order " +
  "would actually cost.";

/**
 * Whole cases, not exact requirements.
 *
 * `Buy = CEILING(Order ÷ pack)` always rounds up, so a purchase order brings
 * in slightly more than the shortfall it was raised against. That overshoot is
 * real stock and real money, and it is why the cost line does not divide back
 * into the unit requirement.
 */
export const PACK_ROUNDING_NOTE =
  "Purchase quantities round up to whole packs, so a line buys a little more " +
  "than its shortfall.";

export function normalizeReplenishmentDashboard(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Replenishment dashboard payload must be an object");
  }
  if (payload.schema_version !== SCHEMA_VERSION) {
    throw new Error(
      `Replenishment dashboard schema_version ${payload.schema_version} is ` +
        `not supported (expected ${SCHEMA_VERSION})`,
    );
  }
  if (payload.agent !== AGENT_ID) {
    throw new Error(
      `Replenishment dashboard is for ${AGENT_ID}, received ${payload.agent}`,
    );
  }

  return {
    schema_version: SCHEMA_VERSION,
    agent: AGENT_ID,
    as_of: payload.as_of ?? "",
    is_mock: payload.is_mock === true,
    note: payload.note ?? "",
    derivation: payload.derivation ?? {},
    scope: { ...DEFAULT_SCOPE, ...(payload.scope ?? {}) },
    routes: payload.routes ?? [],
    filter_options: {
      legal_entities: payload.filter_options?.legal_entities ?? [],
      categories: payload.filter_options?.categories ?? [],
      stores: payload.filter_options?.stores ?? [],
      routes: payload.filter_options?.routes ?? [],
    },
    kpis: {
      skus_to_reorder: 0,
      order_units: 0,
      order_value_retail: 0,
      order_value_cost: 0,
      inbound_open_po: 0,
      fill_rate_pct: 0,
      avg_cover_days: 0,
      recoverable_saving: 0,
      line_count: 0,
      ...(payload.kpis ?? {}),
    },
    /*
     * `requirement` and `simulation` default to empty rather than throwing,
     * and `schema_version` stays 1: both are additive, so a backend that
     * predates them renders an empty panel instead of crashing the board.
     *
     * `mode` picks the chart's grain: "weekly" when every line carried a
     * 32-week demand curve, "daily" for the flat-ADS fallback. The weekly
     * fields (`split_index`, `first_shortfall_week`, `demand_per_week`) are
     * declared here for the same reason every field is — one this list omits
     * never reaches a component.
     */
    requirement: {
      mode: payload.requirement?.mode ?? "daily",
      days: payload.requirement?.days ?? 0,
      weeks: payload.requirement?.weeks ?? null,
      points: payload.requirement?.points ?? [],
      demand_per_day: payload.requirement?.demand_per_day ?? 0,
      demand_per_week: payload.requirement?.demand_per_week ?? 0,
      cover_runs_out: payload.requirement?.cover_runs_out ?? null,
      first_shortfall_week: payload.requirement?.first_shortfall_week ?? null,
      split_index: payload.requirement?.split_index ?? 0,
      gap_at_horizon: payload.requirement?.gap_at_horizon ?? 0,
    },
    simulation: {
      applied: payload.simulation?.applied === true,
      levers: { ...BASELINE_LEVERS, ...(payload.simulation?.levers ?? {}) },
      baseline: payload.simulation?.baseline ?? null,
      scenario: payload.simulation?.scenario ?? null,
      baseline_requirement: payload.simulation?.baseline_requirement ?? null,
      requirement: payload.simulation?.requirement ?? null,
      index: payload.simulation?.index ?? [],
      unmodelled: (
        Array.isArray(payload.simulation?.unmodelled)
          ? payload.simulation.unmodelled
          : []
      ).map(String),
    },
    by_route: payload.by_route ?? [],
    by_store: payload.by_store ?? [],
    by_category: payload.by_category ?? [],
    by_cluster: payload.by_cluster ?? [],
    by_legal_entity: payload.by_legal_entity ?? [],
    kpi_sparklines: payload.kpi_sparklines ?? {},
    vendors: payload.vendors ?? [],
    vendor_split: payload.vendor_split ?? [],
    /*
     * Declared, or it is dropped — this returns an explicit object, so a block
     * the selectors add and this list omits never reaches a component. That is
     * exactly how the KPI charts went missing on Inventory Risk, and the
     * regression test for it asserts through the rendered board rather than
     * through the selector, because a selector test would have passed.
     */
    sourcing: payload.sourcing ?? {
      terms: null,
      skus: [],
      switchable_lines: 0,
      on_best_lines: 0,
    },
    purchase_order: payload.purchase_order ?? [],
    reference_by_vertical: payload.reference_by_vertical ?? [],
  };
}

/** Serialize a scope into the query the backend route will accept. */
export function serializeScope(scope) {
  const query = {};
  for (const [key, value] of Object.entries({ ...DEFAULT_SCOPE, ...scope })) {
    if (value === ALL || value === "" || value === false) continue;
    query[key] = value;
  }
  return query;
}
