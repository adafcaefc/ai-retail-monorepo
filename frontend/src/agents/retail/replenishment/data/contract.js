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
 * How many weeks of real history and real forecast the requirement chart
 * draws each side of Today (A3 spec section 4).
 *
 * `synthetic.demand_store_sku_32w` carries exactly this many weeks each way,
 * store x SKU — see `scripts/seed_synthetic_demand_32w.py`. The chart used to
 * be capped at 28 days forward and nothing backward, because one ADS per SKU
 * was all the workbook held; a flat rate has no reason to run past the
 * longest lead time. A real weekly curve does.
 */
export const REQUIREMENT_WEEKS_BACK = 16;
export const REQUIREMENT_WEEKS_FORWARD = 16;

/**
 * The assumption behind the requirement-versus-inbound chart, A3 spec 4.
 *
 * The workbook stores how much is on order per SKU and never when it lands.
 * There is no arrival date in any of the 30 tables, so an arrival calendar was
 * generated instead: `synthetic.inbound_store_sku_16w`, batched on each
 * route's own cadence (direct weekly, flow every 2 weeks, cross every 3) and
 * anchored to the demand curve, so total inbound across the horizon reproduces
 * total forecast demand. That anchoring is what keeps cover tracking
 * requirement rather than falling behind it for ever.
 *
 * It is synthetic and the board says so. What it replaced was not more honest,
 * only less visible: with no calendar at all the chart placed every SKU's
 * whole open PO on its lead day, and since all three routes lead under a week,
 * cover was one step at W+1 and a flat line thereafter.
 */
export const REQUIREMENT_NOTE =
  "Inbound follows a generated delivery calendar — the workbook records how " +
  "much is on order but never when it arrives, and records no past receipts " +
  "at all, so weeks before today are drawn at a flat 97% of demand. Both " +
  "lines are units per week; the stock they imply is in the tooltip.";

/**
 * Historical inbound, as a fraction of that week's measured demand.
 *
 * No table records what was actually received 16 weeks ago -- the warehouse
 * carries no receipts at all, which is the same gap
 * `synthetic.inbound_store_sku_16w` fills going forward. But leaving the past
 * blank drew the inbound line only across the forecast half, and a reader
 * comparing supply against demand got half a picture.
 *
 * What can be said about the past is narrow and worth stating exactly: over 16
 * weeks the chain neither ran dry nor buried itself, so receipts must have
 * tracked sales closely. Slightly under, because the position the board opens
 * with today is lower than it was -- stock was drawn down, not built up. Hence
 * a flat fraction rather than a shape: a fabricated wiggle would imply weekly
 * receipt data nobody has, while a flat line reads as what it is, an
 * assumption applied evenly.
 */
export const HISTORY_INBOUND_RATIO = 0.97;

/** Shown instead when no arrival schedule reached the browser. */
export const REQUIREMENT_FALLBACK_NOTE =
  "No delivery schedule in scope, so each SKU's whole open PO is placed in " +
  "the week its lead day falls.";

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
     */
    requirement: {
      weeks_back: payload.requirement?.weeks_back ?? 0,
      weeks_forward: payload.requirement?.weeks_forward ?? 0,
      points: payload.requirement?.points ?? [],
      // False when no arrival schedule reached the browser, which switches the
      // panel's caveat to the one that describes what it actually drew.
      inbound_scheduled: payload.requirement?.inbound_scheduled ?? false,
      demand_per_week: payload.requirement?.demand_per_week ?? 0,
      inbound_per_week: payload.requirement?.inbound_per_week ?? 0,
      cover_runs_out: payload.requirement?.cover_runs_out ?? null,
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
