/**
 * Assortment Optimization (Agent 6) dashboard data contract.
 *
 * The single shape both data sources produce: the local fixture today, and
 * `GET /api/html/dashboard/retail.assortment_optimization` once a backend
 * module exists. Every presentation component reads this shape and nothing
 * else.
 *
 * NUMBERS ARE RAW. Components format at render time. Never store a formatted
 * string here.
 *
 * WHY THE A6 SHEET'S OWN KPI CELLS ARE NOT THE SOURCE.
 * A prior audit of the workbook (`Dataset_AI_Retail.xlsx`, sheet "AUDIT Root
 * Cause", RC-2) names `A6!B6:F13` — delist candidates, grow candidates, avg
 * GMROI, tail share, capital freed — as stale hardcoded values pasted from an
 * old snapshot rather than live formulas. Those five are computed fresh from
 * ENGINE / ENGINE_STORE / SKU_Master instead. Column G (contribution/day) sits
 * outside the flagged range and reconciles exactly against the live
 * ENGINE_STORE sum, so it is trusted. See the fixture builder script.
 *
 * WHERE THE CLASSIFICATION LIVES. `classification` ("delist"/"grow"/"hold"),
 * `is_tail` and `best_action_tab` are resolved upstream — in
 * `scripts/build_assortment_optimization_fixture.py` for the shipped
 * baseline, and re-derived in `engine.js` under a What-If scenario, from
 * thresholds the fixture carries on `classification_thresholds`. No component
 * re-decides them.
 */

export const AGENT_ID = "retail.assortment_optimization";
export const SCHEMA_VERSION = 1;

/** The dropdowns' "clear" option. */
export const ALL = "ALL";

/** Inventory states, ordered by severity — shared with the sibling boards. */
export const STATE_ORDER = Object.freeze([
  "Stockout",
  "Low",
  "Expiry",
  "Overstock",
  "Slow-mover",
  "Healthy",
]);

export const HEALTHY_STATE = "Healthy";

/** A6 spec section 2: states that make a SKU a delist candidate outright. */
export const DELIST_STATES = Object.freeze(["Slow-mover", "Overstock", "Expiry"]);

/** The three assortment verdicts. */
export const CLASSIFICATIONS = Object.freeze(["delist", "grow", "hold"]);

/**
 * What-If levers, A6 spec section 9a -> `Constants` B16-B21.
 *
 * Unlike the markdown board, `markdown` IS modelled here in one direction
 * only: it does not enter any formula, so it stays inert — the workbook has
 * no depth term. The other five drive ADS and position, which drive
 * contribution/day, GMROI and therefore the delist/grow scoring.
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
    effect: "ADS x (1 + demand/100) -- raises contribution/day and GMROI, moves SKUs out of the tail",
  },
  {
    id: "promo",
    label: "Promo depth",
    unit: "%",
    min: 0,
    max: 50,
    step: 1,
    cell: "B17",
    effect: "Raises ADS on promo-eligible SKUs -- can lift a tail SKU into hold or grow",
  },
  {
    id: "markdown",
    label: "Markdown depth",
    unit: "%",
    min: 0,
    max: 60,
    step: 1,
    cell: "B18",
    effect: "No modelled effect -- the workbook's formula set has no markdown term",
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
    effect: "Open PO x (1 + inbound/100) -- raises position, inventory value and capital locked",
  },
  {
    id: "lead",
    label: "Vendor lead",
    unit: "d",
    min: -2,
    max: 6,
    step: 1,
    cell: "B20",
    effect: "Shifts ROP/Max -- changes inventory state and range-risk classification",
  },
  {
    id: "safety",
    label: "Safety stock",
    unit: "d",
    min: -2,
    max: 5,
    step: 1,
    cell: "B21",
    effect: "Shifts ROP -- changes stock state and therefore delist eligibility",
  },
]);

/** Every lever at rest -- the setting the workbook was calculated at. */
export const BASELINE_LEVERS = Object.freeze(
  Object.fromEntries(LEVER_DEFINITIONS.map(({ id }) => [id, 0])),
);

/**
 * The four Suggested Best Action tabs, A6 spec section 7. Grow Winners is
 * the grow population; the delist population splits three ways
 * (vendor-clustered, category-imbalanced, else plain tail) so every
 * classified SKU lands in exactly one tab. Resolved upstream as
 * `best_action_tab`.
 */
export const BEST_ACTION_TABS = Object.freeze([
  { id: "delist_tail", label: "Delist Tail", recommendation: "Delist / reduce facing / stop reorder" },
  { id: "grow_winners", label: "Grow Winners", recommendation: "Grow range / add space / expand stores" },
  { id: "rebalance_space", label: "Rebalance Space", recommendation: "Rationalize tail and rebalance category" },
  { id: "vendor_brand_review", label: "Vendor/Brand Review", recommendation: "Vendor or brand review" },
]);

/** The metrics the What-If simulator compares as paired index bars (Baseline=100). */
export const SIMULATION_METRICS = Object.freeze([
  { id: "delist_candidates", label: "Delist", lowerIsBetter: true },
  { id: "grow_candidates", label: "Grow", lowerIsBetter: false },
  { id: "avg_gmroi", label: "Avg GMROI", lowerIsBetter: false },
  { id: "capital_freed", label: "Capital freed", lowerIsBetter: false },
]);

/**
 * @typedef {Object} AssortmentScope
 * @property {string} legal_entity_id  Vertical id, or "ALL".
 * @property {string} category_group   Category id, or "ALL".
 * @property {string} store_id         Store id, or "ALL".
 * @property {string} classification   One of CLASSIFICATIONS, or "ALL".
 * @property {string} sku              Free-text SKU/name/vendor/brand search.
 */

export const DEFAULT_SCOPE = Object.freeze({
  legal_entity_id: ALL,
  category_group: ALL,
  store_id: ALL,
  classification: ALL,
  sku: "",
});

/**
 * A6 spec section 11: contribution charts are store-level rollups, while
 * candidate counts and capital freed are SKU-level decision metrics. They
 * answer different questions and are not expected to tie out.
 */
export const GRAIN_NOTE =
  "Contribution/day charts roll up store-level rows. Delist/grow counts and " +
  "capital freed are SKU-level decision metrics — the two are different " +
  "measures and are not expected to reconcile against each other.";

/** A6 spec section 11: capital freed is potential, not cash in hand. */
export const CAPITAL_FREED_NOTE =
  "Capital freed is the inventory value locked in delist candidates — a " +
  "decision value, not a cash receipt. Real release depends on sell-down, " +
  "markdown execution, returns, transfers and delist timing.";

/** A6 spec section 11: GMROI here is a workbook proxy, not an accounting figure. */
export const GMROI_NOTE =
  "GMROI is a proxy: weekly margin over inventory value at one snapshot. A " +
  "true GMROI needs a time period, average inventory and cost accounting rules.";

export const KPI_FORMULAS = Object.freeze({
  delist_candidates: "count(state in {Slow-mover, Overstock, Expiry} OR low GMROI OR tail contribution)",
  grow_candidates: "count(Healthy AND high GMROI AND high contribution/day AND growth >= 1.0)",
  avg_gmroi: "inventory-weighted mean(Margin (Rp) / Inventory value)",
  tail_share_pct: "share of SKUs in the bottom contribution/day quartile",
  capital_freed: "SUM(Inventory value) over delist candidates",
  contribution_per_day: "SUM(ADS x Price x Margin %)",
});

/**
 * Validate and default a dashboard payload into the contract shape.
 *
 * @param {any} payload
 * @returns {object}
 */
export function normalizeAssortmentDashboard(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Assortment Optimization dashboard payload must be an object");
  }

  const { schema_version: version, agent } = payload;

  if (version !== SCHEMA_VERSION) {
    throw new Error(
      `Assortment Optimization dashboard schema_version ${version} is not supported ` +
        `(expected ${SCHEMA_VERSION})`,
    );
  }
  if (agent !== AGENT_ID) {
    throw new Error(`Assortment Optimization dashboard is for ${AGENT_ID}, received ${agent}`);
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
      classifications: payload.filter_options?.classifications ?? [...CLASSIFICATIONS],
    },
    formulas: payload.formulas ?? {},
    classification_thresholds: payload.classification_thresholds ?? {},
    kpi_sparklines: payload.kpi_sparklines ?? {},
    kpis: {
      delist_candidates: 0,
      grow_candidates: 0,
      avg_gmroi: 0,
      tail_share_pct: 0,
      capital_freed: 0,
      contribution_per_day: 0,
      hold_count: 0,
      sku_count: 0,
      ...(payload.kpis ?? {}),
    },
    by_vertical: payload.by_vertical ?? [],
    by_category: payload.by_category ?? [],
    by_store: payload.by_store ?? [],
    by_cluster: payload.by_cluster ?? [],
    by_channel: payload.by_channel ?? [],
    by_state: payload.by_state ?? [],
    by_legal_entity: payload.by_legal_entity ?? [],
    quadrant: payload.quadrant ?? [],
    action_preview: payload.action_preview ?? [],
    best_actions: payload.best_actions ?? {
      delist_tail: [],
      grow_winners: [],
      rebalance_space: [],
      vendor_brand_review: [],
    },
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
 * Serialize a scope into the query the backend route will accept, once one
 * exists. `ALL` and empty search are omitted so the URL stays readable.
 *
 * @param {Partial<AssortmentScope>} scope
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
