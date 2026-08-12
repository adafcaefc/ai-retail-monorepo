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
    by_route: payload.by_route ?? [],
    by_store: payload.by_store ?? [],
    by_category: payload.by_category ?? [],
    by_cluster: payload.by_cluster ?? [],
    vendors: payload.vendors ?? [],
    vendor_split: payload.vendor_split ?? [],
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
