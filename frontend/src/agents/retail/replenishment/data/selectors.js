/**
 * Derive a Replenishment payload from the workbook fixture.
 *
 * Counts, sums, groups and sorts. Every rule the board depends on — which SKUs
 * need reordering, how much, at what price, on which route — was resolved in
 * `scripts/build_replenishment_fixture.py` against the catalogue formulas and
 * checked line by line against `A3 Replenishment` before the fixture was
 * written. Nothing here re-decides any of it.
 */

import { AGENT_ID, ALL, DEFAULT_SCOPE, ROUTE_ORDER, SCHEMA_VERSION } from "./contract.js";

const sum = (rows, key) => rows.reduce((total, row) => total + (row[key] ?? 0), 0);

function matchesSearch(line, term) {
  const needle = term.trim().toLowerCase();
  if (!needle) return true;
  return (
    line.sku_id.toLowerCase().includes(needle) ||
    line.name.toLowerCase().includes(needle)
  );
}

/**
 * Apply the scope.
 *
 * `reorder_only` defaults on, which is the difference between a purchase-order
 * screen and an inventory report: a buyer opening this board is looking at
 * what has to be ordered today, not at all 800 SKUs. The toggle is there
 * because the fill-rate KPI needs the denominator.
 */
export function scopeLines(lines, scope) {
  return lines.filter((line) => {
    if (scope.legal_entity_id !== ALL && line.vertical_id !== scope.legal_entity_id) {
      return false;
    }
    if (scope.category_group !== ALL && line.category_id !== scope.category_group) {
      return false;
    }
    if (scope.route !== ALL && line.route !== scope.route) return false;
    if (scope.reorder_only && !line.is_reorder) return false;
    return matchesSearch(line, scope.sku);
  });
}

function scopeStores(stores, scope) {
  if (scope.legal_entity_id === ALL) return stores;
  return stores.filter((store) => store.vertical_id === scope.legal_entity_id);
}

/**
 * The six A3 KPIs, plus the two figures that make the board actionable.
 *
 * `fill_rate_pct` and `avg_cover_days` are measured over EVERY line in scope,
 * not only the ones being reordered — a fill rate computed over the reorder
 * list alone would always be zero, and a cover average over it would describe
 * the problem rather than the chain.
 */
export function computeKpis(lines, allLines) {
  const need = lines.filter((line) => line.is_reorder);
  const universe = allLines.length ? allLines : lines;
  const healthy = universe.filter((line) => !line.is_reorder).length;

  return {
    skus_to_reorder: need.length,
    order_units: sum(lines, "order_qty_sales"),
    order_value_retail: sum(lines, "order_value_retail"),
    order_value_cost: sum(lines, "order_value_cost"),
    inbound_open_po: sum(lines, "open_po"),
    fill_rate_pct: universe.length ? (healthy / universe.length) * 100 : 0,
    avg_cover_days: universe.length ? sum(universe, "dos") / universe.length : 0,
    // What switching every line to its cheapest quoted vendor would recover.
    // The only number on this board that proposes something.
    recoverable_saving: sum(lines, "saving_vs_designated"),
    line_count: lines.length,
  };
}

function groupBy(rows, key, label, extra = () => ({})) {
  const grouped = new Map();
  for (const row of rows) {
    const id = row[key];
    const bucket = grouped.get(id) || {
      id,
      label: label(row),
      line_count: 0,
      order_units: 0,
      order_value_retail: 0,
      order_value_cost: 0,
      saving: 0,
      ...extra(row),
    };
    bucket.line_count += 1;
    bucket.order_units += row.order_qty_sales ?? 0;
    bucket.order_value_retail += row.order_value_retail ?? 0;
    bucket.order_value_cost += row.order_value_cost ?? 0;
    bucket.saving += row.saving_vs_designated ?? 0;
    grouped.set(id, bucket);
  }
  return [...grouped.values()];
}

/** A3 spec 5a: order value by route, in lead-time order rather than by size. */
export function computeByRoute(lines, routes) {
  const byId = new Map(
    groupBy(lines, "route", (row) => row.route).map((row) => [row.id, row]),
  );

  return ROUTE_ORDER.map((id) => {
    const definition = routes.find((route) => route.id === id);
    const bucket = byId.get(id);
    return {
      id,
      label: definition?.label ?? id,
      added_days: definition?.added_days ?? 0,
      note: definition?.note ?? "",
      line_count: bucket?.line_count ?? 0,
      order_units: bucket?.order_units ?? 0,
      order_value_retail: bucket?.order_value_retail ?? 0,
      order_value_cost: bucket?.order_value_cost ?? 0,
      saving: bucket?.saving ?? 0,
    };
  });
}

/** A3 spec 5b: order value by store, largest first. */
export function computeByStore(stores) {
  return [...stores]
    .map((store) => ({
      id: store.store_id,
      label: store.name,
      legal_entity_id: store.vertical_id,
      cluster: store.cluster,
      line_count: store.reorder_count,
      order_units: store.order_units,
      order_value_retail: store.order_value_retail,
      open_po: store.open_po,
    }))
    .sort((a, b) => b.order_value_retail - a.order_value_retail);
}

export function computeByCategory(lines) {
  return groupBy(lines, "category_id", (row) => row.category_label)
    .map((row) => ({ ...row, legal_entity_id: undefined }))
    .sort((a, b) => b.order_value_retail - a.order_value_retail);
}

export function computeByCluster(stores) {
  const grouped = new Map();
  for (const store of stores) {
    const bucket = grouped.get(store.cluster) || {
      id: store.cluster,
      label: store.cluster,
      store_count: 0,
      order_value_retail: 0,
      order_units: 0,
    };
    bucket.store_count += 1;
    bucket.order_value_retail += store.order_value_retail;
    bucket.order_units += store.order_units;
    grouped.set(store.cluster, bucket);
  }
  return [...grouped.values()].sort(
    (a, b) => b.order_value_retail - a.order_value_retail,
  );
}

/**
 * Where the money would go, and where it could go instead.
 *
 * Grouped by the vendor the trade agreement designates, with the part that a
 * cheaper quote would recover shown against it. `saving_vs_designated` is the
 * workbook's own column; nothing here recalculates a price.
 */
export function computeVendorSplit(lines) {
  const grouped = new Map();
  for (const line of lines) {
    const bucket = grouped.get(line.designated_vendor) || {
      vendor: line.designated_vendor,
      line_count: 0,
      order_value_cost: 0,
      saving: 0,
      switchable_lines: 0,
    };
    bucket.line_count += 1;
    bucket.order_value_cost += line.order_value_cost;
    bucket.saving += line.saving_vs_designated;
    if (line.saving_vs_designated > 0) bucket.switchable_lines += 1;
    grouped.set(line.designated_vendor, bucket);
  }
  return [...grouped.values()].sort(
    (a, b) => b.order_value_cost - a.order_value_cost,
  );
}

/**
 * A3 spec 5c: the purchase order itself, biggest commitment first.
 *
 * Sorted by cost rather than by shortfall: a buyer works down a PO by what it
 * spends, and the largest shortfall is not always the largest cheque.
 */
export function computePurchaseOrder(lines) {
  return [...lines]
    .filter((line) => line.order_qty_sales > 0)
    .sort((a, b) => b.order_value_cost - a.order_value_cost)
    .map((line) => ({
      sku_id: line.sku_id,
      name: line.name,
      category_label: line.category_label,
      route: line.route,
      on_hand: line.on_hand,
      open_po: line.open_po,
      position: line.position,
      rop: line.rop,
      max: line.max,
      order_qty_sales: line.order_qty_sales,
      order_qty_buy: line.order_qty_buy,
      buy_uom: line.buy_uom,
      pack_factor: line.pack_factor,
      order_value_cost: line.order_value_cost,
      order_value_retail: line.order_value_retail,
      designated_vendor: line.designated_vendor,
      best_price_vendor: line.best_price_vendor,
      saving_vs_designated: line.saving_vs_designated,
      lead_days: line.lead_days,
    }));
}

export function buildDashboardFromFixture(fixture, scope = {}) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  const lines = scopeLines(fixture.lines, merged);

  // The denominator for fill rate and cover: the same scope, but without the
  // reorder filter, because those two describe the chain rather than the order.
  const universe = scopeLines(fixture.lines, { ...merged, reorder_only: false });
  const stores = scopeStores(fixture.stores, merged);

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

  return {
    schema_version: SCHEMA_VERSION,
    agent: AGENT_ID,
    as_of: fixture.generated_at,
    is_mock: fixture.is_mock,
    note: fixture.note,
    derivation: fixture.derivation,
    scope: merged,
    routes: fixture.routes,
    filter_options: {
      legal_entities: fixture.filter_options.legal_entities,
      categories,
      stores: storeOptions,
      routes: fixture.filter_options.routes,
    },
    kpis: computeKpis(lines, universe),
    by_route: computeByRoute(lines, fixture.routes),
    by_store: computeByStore(stores),
    by_category: computeByCategory(lines),
    by_cluster: computeByCluster(stores),
    vendors: fixture.vendors,
    vendor_split: computeVendorSplit(lines),
    purchase_order: computePurchaseOrder(lines),
    reference_by_vertical: fixture.reference_by_vertical,
  };
}
