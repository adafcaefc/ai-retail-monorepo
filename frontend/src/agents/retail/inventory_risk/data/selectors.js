/**
 * Derive an Inventory Risk dashboard payload from the workbook fixture.
 *
 * Everything here is a count, a sum, a group, or a sort. No business rule is
 * re-implemented: `state`, `is_stockout_risk`, `is_overstock` and
 * `is_slow_mover` arrive already resolved from
 * `scripts/build_inventory_risk_fixture.py`, which checks them against the
 * workbook's own `A2 Inventory Risk` totals before writing. Keep it that way —
 * a threshold typed into this file is a second definition of a rule, and the
 * copy in JavaScript is the one nobody will notice drifting.
 *
 * Pure and synchronous: same fixture plus same scope gives the same result,
 * every render and every test. No clock, no randomness.
 */

import {
  AGENT_ID,
  ALL,
  DEFAULT_SCOPE,
  EXPIRY_BUCKETS,
  EXPIRY_WATCHLIST_SIZE,
  HEALTHY_STATE,
  SCHEMA_VERSION,
  STATE_ORDER,
} from "./contract.js";

/**
 * STORE SCOPING IS NOT SUPPORTED BY THIS PROVIDER.
 *
 * `fixture.items` is chain-net: one row per SKU across the whole chain, with
 * no store dimension. Scoping KPIs to a single store needs the 16,000-row
 * SKU x store grid, which costs ~163 KB gzipped on top of this fixture — for
 * interim data, and for exactly the dimension the D365 endpoint does not yet
 * return at all.
 *
 * So `scope.store_id` is accepted and echoed back (the contract keeps it, the
 * API will honour it) but does not filter here. The store and cluster charts
 * are unaffected: they read `fixture.stores`, which is already aggregated per
 * store. To turn it on later, add the grid to the fixture builder and filter
 * `items` through it — no contract or component change is required.
 */
export const SUPPORTS_STORE_SCOPE = false;

function matchesSearch(item, term) {
  const needle = term.trim().toLowerCase();
  if (!needle) return true;
  return (
    item.sku_id.toLowerCase().includes(needle) ||
    item.name.toLowerCase().includes(needle)
  );
}

/** Apply the scope this provider can honour. See SUPPORTS_STORE_SCOPE. */
export function scopeItems(items, scope) {
  return items.filter((item) => {
    if (
      scope.legal_entity_id !== ALL &&
      item.vertical_id !== scope.legal_entity_id
    ) {
      return false;
    }
    if (
      scope.category_group !== ALL &&
      item.category_id !== scope.category_group
    ) {
      return false;
    }
    if (scope.state !== ALL && item.state !== scope.state) {
      return false;
    }
    return matchesSearch(item, scope.sku);
  });
}

function scopeStores(stores, scope) {
  if (scope.legal_entity_id === ALL) return stores;
  return stores.filter((store) => store.vertical_id === scope.legal_entity_id);
}

function sum(rows, key) {
  return rows.reduce((total, row) => total + (row[key] ?? 0), 0);
}

/** The six A2 KPIs plus slow-mover, from pre-resolved flags only. */
export function computeKpis(items) {
  const count = items.length;
  return {
    stockout_risk_skus: items.filter((item) => item.is_stockout_risk).length,
    overstock_skus: items.filter((item) => item.is_overstock).length,
    expiry_units: sum(items, "expiry_units"),
    slow_mover_skus: items.filter((item) => item.is_slow_mover).length,
    avg_dos: count ? sum(items, "dos") / count : 0,
    inventory_value: sum(items, "inv_value"),
    at_risk_value: sum(items, "at_risk_value"),
    healthy_skus: items.filter((item) => item.state === HEALTHY_STATE).length,
    sku_count: count,
  };
}

/**
 * Stacked horizontal bar: one bar per state, segmented by category
 * (A2 spec section 5a). States with no rows in scope are dropped rather than
 * drawn as empty bars.
 */
export function computeAtRiskByState(items) {
  const byState = new Map();

  for (const item of items) {
    let bucket = byState.get(item.state);
    if (!bucket) {
      bucket = { state: item.state, total: 0, segments: new Map() };
      byState.set(item.state, bucket);
    }
    bucket.total += item.at_risk_value;

    const segment = bucket.segments.get(item.category_id);
    if (segment) {
      segment.value += item.at_risk_value;
    } else {
      bucket.segments.set(item.category_id, {
        category_id: item.category_id,
        label: item.category_name,
        value: item.at_risk_value,
      });
    }
  }

  return STATE_ORDER.filter((state) => byState.has(state)).map((state) => {
    const bucket = byState.get(state);
    return {
      state,
      total: bucket.total,
      segments: [...bucket.segments.values()].sort((a, b) => b.value - a.value),
    };
  });
}

function groupByCategory(items, key) {
  const grouped = new Map();
  for (const item of items) {
    const row = grouped.get(item.category_id);
    if (row) {
      row.value += item[key];
    } else {
      grouped.set(item.category_id, {
        category_id: item.category_id,
        label: item.category_name,
        value: item[key],
      });
    }
  }
  return [...grouped.values()].sort((a, b) => b.value - a.value);
}

/** Donut share of inventory value by category (A2 spec section 5b). */
export function computeValueByCategory(items) {
  const rows = groupByCategory(items, "inv_value");
  const total = rows.reduce((running, row) => running + row.value, 0);
  return rows.map((row) => ({
    ...row,
    share: total ? row.value / total : 0,
  }));
}

/** Vertical bar of at-risk value by category (A2 spec section 6). */
export function computeAtRiskByCategory(items) {
  return groupByCategory(items, "at_risk_value");
}

/**
 * Gross per-store stockout counts, worst first (A2 spec section 6).
 * See GROSS_VS_NET_NOTE in the contract: these exceed the chain-net headline
 * on purpose.
 */
export function computeStockoutByStore(stores) {
  return [...stores]
    .map((store) => ({
      store_id: store.store_id,
      label: store.name,
      cluster: store.cluster,
      stockout_risk_count: store.stockout_risk_count,
      at_risk_count: store.at_risk_count,
      healthy_count: store.sku_count - store.at_risk_count,
      sku_count: store.sku_count,
      at_risk_value: store.at_risk_value,
    }))
    .sort((a, b) => b.stockout_risk_count - a.stockout_risk_count);
}

/** Gross at-risk value by store cluster (A2 spec section 6). */
export function computeAtRiskByCluster(stores) {
  const grouped = new Map();
  for (const store of stores) {
    const row = grouped.get(store.cluster);
    if (row) {
      row.value += store.at_risk_value;
      row.store_count += 1;
    } else {
      grouped.set(store.cluster, {
        cluster: store.cluster,
        value: store.at_risk_value,
        store_count: 1,
      });
    }
  }
  return [...grouped.values()].sort((a, b) => b.value - a.value);
}

/** Roll store -> legal entity (A2 spec section 6, `#ch-dim-le`). */
export function computeAtRiskByLegalEntity(stores, legalEntities) {
  const labelOf = new Map(
    legalEntities.map((entity) => [entity.value, entity.label]),
  );
  const grouped = new Map();

  for (const store of stores) {
    const row = grouped.get(store.vertical_id);
    if (row) {
      row.value += store.at_risk_value;
    } else {
      grouped.set(store.vertical_id, {
        legal_entity_id: store.vertical_id,
        label: labelOf.get(store.vertical_id) ?? store.vertical_id,
        value: store.at_risk_value,
      });
    }
  }
  return [...grouped.values()].sort((a, b) => b.value - a.value);
}

/**
 * Shelf-life buckets plus the shortest-dated watchlist (A2 spec section 6).
 * Only perishable rows carrying expiry units participate; the workbook leaves
 * the rest at zero.
 */
export function computeExpiryTimeline(items) {
  const atRisk = items.filter((item) => item.expiry_units > 0);

  const buckets = EXPIRY_BUCKETS.map((bucket) => ({
    id: bucket.id,
    label: bucket.label,
    units: 0,
  }));

  for (const item of atRisk) {
    const days = item.shelf_life_days ?? 0;
    const index = EXPIRY_BUCKETS.findIndex(
      (bucket) => bucket.max === null || days <= bucket.max,
    );
    buckets[index === -1 ? buckets.length - 1 : index].units += item.expiry_units;
  }

  const watchlist = [...atRisk]
    .sort(
      (a, b) =>
        (a.shelf_life_days ?? 0) - (b.shelf_life_days ?? 0) ||
        b.expiry_units - a.expiry_units,
    )
    .slice(0, EXPIRY_WATCHLIST_SIZE)
    .map((item) => ({
      sku_id: item.sku_id,
      name: item.name,
      shelf_life_days: item.shelf_life_days,
      units: item.expiry_units,
    }));

  return { buckets, watchlist };
}

/** Severity first, then value (A2 spec section 5c). */
export function computeRiskRegister(items) {
  return [...items].sort(
    (a, b) => a.severity_rank - b.severity_rank || b.inv_value - a.inv_value,
  );
}

/**
 * Build the full dashboard payload for one scope.
 *
 * @param {object} fixture Parsed `fixture.json`.
 * @param {Partial<import("./contract.js").InventoryRiskScope>} [scope]
 * @returns {object} A payload matching the dashboard contract.
 */
export function buildDashboardFromFixture(fixture, scope = {}) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  const items = scopeItems(fixture.items, merged);
  const stores = scopeStores(fixture.stores, merged);
  const legalEntities = fixture.filter_options.legal_entities;

  // Categories depend on the selected vertical, so the filter bar can reset a
  // child selection the new parent invalidates without a second load.
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
    scope: merged,
    filter_options: {
      legal_entities: legalEntities,
      categories,
      stores: storeOptions,
      states: fixture.filter_options.states,
    },
    kpis: computeKpis(items),
    at_risk_by_state: computeAtRiskByState(items),
    value_by_category: computeValueByCategory(items),
    at_risk_by_category: computeAtRiskByCategory(items),
    stockout_by_store: computeStockoutByStore(stores),
    at_risk_by_cluster: computeAtRiskByCluster(stores),
    at_risk_by_legal_entity: computeAtRiskByLegalEntity(stores, legalEntities),
    expiry_timeline: computeExpiryTimeline(items),
    risk_register: computeRiskRegister(items),
    reference_by_vertical: fixture.reference_by_vertical,
  };
}
