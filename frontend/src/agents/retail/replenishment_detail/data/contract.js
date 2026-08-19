/**
 * The shape Replenishment Detail renders.
 *
 * Same discipline as its sibling boards: one normalizer at the boundary,
 * presentation components downstream of it, and no component that knows where
 * the payload came from.
 *
 * Unlike the other five Retail boards, this one has NO checked-in fixture. It
 * reads the API or it reports an error — see `dashboardData.js` for why. So
 * the normalizer's job here is narrower than its siblings': there is one
 * producer, and what it guards against is a backend that has moved on, not two
 * sources that might disagree.
 */

export const AGENT_ID = "retail.replenishment_detail";
export const SCHEMA_VERSION = 1;

export const ALL = "ALL";

/**
 * Reorder status is three-valued, not a boolean.
 *
 * Agent 3 carries a `reorder_only` checkbox, because a purchase plan is either
 * showing you what to buy or showing you everything. A detail page is also
 * asked the third question — "what did we decide *not* to order, and why" —
 * and a checkbox cannot express it.
 */
export const REORDER_STATUS = Object.freeze([
  { value: "YES", label: "Needs reorder" },
  { value: ALL, label: "All lines" },
  { value: "NO_ORDER", label: "No order" },
]);

/** Spec section 10.1. The order is most-actionable first. */
export const ELIGIBILITY_LABELS = Object.freeze({
  ELIGIBLE: "Ready",
  BLOCKED: "Blocked",
  NO_ORDER: "No order",
});

/**
 * Spec section 14, in the module's own order — most-blocking first.
 *
 * Each label says what the exception *prevents*, not merely what is absent. A
 * planner reading "Missing pack factor" has to already know that the
 * sales-to-buy conversion depends on it; one reading the consequence does not.
 */
export const EXCEPTION_LABELS = Object.freeze({
  MISSING_PACK_FACTOR: "No pack factor — cannot convert to buy units",
  MISSING_BUY_UOM: "No buy UOM — cannot state what a pack is",
  MISSING_VENDOR: "No designated vendor — nothing to source against",
  MISSING_TA_PRICE: "No trade-agreement price — cannot value or approve",
  INVALID_ROP_MAX: "ROP/Max pair is invalid — Max is below ROP",
  NEGATIVE_INVENTORY_INPUT: "Negative inventory input",
  FORMULA_TIE_OUT_FAILED: "Stored amount or saving does not reconcile",
});

/**
 * The formula behind each KPI tile, shown on hover (spec section 7).
 *
 * Order qty (buy) has no total here on purpose. Summing Crates, Pallets and
 * Packs is arithmetically valid and operationally meaningless, so the tile
 * reports the UOM count and the breakdown panel carries the quantities.
 */
export const KPI_FORMULAS = Object.freeze({
  reorder_sku_count: "count( Position < ROP ), strictly below",
  order_qty_sales: "Σ max(0, Max − Position), sales units",
  buy_uom_count: "distinct buy UOMs across reorder lines — see the breakdown",
  purchase_amount: "Σ order qty (buy) × pack factor × unit price",
  potential_saving: "Σ ordered sales units × (designated − best price)",
  alternate_vendor_count: "count( best-price vendor ≠ designated AND saving > 0 )",
});

/**
 * Column formulas for the detail grid, shown per cell.
 *
 * "Position", "Amount" and "Saving" mean different things in different retail
 * systems, and a reader who cannot check what a number counts will eventually
 * assume the wrong one.
 */
export const LINE_FORMULAS = Object.freeze({
  qty_on_hand: "On-hand = max(0, Position − Open PO)",
  open_po: "Open PO = ordered, not yet received. No ETA in this data",
  position: "Position = On-hand + Open PO",
  demand_per_day: "Average daily sales from the engine",
  rop: "ROP = ADS × (Lead + Safety)",
  max: "Max = ADS × (Lead + Safety + 4). Must be ≥ ROP",
  is_reorder: "YES when Position < ROP. Equality does not trigger",
  order_qty_sales: "Order (sales) = max(0, Max − Position)",
  order_qty_buy: "Order (buy) = CEILING(Order sales ÷ pack factor)",
  ordered_sales_units: "Ordered units = Order (buy) × pack factor",
  rounding_uplift: "Uplift = Ordered units − Order (sales), from whole packs",
  unit_price_ta: "Trade-agreement price, per SALES unit",
  amount: "Amount = Order (buy) × pack factor × unit price",
  best_price: "Lowest valid candidate price, per sales unit",
  saving_vs_designated: "Saving = Ordered units × (designated − best price)",
});

/**
 * Unit price is per sales unit, and this is the note that says so.
 *
 * Spec section 17, finding 5. Labelling it "per Crate" understates a
 * pack-factor-12 line twelvefold, and the mistake is invisible: the number
 * still looks like a price and the total still looks like money.
 */
export const PRICE_BASIS_NOTE =
  "Unit price and best price are per SALES unit, not per buy UOM. Amount " +
  "multiplies by the pack factor for that reason.";

/**
 * Why the ordered quantity exceeds the requirement.
 *
 * Spec section 6.4. The overshoot is correct behaviour — a purchase order buys
 * whole Crates — so the grid shows the requirement and what will actually
 * arrive as separate columns rather than reconciling them away.
 */
export const PACK_ROUNDING_NOTE =
  "Buy quantities round up to whole packs, so a line orders a little more " +
  "than its shortfall. The uplift column is that difference.";

/** Spec section 17, finding 9. Why the buy-quantity KPI is not a total. */
export const MIXED_UOM_NOTE =
  "Buy quantities are not additive across Crates, Pallets and Packs. They " +
  "are segmented by UOM rather than summed.";

/**
 * What this sheet cannot answer, stated on the board rather than discovered.
 *
 * Spec section 17, findings 1 and 7. A planner who expects a store filter and
 * does not find one should be told why, not left to assume it is missing.
 */
export const GRAIN_NOTE =
  "One row per SKU. This sheet carries no store, run id, approval state or " +
  "ERP document, so it is a recommendation snapshot rather than an execution " +
  "ledger.";

/** @typedef {object} ReplenishmentDetailScope */
export const DEFAULT_SCOPE = Object.freeze({
  // Server-side: these two narrow the SQL.
  legal_entity_id: ALL,
  category_group: ALL,
  // Client-side: the board holds all 800 rows and narrows them itself.
  sku: "",
  reorder_status: "YES",
  designated_vendor: ALL,
  best_price_vendor: ALL,
  buy_uom: ALL,
  eligibility: ALL,
  saving_only: false,
  min_amount: "",
  max_amount: "",
});

/** Default sort, spec section 8.1: Amount desc, then Saving desc, then Item asc. */
export const DEFAULT_SORT = Object.freeze({ by: "amount", direction: "desc" });

export function normalizeReplenishmentDetailDashboard(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Replenishment Detail payload must be an object");
  }
  if (payload.schema_version !== SCHEMA_VERSION) {
    throw new Error(
      `Replenishment Detail schema_version ${payload.schema_version} is ` +
        `not supported (expected ${SCHEMA_VERSION})`,
    );
  }
  if (payload.agent !== AGENT_ID) {
    throw new Error(
      `Replenishment Detail is for ${AGENT_ID}, received ${payload.agent}`,
    );
  }

  /*
   * Declared, or it is dropped — this returns an explicit object, so a block
   * the selectors add and this list omits never reaches a component. That is
   * how the KPI charts once went missing on Inventory Risk, and the regression
   * test for it asserts through the rendered board rather than through the
   * selector, because a selector test would have passed.
   */
  return {
    schema_version: SCHEMA_VERSION,
    agent: AGENT_ID,
    as_of: payload.as_of ?? "",
    is_mock: payload.is_mock === true,
    note: payload.note ?? "",
    scope: { ...DEFAULT_SCOPE, ...(payload.scope ?? {}) },
    formulas: payload.formulas ?? {},
    filter_options: {
      legal_entities: payload.filter_options?.legal_entities ?? [],
      categories: payload.filter_options?.categories ?? [],
      // Derived from the rows rather than served: the backend's filter_options
      // carries entities and categories only.
      vendors: payload.filter_options?.vendors ?? [],
      best_price_vendors: payload.filter_options?.best_price_vendors ?? [],
      buy_uoms: payload.filter_options?.buy_uoms ?? [],
    },
    kpis: {
      reorder_sku_count: 0,
      skus_in_scope: 0,
      order_qty_sales: 0,
      ordered_sales_units: 0,
      rounding_uplift: 0,
      purchase_amount: 0,
      potential_saving: 0,
      alternate_vendor_count: 0,
      blocked_count: 0,
      buy_uom_count: 0,
      line_count: 0,
      ...(payload.kpis ?? {}),
    },
    lines: payload.lines ?? [],
    by_uom: payload.by_uom ?? [],
    exception_counts: payload.exception_counts ?? {},
    quotes_by_sku: payload.quotes_by_sku ?? {},
    quote_terms: payload.quote_terms ?? null,
    vendors: payload.vendors ?? [],
    reference_by_vertical: payload.reference_by_vertical ?? [],
  };
}

/**
 * Serialize a scope into the query the backend route will accept.
 *
 * ONLY the two filters the API can actually narrow by. The other nine are
 * applied in `selectors.js` over rows already on the page, and sending them
 * would come back named in `ignored_filters` — which nothing on the frontend
 * reads, so the board would show chain-wide figures under a filtered heading.
 * `buy_uom` and friends are not fields of `DashboardScope` at all, and the
 * route answers an unknown filter with a 400 rather than dropping it.
 */
export function serializeScope(scope) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  const query = {};
  for (const key of ["legal_entity_id", "category_group"]) {
    const value = merged[key];
    if (value === ALL || value === "" || value == null) continue;
    query[key] = value;
  }
  return query;
}
