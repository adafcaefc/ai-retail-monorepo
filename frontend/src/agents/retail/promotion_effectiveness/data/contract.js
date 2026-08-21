/**
 * Promotion Effectiveness (Agent 4) dashboard data contract.
 *
 * The single shape both data sources produce: the local fixture today, and
 * `GET /api/html/dashboard/retail.promotion_effectiveness` in API mode. Every
 * presentation component reads this shape and nothing else, so the cutover to
 * the API changes one file (`dashboardData.js`) and no component.
 *
 * NUMBERS ARE RAW. Components format at render time using the shared
 * formatters. Never store a formatted string here — a formatted number cannot
 * be summed, sorted, or compared.
 *
 * NO THRESHOLD LIVES IN JAVASCRIPT. The promo-classification thresholds (ROI
 * target, funding guardrail, cannibalization cap, pre-buy materiality) live
 * upstream — in the backend snapshot and the fixture builder — and arrive on
 * the `thresholds` block. This module and its selectors only count and sum.
 *
 * TWO UPLIFTS. `uplift_pct` on the cards and per-vertical block is the modeled
 * NET uplift from the A4 Promotion sheet (~26% chain). Each campaign's
 * `expected_uplift_pct` is that campaign's PLANNED uplift (~47% average). They
 * are different numbers answering different questions; components label both.
 */

export const AGENT_ID = "retail.promotion_effectiveness";
export const SCHEMA_VERSION = 1;

/** The dropdowns' "clear" option, matching the backend's server-filter value. */
export const ALL = "ALL";

/**
 * What-If levers, A4 spec section 9a → `Constants` B16–B21.
 *
 * The same six levers every retail board carries, because the workbook's
 * engine is shared. Here the promo lever (B17) is the one that matters: it
 * lifts the modeled uplift on promo-eligible SKUs, raises the discount cost
 * and widens the cannibalization drag. `markdown` carries no modelled effect
 * for promotion margin and is marked so, matching the other boards.
 */
export const LEVER_DEFINITIONS = Object.freeze([
  {
    id: "demand",
    label: "Demand uplift",
    unit: "%",
    min: -30,
    max: 40,
    step: 1,
    cell: "B16",
    effect: "ADS × (1 + demand/100) — raises base traffic and promo volume",
  },
  {
    id: "promo",
    label: "Promo depth",
    unit: "%",
    min: 0,
    max: 50,
    step: 1,
    cell: "B17",
    effect: "Promo-eligible SKUs: higher uplift, deeper discount cost, more cannib",
  },
  {
    id: "markdown",
    label: "Markdown depth",
    unit: "%",
    min: 0,
    max: 60,
    step: 1,
    cell: "B18",
    effect: "No modelled effect on promo margin — the workbook has no markdown term",
    modelled: false,
  },
  {
    id: "inbound",
    label: "Open PO",
    unit: "%",
    min: -40,
    max: 60,
    step: 5,
    cell: "B19",
    effect: "Supports promo availability and pre-buy readiness",
  },
  {
    id: "lead",
    label: "Vendor lead",
    unit: "d",
    min: -2,
    max: 6,
    step: 1,
    cell: "B20",
    effect: "Affects A3 pre-buy feasibility",
  },
  {
    id: "safety",
    label: "Safety stock",
    unit: "d",
    min: -2,
    max: 5,
    step: 1,
    cell: "B21",
    effect: "Affects availability and order-up-to need",
  },
]);

/** Every lever at its baseline (workbook-calculated) position. */
export const BASELINE_LEVERS = Object.freeze(
  Object.fromEntries(LEVER_DEFINITIONS.map(({ id }) => [id, 0])),
);

/**
 * The four campaign-classification tabs the Suggested Best Action panel shows.
 * `recommendation` is resolved upstream (backend snapshot / fixture builder)
 * from the spec's promoClassify rule, never re-decided in a component.
 */
export const BEST_ACTION_TABS = Object.freeze([
  { id: "high_roi", label: "High ROI", recommendation: "Approve promo" },
  { id: "funding_gap", label: "Funding Gap", recommendation: "Negotiate supplier funding" },
  { id: "pre_buy_required", label: "Pre-buy Required", recommendation: "Trigger A3 pre-buy PO" },
]);

/** The metrics the What-If simulator compares as paired index bars (Baseline=100). */
export const SIMULATION_METRICS = Object.freeze([
  { id: "active_promo_skus", label: "Promo SKUs", lowerIsBetter: false },
  { id: "uplift_pct", label: "Uplift %", lowerIsBetter: false },
  { id: "incremental_margin", label: "Incr margin", lowerIsBetter: false },
  { id: "roi_x", label: "ROI", lowerIsBetter: false },
]);

/**
 * @typedef {Object} PromotionScope
 * @property {string} legal_entity_id   Vertical id (GRC, GMR, ...) or "ALL".
 * @property {string} category_group    Category id or "ALL".
 * @property {string} sku               Free-text SKU / promo-name search.
 */

export const DEFAULT_SCOPE = Object.freeze({
  legal_entity_id: ALL,
  category_group: ALL,
  store_id: ALL,
  sku: "",
});

/** The headline caveat the board prints beneath the charts. */
export const GRAIN_NOTE =
  "Incremental margin is chain-net gross (one row per item, surplus in one " +
  "store already netted against shortage in another). ROI is a stored KPI; " +
  "no separate promo-investment column is exposed.";

/**
 * The store/cluster/channel caveat — deliberately NOT the same wording as
 * GRAIN_NOTE above. Unlike a physical inventory position, incremental margin
 * has no netting operation between stores: f01 is purely multiplicative in
 * store_size and f13 is linear in ads, so a store's share of an item's
 * incremental_margin is `item.incremental_margin * (store.size_index /
 * item.store_size)` exactly, and summing it back up reproduces the chain-net
 * headline to the cent. See `selectors.js`'s `computeByStore` for the proof.
 */
export const STORE_GRAIN_NOTE =
  "Incremental margin by store, cluster and channel reconciles exactly to " +
  "the chain-net headline above — margin has no netting operation the way " +
  "physical inventory position does. Selecting a store replaces every KPI " +
  "and chart with that store's own position; campaigns and the season mix " +
  "stay chain-wide because the workbook carries no store dimension for them.";

/** The two-uplifts caveat, printed wherever both numbers appear near each other. */
export const UPLIFT_NOTE =
  "Two uplifts: the cards carry the modeled NET uplift (~26% chain); each " +
  "campaign's expected uplift is its PLANNED figure (~47% average).";

/** Per-tile hover labels, sourced from the workbook's own formulas. */
export const KPI_FORMULAS = Object.freeze({
  active_promo_skus: "SUM(fc11 promo SKU flag)",
  uplift_pct: "AVG(fc12 promo net uplift %)",
  incremental_margin: "SUM(f13 incremental promotion margin)",
  roi_x: "stored KPI — no exposed investment column",
  cannib_pct: "avg dim_item.cannibalisation_pct for promo SKUs",
  funding_pct: "avg supplier funding offset",
});

/**
 * Validate and default a dashboard payload into the contract shape.
 *
 * Returns an explicit object: any block the selectors add that this list
 * omits is dropped, which is how a tile went missing on a sibling board while
 * work continued on the others.
 *
 * @param {any} payload
 * @returns {import("./contract.js").PromotionDashboard}
 */
export function normalizePromotionDashboard(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Promotion dashboard payload must be an object");
  }

  const { schema_version: version, agent } = payload;

  if (version !== SCHEMA_VERSION) {
    throw new Error(
      `Promotion dashboard schema_version ${version} is not supported ` +
        `(expected ${SCHEMA_VERSION})`,
    );
  }
  if (agent !== AGENT_ID) {
    throw new Error(
      `Promotion dashboard is for ${AGENT_ID}, received ${agent}`,
    );
  }

  return {
    schema_version: SCHEMA_VERSION,
    agent: AGENT_ID,
    as_of: payload.as_of ?? "",
    is_mock: payload.is_mock === true,
    note: payload.note ?? "",
    source_workbook: payload.source_workbook ?? "",
    scope: { ...DEFAULT_SCOPE, ...(payload.scope ?? {}) },
    filter_options: {
      legal_entities: payload.filter_options?.legal_entities ?? [],
      categories: payload.filter_options?.categories ?? [],
      stores: payload.filter_options?.stores ?? [],
    },
    thresholds: {
      roi_target: 2,
      uplift_target_pct: 20,
      funding_guardrail_pct: 35,
      cannib_cap_pct: 25,
      pre_buy_material_units: 2000,
      ...(payload.thresholds ?? {}),
    },
    formulas: payload.formulas ?? {},
    kpi_sparklines: payload.kpi_sparklines ?? {},
    kpis: {
      active_promo_skus: 0,
      uplift_pct: 0,
      incremental_margin: 0,
      roi_x: 0,
      cannib_pct: 0,
      funding_pct: 0,
      campaigns: 0,
      pre_buy_uplift_units: 0,
      ...(payload.kpis ?? {}),
    },
    by_vertical: payload.by_vertical ?? [],
    by_category: payload.by_category ?? [],
    by_season: payload.by_season ?? [],
    by_store: payload.by_store ?? [],
    by_cluster: payload.by_cluster ?? [],
    by_channel: payload.by_channel ?? [],
    by_state: payload.by_state ?? [],
    largest_margin_skus: payload.largest_margin_skus ?? [],
    campaigns: payload.campaigns ?? [],
    best_actions: payload.best_actions ?? { high_roi: [], funding_gap: [], pre_buy_required: [] },
    simulation: {
      applied: payload.simulation?.applied === true,
      levers: { ...BASELINE_LEVERS, ...(payload.simulation?.levers ?? {}) },
      baseline: payload.simulation?.baseline ?? null,
      scenario: payload.simulation?.scenario ?? null,
      index: payload.simulation?.index ?? [],
    },
    reference_by_vertical: payload.reference_by_vertical ?? [],
  };
}

/**
 * Serialize a scope into the query the backend route accepts.
 * `ALL` and empty search are omitted so the URL stays readable.
 *
 * @param {Partial<PromotionScope>} scope
 * @returns {Record<string, string>}
 */
export function serializeScope(scope) {
  const merged = { ...DEFAULT_SCOPE, ...(scope ?? {}) };
  const query = {};

  for (const key of ["legal_entity_id", "category_group", "store_id"]) {
    if (merged[key] && merged[key] !== ALL) {
      query[key] = merged[key];
    }
  }
  if (merged.sku && merged.sku.trim()) {
    query.sku = merged.sku.trim();
  }

  return query;
}
