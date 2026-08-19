/**
 * Pricing & Markdown (Agent 5) dashboard data contract.
 *
 * The single shape both data sources produce: the local fixture today, and
 * `GET /api/html/dashboard/retail.pricing_markdown` once a backend module
 * exists. Every presentation component reads this shape and nothing else, so
 * the cutover to the API changes one file (`dashboardData.js`) and no
 * component.
 *
 * NUMBERS ARE RAW. Components format at render time. Never store a formatted
 * string here.
 *
 * NO THRESHOLD LIVES IN JAVASCRIPT. State classification and the
 * best-action tab are resolved upstream in
 * `scripts/build_pricing_markdown_fixture.py`. This module and its
 * selectors only count and sum.
 *
 * WHY at_risk_value / recoverable_value ARE NOT SOURCED FROM THE A5 SHEET.
 * A prior audit of the workbook (`Dataset_AI_Retail.xlsx`, sheets "AUDIT
 * Root Cause" / "AUDIT Fix Register") found the A5 Pricing & Markdown
 * sheet's own cells (C6:G13) hold stale hardcoded values, not live
 * formulas. The fixture instead sums ENGINE_STORE (store grain) per the
 * audit's own recommended fix (F-05) -- see the fixture builder script for
 * the full account.
 */

export const AGENT_ID = "retail.pricing_markdown";
export const SCHEMA_VERSION = 1;

/** The dropdowns' "clear" option. */
export const ALL = "ALL";

/** A5 spec section 6, #ch-dim-state. */
export const STATE_ORDER = Object.freeze([
  "Stockout",
  "Low",
  "Expiry",
  "Overstock",
  "Slow-mover",
  "Healthy",
]);

export const HEALTHY_STATE = "Healthy";

/** A5 spec section 2: markdown candidates are exactly these three states. */
export const CANDIDATE_STATES = Object.freeze(["Expiry", "Overstock", "Slow-mover"]);

/**
 * What-If levers, A5 spec section 9a -> `Constants` B16-B21.
 *
 * `demand`, `promo`, `inbound`, `lead`, `safety` flow through to `state` via
 * the same cascade `inventory_risk` runs, and state feeds f12 (at-risk) and
 * f23 (gross markdown exposure) in the browser engine. `markdown` is
 * different from the other five: it does not move `state`, it moves how much
 * of the gross exposure f14-recoverable-at-risk-value converts to
 * `recoverable_value` -- the one lever this formula set actually models a
 * depth-to-recovery term for.
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
    effect: "ADS x (1 + demand/100) -- changes DoS, can move a SKU into or out of a markdown state",
  },
  {
    id: "promo",
    label: "Promo depth",
    unit: "%",
    min: 0,
    max: 50,
    step: 1,
    cell: "B17",
    effect: "Raises ADS on promo-eligible SKUs -- can pull a Slow-mover back to Healthy",
  },
  {
    id: "markdown",
    label: "Markdown depth",
    unit: "%",
    min: 0,
    max: 60,
    step: 1,
    cell: "B18",
    effect: "Widens the recovery depth f14 applies to gross exposure -- deeper markdown, more of the gross recovered, up to a 65% cap",
    modelled: true,
  },
  {
    id: "inbound",
    label: "Open PO",
    unit: "%",
    min: -40,
    max: 60,
    step: 5,
    cell: "B19",
    effect: "Open PO x (1 + inbound/100) -- raises Position, can push a SKU into Overstock",
  },
  {
    id: "lead",
    label: "Vendor lead",
    unit: "d",
    min: -2,
    max: 6,
    step: 1,
    cell: "B20",
    effect: "Shifts ROP -- changes the Stockout/Low boundary",
  },
  {
    id: "safety",
    label: "Safety stock",
    unit: "d",
    min: -2,
    max: 5,
    step: 1,
    cell: "B21",
    effect: "Shifts ROP -- fewer stockouts, more capital tied up in position",
  },
]);

/** Every lever at rest -- the setting the workbook was calculated at. */
export const BASELINE_LEVERS = Object.freeze(
  Object.fromEntries(LEVER_DEFINITIONS.map(({ id }) => [id, 0])),
);

/**
 * The four Suggested Best Action tabs, A5 spec section 7. `expiry_markdown`,
 * `overstock_clearance` and `slow_mover_price_cut` map 1:1 to their state.
 * `suppress_reorder` is the Overstock subset that still carries open PO. The
 * four are a clean partition of the candidate population, resolved upstream
 * as `best_action_tab` on each item -- never recomputed here.
 */
export const BEST_ACTION_TABS = Object.freeze([
  { id: "expiry_markdown", label: "Expiry Markdown", recommendation: "Immediate markdown / short expiry clearance" },
  { id: "overstock_clearance", label: "Overstock Clearance", recommendation: "Clearance markdown and block replenishment" },
  { id: "slow_mover_price_cut", label: "Slow-mover Price Cut", recommendation: "Price cut or targeted promo" },
  { id: "suppress_reorder", label: "Suppress Reorder", recommendation: "Suppress reorder and clear existing position first" },
]);

/** The metrics the What-If simulator compares as paired index bars (Baseline=100). */
export const SIMULATION_METRICS = Object.freeze([
  { id: "markdown_candidates", label: "Candidates", lowerIsBetter: false },
  { id: "at_risk_value", label: "At-risk value", lowerIsBetter: true },
  { id: "recoverable_value", label: "Recoverable", lowerIsBetter: false },
  { id: "write_off_value", label: "Write-off", lowerIsBetter: true },
]);

/**
 * The What-If metrics strip, A5 spec section 9c (#sim-metrics) -- distinct
 * from SIMULATION_METRICS above, which drives the paired index-bar chart.
 * Each tile shows the scenario value with a delta-vs-baseline badge.
 */
export const SIMULATION_STRIP_METRICS = Object.freeze([
  { id: "at_risk_value", label: "At-risk", lowerIsBetter: true },
  { id: "recoverable_value", label: "Recoverable", lowerIsBetter: false },
  { id: "write_off_value", label: "Write-off", lowerIsBetter: true },
  { id: "recovery_rate_pct", label: "Recovery rate", lowerIsBetter: false },
]);

/**
 * @typedef {Object} PricingScope
 * @property {string} legal_entity_id  Vertical id, or "ALL".
 * @property {string} category_group   Category id, or "ALL".
 * @property {string} store_id         Store id, or "ALL".
 * @property {string} state            One of STATE_ORDER, or "ALL".
 * @property {string} sku              Free-text SKU/name/vendor/brand search.
 */

export const DEFAULT_SCOPE = Object.freeze({
  legal_entity_id: ALL,
  category_group: ALL,
  store_id: ALL,
  state: ALL,
  sku: "",
});

/**
 * A5 spec section 11: chain-net headline vs. store-level gross dimension
 * charts. They will not reconcile 1:1 -- that is by design, not a bug.
 */
export const GRAIN_NOTE =
  "At-risk and recoverable value are summed from ENGINE_STORE (store grain). " +
  "Store, cluster and channel breakdowns are gross and will not reconcile " +
  "1:1 with the SKU-level headline, which nets across a SKU's own stores.";

/** A5 spec section 11: candidates exclude Stockout/Low -- that is Agent 3's territory. */
export const CANDIDATE_SCOPE_NOTE =
  "Markdown candidates are SKUs with at least one store in Expiry, Overstock " +
  "or Slow-mover. Stockout and Low are inventory risk states handled by " +
  "Agent 3 Replenishment.";

export const KPI_FORMULAS = Object.freeze({
  markdown_candidates: "count(SKUs with >=1 store in {Expiry, Overstock, Slow-mover})",
  avg_depth_pct: "weighted avg markdown depth by candidate value (vertical-level, workbook reference)",
  at_risk_value: "SUM(ENGINE_STORE.at_risk) across a SKU's stores",
  recoverable_value:
    "SUM(ENGINE_STORE.markdown_recoverable) across a SKU's candidate-state stores; " +
    "re-simulated as f14(f23(state, position, ads, shelf_life_days, max, price), state, elasticity, markdown_lever) when a lever moves",
  write_off_value: "at-risk value - recoverable value",
  comp_idx: "mean(SKU_Master.comp_idx) over candidates",
});

/**
 * Validate and default a dashboard payload into the contract shape.
 *
 * @param {any} payload
 * @returns {import("./contract.js").PricingDashboard}
 */
export function normalizePricingDashboard(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Pricing & Markdown dashboard payload must be an object");
  }

  const { schema_version: version, agent } = payload;

  if (version !== SCHEMA_VERSION) {
    throw new Error(
      `Pricing & Markdown dashboard schema_version ${version} is not supported ` +
        `(expected ${SCHEMA_VERSION})`,
    );
  }
  if (agent !== AGENT_ID) {
    throw new Error(`Pricing & Markdown dashboard is for ${AGENT_ID}, received ${agent}`);
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
      states: payload.filter_options?.states ?? [...STATE_ORDER],
    },
    formulas: payload.formulas ?? {},
    kpi_sparklines: payload.kpi_sparklines ?? {},
    kpis: {
      markdown_candidates: 0,
      avg_depth_pct: 0,
      at_risk_value: 0,
      recoverable_value: 0,
      write_off_value: 0,
      comp_idx: 0,
      recovery_rate_pct: 0,
      ...(payload.kpis ?? {}),
    },
    by_vertical: payload.by_vertical ?? [],
    by_category: payload.by_category ?? [],
    by_store: payload.by_store ?? [],
    by_cluster: payload.by_cluster ?? [],
    by_channel: payload.by_channel ?? [],
    by_state: payload.by_state ?? [],
    by_legal_entity: payload.by_legal_entity ?? [],
    candidates: payload.candidates ?? [],
    best_actions: payload.best_actions ?? {
      expiry_markdown: [],
      overstock_clearance: [],
      slow_mover_price_cut: [],
      suppress_reorder: [],
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
 * @param {Partial<PricingScope>} scope
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
