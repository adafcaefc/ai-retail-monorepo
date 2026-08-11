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
 * @property {number} overstock_skus     Count of `DoS > 15`.
 * @property {number} expiry_units       Sum of units past shelf-life cover.
 * @property {number} slow_mover_skus    Count of `growth < 1 && DoS > 10`.
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
  overstock_skus: "count( DoS > 15 ) · excess = Σ (Position − Max) × price",
  expiry_units: "Σ max(0, Position − ADS × shelf-life)",
  slow_mover_skus: "count( growth < 1.0 AND DoS > 10 )",
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
    },
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
