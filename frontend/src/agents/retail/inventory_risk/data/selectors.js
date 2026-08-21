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
  PROJECTION_DAYS,
  REPLENISH_STATES,
  PROJECTION_HORIZONS_WEEKS,
  SCHEMA_VERSION,
  STATE_ORDER,
  horizonDays,
  resolveHorizonWeeks,
  resolveDemandModel,
  FLAT_SEASONALITY,
} from "./contract.js";
import {
  dosHistogram,
  growthHistogram,
  topGroups,
} from "../../common/distributions.js";
import { dailyFactors } from "../../common/demandModel.js";
import { buildDrilldown } from "./drilldown.js";
import { BASELINE_LEVERS, createEngine, isBaseline } from "./engine.js";

/**
 * STORE SCOPING IS SUPPORTED, AND THE GRID IS NOW WHAT WE SHIP.
 *
 * `items` is ENGINE_STORE grain: one row per SKU x store, 16,000 of them. It
 * used to be the 800-row chain-net rollup, with a store view reconstructed on
 * demand by `atStore` from four carried numbers — clever, proven against every
 * grid row, and answering the wrong question. The cards counted a population
 * the workbook's own dropdown never shows: 37 slow movers where the grid holds
 * 75 distinct SKUs across 755 rows.
 *
 * So selecting a store now NARROWS the rows rather than replacing the
 * measurement with a derived one. `scopeItems` filters on `store_id` like any
 * other field.
 *
 * THE ONE RULE THIS GRAIN IMPOSES, and it is easy to get wrong:
 *
 *   counts  -> DISTINCT sku_id. A SKU sits in ~20 stores and can be Slow-mover
 *              in several, so `.length` reports rows (755) where the card must
 *              report SKUs (75).
 *   money   -> sum every row. Each row's exposure is real and additive.
 *
 * `reference_by_vertical` still carries the `A2 Inventory Risk` sheet's
 * figures, which are CHAIN-NET (overstock 26, stockout-risk 345). They are a
 * benchmark from the other grain, not a target these tiles are expected to
 * hit — see GROSS_VS_NET_NOTE.
 */
export const SUPPORTS_STORE_SCOPE = true;

/** Distinct SKUs among the rows a predicate accepts. See the rule above. */
function distinctSkus(items, predicate) {
  const seen = new Set();
  for (const item of items) {
    if (predicate(item)) seen.add(item.sku_id);
  }
  return seen.size;
}

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
    // Store is an intrinsic field on the row now, not a re-derivation. This
    // clause did not exist while `items` was chain-net — there was nothing to
    // filter — and its absence would silently leave every store's rows in the
    // set at this grain.
    if (scope.store_id !== ALL && item.store_id !== scope.store_id) {
      return false;
    }
    return matchesSearch(item, scope.sku);
  });
}

function scopeStores(stores, scope) {
  // A named store narrows to itself, so the store and cluster charts describe
  // the same slice the tiles do rather than the whole vertical behind it.
  if (scope.store_id !== ALL) {
    return stores.filter((store) => store.store_id === scope.store_id);
  }
  if (scope.legal_entity_id === ALL) return stores;
  return stores.filter((store) => store.vertical_id === scope.legal_entity_id);
}

function sum(rows, key) {
  return rows.reduce((total, row) => total + (row[key] ?? 0), 0);
}

/**
 * The A2 KPIs at ENGINE_STORE grain.
 *
 * COUNTS ARE DISTINCT SKUs, VALUES ARE ROW SUMS — the rule stated at the top
 * of this file. Every count below went through `.length` when `items` was
 * chain-net and one row meant one SKU; at this grain that same `.length`
 * reports 755 slow-moving rows for 75 slow-moving SKUs.
 *
 * `stockout_risk_skus` is the headline reorder-zone measure (Stockout + Low,
 * 524, `Position < ROP`) — the same predicate Replenishment's
 * `skus_to_reorder` and Demand Forecasting's `stockout_risk_skus` count, so
 * all three boards agree on which SKUs are "at stockout risk" even though
 * this board counts them at ENGINE_STORE grain. `stockout_skus` counts the
 * narrower Stockout state alone (247, `Position < 0.6 x ROP`) and is kept as
 * a distinct, more severe measure — the risk register's own state filter
 * reads it — but it is no longer what the board's headline tile shows,
 * because a reader comparing tabs would see three different numbers for what
 * reads as the same question. `low_skus` (457) completes the split.
 *
 * Two tiles carry a money figure under their count, and both sum
 * `markdown_at_risk_gross` — `f23-markdown-at-risk-gross`, evaluated per item
 * in `dashboard.py`'s `build_items()` / `engine.js`'s `applyLevers()` — rather
 * than re-deriving the arithmetic here. `overstock_excess_value` scopes to
 * Overstock-state rows only, not Slow-mover, matching this tile's existing
 * name even though f23 shares one branch across both states.
 *
 * `expiry_units` scopes to Expiry-state rows, not every perishable row, so it
 * describes the same rows as `expiry_value` beside it. Note the two do not
 * divide into each other exactly: f22 ROUNDs per row and f23 does not. That is
 * the catalogue's inconsistency, not this function's.
 */
export function computeKpis(items) {
  const count = items.length;
  const expiryRows = items.filter((item) => item.state === "Expiry");
  return {
    stockout_skus: distinctSkus(items, (item) => item.state === "Stockout"),
    stockout_value: items.reduce(
      (total, item) =>
        item.state === "Stockout" ? total + item.at_risk_value : total,
      0,
    ),
    low_skus: distinctSkus(items, (item) => item.state === "Low"),
    stockout_risk_skus: distinctSkus(items, (item) => item.is_stockout_risk),
    stockout_risk_value: items.reduce(
      (total, item) =>
        item.is_stockout_risk ? total + item.at_risk_value : total,
      0,
    ),
    overstock_skus: distinctSkus(items, (item) => item.is_overstock),
    overstock_excess_value: items.reduce(
      (total, item) =>
        item.is_overstock ? total + item.markdown_at_risk_gross : total,
      0,
    ),
    expiry_skus: distinctSkus(items, (item) => item.state === "Expiry"),
    expiry_units: sum(expiryRows, "expiry_units"),
    expiry_value: sum(expiryRows, "markdown_at_risk_gross"),
    slow_mover_skus: distinctSkus(items, (item) => item.is_slow_mover),
    avg_dos: count ? sum(items, "dos") / count : 0,
    inventory_value: sum(items, "inv_value"),
    at_risk_value: sum(items, "at_risk_value"),
    healthy_skus: distinctSkus(items, (item) => item.state === HEALTHY_STATE),
    sku_count: distinctSkus(items, () => true),
    row_count: count,
  };
}

/**
 * A real mini-chart for each KPI tile.
 *
 * The tiles carried none, and the comment explaining why was right: the
 * workbook has no date column, so a trend line here would be invented, and an
 * invented trend on a risk board is worse than an empty space.
 *
 * A DISTRIBUTION needs no dates. Each of these is a histogram of the rows
 * behind the number — which answers something the figure alone cannot: 302
 * SKUs below reorder point reads very differently if they are all barely under
 * than if half sit at zero cover. Days of cover is the shared axis for the
 * stock tiles, so the shapes are comparable across the row.
 *
 * `kind` travels with each one so the tile can caption it honestly; nothing
 * here is drawn as a series.
 */
export function computeKpiSparklines(items) {
  return {
    // Keyed to the tile it sits on, which shows the whole reorder zone —
    // Stockout and Low together, `Position < ROP` — so the histogram spans
    // exactly the population the headline number counts.
    stockout_risk_skus: {
      kind: "distribution",
      caption: "Days of cover, at-risk SKUs",
      values: dosHistogram(items.filter((item) => item.is_stockout_risk)),
    },
    overstock_skus: {
      kind: "distribution",
      caption: "Days of cover, overstocked SKUs",
      values: dosHistogram(items.filter((item) => item.is_overstock)),
    },
    // Already bucketed by the board's own expiry timeline — reusing its shape
    // rather than inventing a second one keeps the tile and the panel in step.
    expiry_units: {
      kind: "distribution",
      caption: "Shelf life remaining",
      values: computeExpiryTimeline(items).buckets.map((bucket) => bucket.units),
    },
    slow_mover_skus: {
      kind: "distribution",
      caption: "Growth index, slow movers",
      values: growthHistogram(items.filter((item) => item.is_slow_mover)),
    },
    // The whole chain on the cover axis: the mean the tile prints is one point
    // on this curve, and the spread is what says whether that mean is honest.
    avg_dos: {
      kind: "distribution",
      caption: "Days of cover, all SKUs",
      values: dosHistogram(items),
    },
    inventory_value: {
      kind: "distribution",
      caption: "Value by category, largest first",
      values: topGroups(items, "category_id", (rows) =>
        rows.reduce((total, row) => total + row.inv_value, 0),
      ),
    },
  };
}

/**
 * Suggested Best Action (A2 spec section 1 point 8).
 *
 * Two routes, not a ranked list of one: Stockout and Low are a replenishment
 * problem and go to Agent 3, while Expiry, Overstock and Slow-mover are a
 * markdown/assortment problem and go to Agent 5. The split already exists per
 * row as `next_agent`; this only groups it and sizes each side so the board
 * can say which route is the bigger call today.
 */
export function computeBestActions(items) {
  const routes = new Map();

  for (const item of items) {
    if (item.state === HEALTHY_STATE) continue;

    let route = routes.get(item.next_agent);
    if (!route) {
      route = routes.set(item.next_agent, {
        next_agent: item.next_agent,
        skus: new Set(),
        value: 0,
        states: new Set(),
        // Keyed by SKU, not pushed per row: a SKU in trouble at twenty stores
        // is one call to make, and ranking rows would fill all three slots
        // with a single product's worst branches.
        bySku: new Map(),
      }).get(item.next_agent);
    }
    route.skus.add(item.sku_id);
    route.value += item.at_risk_value;
    route.states.add(item.state);

    const existing = route.bySku.get(item.sku_id);
    if (existing) {
      existing.value += item.at_risk_value;
      existing.store_count += 1;
      // Keep the worst state the SKU reaches anywhere, so the chip beside it
      // is not decided by whichever store happened to be read first.
      if (item.severity_rank < existing.severity_rank) {
        existing.severity_rank = item.severity_rank;
        existing.state = item.state;
      }
    } else {
      route.bySku.set(item.sku_id, {
        sku_id: item.sku_id,
        name: item.name,
        state: item.state,
        severity_rank: item.severity_rank,
        value: item.at_risk_value,
        store_count: 1,
      });
    }
  }

  return [...routes.values()]
    .map((route) => ({
      next_agent: route.next_agent,
      sku_count: route.skus.size,
      value: route.value,
      states: STATE_ORDER.filter((state) => route.states.has(state)),
      top_skus: [...route.bySku.values()]
        .sort((a, b) => a.severity_rank - b.severity_rank || b.value - a.value)
        .slice(0, 3)
        .map(({ sku_id, name, state, value, store_count }) => ({
          sku_id,
          name,
          state,
          value,
          store_count,
        })),
    }))
    .sort((a, b) => b.value - a.value);
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

/*
 * The two state names the store chart segments separately. Taken apart from
 * REPLENISH_STATES rather than retyped, so the reorder zone stays one
 * definition: these are the states, that is the pair, and nothing can drift.
 */
const [STOCKOUT_STATE, LOW_STATE] = REPLENISH_STATES;

/**
 * Roll one store's rows into the shape `fixture.stores` carries.
 *
 * Same counts, same names, derived instead of read — so a caller can hand this
 * the rows currently in scope and get a bar that describes them, rather than
 * the store's whole shelf. The four state segments partition `sku_count` by
 * construction here, which is the invariant `computeStockoutByStore` documents
 * and the fixture builder enforces on the stored rows.
 */
function tallyStore(store, rows) {
  const tally = {
    store_id: store.store_id,
    name: store.name,
    vertical_id: store.vertical_id,
    cluster: store.cluster,
    channel: store.channel,
    size_index: store.size_index,
    health_index: store.health_index,
    sku_count: rows.length,
    stockout_count: 0,
    low_count: 0,
    other_at_risk_count: 0,
    healthy_count: 0,
    stockout_risk_count: 0,
    at_risk_count: 0,
    at_risk_value: 0,
    inv_value: 0,
  };

  for (const row of rows) {
    if (row.state === STOCKOUT_STATE) tally.stockout_count += 1;
    else if (row.state === LOW_STATE) tally.low_count += 1;
    else if (row.state === HEALTHY_STATE) tally.healthy_count += 1;
    else tally.other_at_risk_count += 1;

    if (row.is_stockout_risk) tally.stockout_risk_count += 1;
    if (row.state !== HEALTHY_STATE) tally.at_risk_count += 1;
    tally.at_risk_value += row.at_risk_value;
    tally.inv_value += row.inv_value;
  }

  return tally;
}

/**
 * Per-store rows for the SCOPE, not for the whole shelf.
 *
 * `fixture.stores` is aggregated per store before it reaches this module, so
 * every figure in it covers all 100 SKUs that store carries. That is the right
 * answer while the board is only scoped by vertical or store, and the wrong
 * one the moment a category, a state or a search narrows the rows: the tiles
 * would describe five SKUs while the chart beneath them still described a
 * hundred. Filtering to `GRC-C01` put 3 at-risk SKUs in the tiles and left 46
 * in the S001 bar.
 *
 * So when the scope narrows rows, each store's own position is taken from the
 * rows in scope. At ENGINE_STORE grain that is a plain `store_id` grouping —
 * no derivation, no `atStore`. The rows already ARE the grid the fixture
 * builder used to check the reconstruction against.
 *
 * Tallied at BASELINE_LEVERS on purpose: these charts have always shown the
 * workbook's position rather than a scenario, and a lever that moved the bars
 * but not the aggregate they are compared against would be worse than one that
 * moves neither.
 *
 * @param {object[]} items  Rows already in scope, store grain throughout.
 * @param {object[]} stores Store rows in scope.
 * @param {object|null} storeRow The selected store, or null for the chain.
 * @param {Function} applyLevers Bound engine, for the scenario case.
 */
function deriveStoreRows(items, stores, storeRow, applyLevers, levers = BASELINE_LEVERS) {
  const priced = isBaseline(levers)
    ? items
    : items.map((item) => applyLevers(item, levers));

  if (storeRow !== null) {
    return [tallyStore(storeRow, priced)];
  }

  // Group once rather than filtering per store: this is 16,000 rows against
  // ~160 stores, and the nested filter it replaces was O(rows x stores).
  const byStore = new Map();
  for (const item of priced) {
    const bucket = byStore.get(item.store_id);
    if (bucket) bucket.push(item);
    else byStore.set(item.store_id, [item]);
  }
  return stores.map((store) =>
    tallyStore(store, byStore.get(store.store_id) ?? []),
  );
}

/**
 * Gross per-store risk breakdown, worst first (A2 spec section 6).
 *
 * The four state segments add up to `sku_count` exactly — the fixture builder
 * refuses to emit a store where they do not. That invariant is the point: an
 * earlier version stacked a partial breakdown, so a dozen SKUs per store fell
 * outside every bar and the chart quietly understated the store.
 *
 * `stockout_count + low_count === stockout_risk_count`, verified across all
 * 16,000 source rows, so the reorder zone is the first two segments.
 *
 * See GROSS_VS_NET_NOTE in the contract: these are row counts, so they total
 * higher than a tile that counts each SKU once. The money reconciles exactly.
 */
export function computeStockoutByStore(stores) {
  return [...stores]
    .map((store) => ({
      store_id: store.store_id,
      label: store.name,
      cluster: store.cluster,
      stockout_count: store.stockout_count,
      low_count: store.low_count,
      other_at_risk_count: store.other_at_risk_count,
      healthy_count: store.healthy_count,
      stockout_risk_count: store.stockout_risk_count,
      at_risk_count: store.at_risk_count,
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

  // One entry per SKU, units summed across its stores. Ranking rows would
  // spend all twelve slots on a handful of products repeated store by store,
  // since shelf life is a SKU attribute and ties across every one of its rows.
  const bySku = new Map();
  for (const item of atRisk) {
    const existing = bySku.get(item.sku_id);
    if (existing) {
      existing.units += item.expiry_units;
      existing.store_count += 1;
    } else {
      bySku.set(item.sku_id, {
        sku_id: item.sku_id,
        name: item.name,
        shelf_life_days: item.shelf_life_days,
        units: item.expiry_units,
        store_count: 1,
      });
    }
  }

  const watchlist = [...bySku.values()]
    .sort(
      (a, b) =>
        (a.shelf_life_days ?? 0) - (b.shelf_life_days ?? 0) ||
        b.units - a.units,
    )
    .slice(0, EXPIRY_WATCHLIST_SIZE);

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
/**
 * The demand shape for every vertical in scope, computed once.
 *
 * The factor depends only on the vertical and the day; the level only on the
 * SKU. Splitting them means the projection multiplies rather than recomputes
 * `(1 + trend) ** (day / 365)` eight hundred times a day.
 *
 * Verticals are looked up individually rather than blended: inside the
 * projection every row already knows its own `vertical_id`, so blending the
 * eight curves into one would only smear a distinction the data still has.
 *
 * @returns {(verticalId: string, day: number) => number}
 */
function demandShape(items, days, model) {
  const byVertical = new Map();

  for (const item of items) {
    if (byVertical.has(item.vertical_id)) continue;
    byVertical.set(
      item.vertical_id,
      dailyFactors(
        days,
        model.profile,
        model.curves[item.vertical_id] ?? FLAT_SEASONALITY,
        model.currentMonth,
        model.trendByVertical[item.vertical_id] ?? 0,
      ),
    );
  }

  return (verticalId, day) => byVertical.get(verticalId)?.[day] ?? 1;
}

/**
 * Projected on-hand against demand, A2 spec section 4.
 *
 * The replenishment cycle in two moving parts: stock falls by a day's demand,
 * and steps back up when an order lands `lead_days` after it was placed.
 *
 * DEMAND — measured level, modelled shape
 * The level is `ads`, f01, one measured number per SKU. The shape across the
 * horizon is `common/demandModel.js` — the same day-of-week, seasonal and
 * trend decomposition the Demand Forecasting board draws, so the two boards
 * cost a day of stock identically. Because the seven day-of-week factors sum
 * to the workbook's own `dow_sum`, any whole week of this burn totals exactly
 * `ads * 7.45`, which is f08's `forecast_7d`. The shape reallocates a measured
 * week; it does not invent one.
 *
 * REPLENISHMENT — the workbook's own ROP and Max
 * A textbook (s, S) policy with s = `rop` (f05) and S = `max` (f06), both
 * already per SKU and both already expressed in the same ADS the burn uses.
 * The trigger is the inventory position, `stock + onOrder`, not on-hand alone:
 * triggering on on-hand would re-order on every day of the lead time and
 * stack a pipeline of duplicate POs for one shortfall.
 *
 * The workbook's existing `open_po` is seeded into that pipeline rather than
 * special-cased, so it lands at `lead_days` exactly as it did before.
 *
 * TWO LIMITS WORTH SAYING OUT LOUD ON THE PANEL
 * The day-of-week allocation is modelled, not measured — the workbook stores
 * only its total. And stock is floored at zero per SKU, so a SKU that runs out
 * stays out rather than going negative and quietly subsidising the chain
 * total.
 */
export function computeProjection(
  items,
  days = PROJECTION_DAYS,
  // Called without a model — a test, or a provider that ships none — the
  // resolver's own fallback gives back the flat burn this panel used to draw.
  model = resolveDemandModel(null),
) {
  const shape = demandShape(items, days, model);
  const points = [];

  /*
   * One pass per SKU rather than per day, because the policy is stateful: what
   * a SKU orders on day 12 depends on what it ordered on day 5. The day-major
   * loop this replaced could be closed-form only because nothing was ever
   * reordered.
   */
  const onHandByDay = new Array(days + 1).fill(0);
  const inboundByDay = new Array(days + 1).fill(0);
  const demandByDay = new Array(days + 1).fill(0);

  for (const item of items) {
    let stock = item.on_hand;
    let onOrder = item.open_po;
    // Units landing on each day. An array, not a queue: every arrival date is
    // known the moment its order is placed, and always lies ahead of the loop.
    const arrivals = new Array(days + 1).fill(0);
    // `lead_days` can exceed the horizon; such an order simply never lands.
    if (item.lead_days <= days) arrivals[item.lead_days] += item.open_po;

    // The lead time drives the policy, and a zero would let a SKU order on
    // every single day. One is the shortest honest cycle.
    const leadDays = Math.max(1, item.lead_days);

    for (let day = 0; day <= days; day += 1) {
      /*
       * Receive, record, order, consume — in that order, and the order
       * matters. Recording before consuming keeps day 0 exactly today's
       * position, which the strip beneath the chart also reports; ordering
       * after recording keeps an order out of the same day's stock.
       */
      const landed = arrivals[day];
      if (landed) {
        stock += landed;
        onOrder -= landed;
      }

      onHandByDay[day] += stock;
      inboundByDay[day] += landed;

      const demand = item.ads * shape(item.vertical_id, day);
      demandByDay[day] += demand;

      if (stock + onOrder < item.rop) {
        const order = Math.max(0, item.max - stock - onOrder);
        if (order > 0) {
          onOrder += order;
          const arrivesOn = day + leadDays;
          if (arrivesOn <= days) arrivals[arrivesOn] += order;
        }
      }

      stock = Math.max(0, stock - demand);
    }
  }

  /*
   * `inbound` is cumulative — everything landed up to and including this day,
   * which is what "Inbound landed" means in the tooltip and what makes the
   * series monotonic. Under the reorder policy it now passes the opening
   * `open_po` total rather than stopping at it.
   */
  let landedToDate = 0;
  for (let day = 0; day <= days; day += 1) {
    landedToDate += inboundByDay[day];
    points.push({
      day,
      label: day === 0 ? "Today" : `D+${day}`,
      on_hand: onHandByDay[day],
      inbound: landedToDate,
      demand: demandByDay[day],
    });
  }

  const opening = points[0];
  return {
    days,
    points,
    // The strip under the chart, A2 spec section 4.
    metrics: {
      position: opening.on_hand + sum(items, "open_po"),
      inbound: sum(items, "open_po"),
      avg_dos: items.length ? sum(items, "dos") / items.length : 0,
      at_risk_value: sum(items, "at_risk_value"),
    },
    /*
     * The first day the chain is projected to hold less than one day of cover.
     * Compared against that day's own demand rather than a chain average,
     * because the demand line moves now — a Saturday and a Tuesday are not the
     * same amount of cover.
     */
    days_to_empty:
      points.find((point) => point.on_hand < point.demand)?.day ?? null,
  };
}

/**
 * Baseline against scenario, A2 spec section 8.
 *
 * `applyLevers` re-runs the workbook's own expressions per SKU; everything
 * here just counts and sums the two sets of rows the same way `computeKpis`
 * does, so a difference between the columns can only come from the formulas.
 *
 * The index bars are the panel's own shape (A2 spec 8c): baseline pinned at
 * 100, scenario expressed against it, so four metrics on four different scales
 * can share one axis. A baseline of zero has no index — reported as `null`
 * rather than as a fabricated 100.
 */
export function computeSimulation(
  items,
  levers,
  applyLevers,
  days = PROJECTION_DAYS,
  model = resolveDemandModel(null),
) {
  const merged = { ...BASELINE_LEVERS, ...levers };
  const applied = !isBaseline(merged);
  const baseline = computeKpis(items);

  /*
   * At rest the scenario IS the baseline, and saying so is not just a saving.
   * Re-running the engine here would produce figures that differ in the last
   * float digit — 6251.887728735004 against a stored 6251.887728735005, from
   * summing 800 re-evaluations instead of 800 readings — and the panel would
   * report a delta of -1e-12 on a board that has not been touched.
   */
  const scenarioItems = applied
    ? items.map((item) => applyLevers(item, merged))
    : items;
  const scenario = applied ? computeKpis(scenarioItems) : baseline;

  const compared = [
    { id: "stockout_risk_skus", label: "Stockout-risk SKUs", lowerIsBetter: true },
    { id: "expiry_units", label: "Expiry units", lowerIsBetter: true },
    { id: "overstock_skus", label: "Overstock SKUs", lowerIsBetter: true },
    { id: "at_risk_value", label: "At-risk value", lowerIsBetter: true },
  ];

  return {
    applied,
    levers: merged,
    baseline,
    scenario,
    /*
     * Two curves, because Compare Scenarios (A2 spec 8d) needs a reference
     * line that does not move. `baseline_projection` is always the workbook's
     * own stock curve for this scope; `projection` is the scenario's.
     *
     * The board's top-level `projection` cannot serve as the reference: with
     * "levers drive whole page" on, it is the simulated one, and a comparison
     * whose baseline shifts with the sliders compares nothing.
     *
     * A scenario is only interesting as a shape over time — "does this run me
     * out before the PO lands" — which four KPI totals cannot answer.
     */
    baseline_projection: computeProjection(items, days, model),
    projection: applied
      ? computeProjection(scenarioItems, days, model)
      : null,
    index: compared.map((metric) => ({
      ...metric,
      baseline_value: baseline[metric.id],
      scenario_value: scenario[metric.id],
      baseline_index: 100,
      scenario_index: baseline[metric.id]
        ? (scenario[metric.id] / baseline[metric.id]) * 100
        : null,
      delta: scenario[metric.id] - baseline[metric.id],
    })),
  };
}

/*
 * One engine per fixture, not one per render.
 *
 * `createEngine` parses ten expressions. A slider drag rebuilds the dashboard
 * on every frame, and re-parsing there would turn a smooth control into a
 * stuttering one for no benefit — the expressions cannot change between
 * renders.
 */
let cachedFormulas = null;
let cachedEngine = null;

function engineFor(formulas) {
  if (formulas !== cachedFormulas) {
    cachedEngine = createEngine(formulas);
    cachedFormulas = formulas;
  }
  return cachedEngine;
}

/**
 * Decompose one KPI tile, over exactly the rows the board is showing.
 *
 * Separate from `buildDashboardFromFixture` and computed on demand, because
 * the per-store split runs the engine once per SKU per store — ~16,000 passes
 * at chain scope. That is fine on a click and wasteful on every render, so the
 * board does not carry six of them it may never open.
 *
 * It re-derives the scope rather than accepting the finished payload so that
 * the drawer and the tile above it can never disagree about which rows they
 * are describing: same scope in, same rows out, same engine.
 */
export function buildDrilldownFromFixture(
  fixture,
  scope = {},
  metricId,
  options = {},
) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  const { applyLevers } = engineFor(fixture.formulas);
  const levers = { ...BASELINE_LEVERS, ...options.levers };
  const simulating = !isBaseline(levers) && options.driveWholePage !== false;

  // `scopeItems` honours `store_id` directly now, so there is no separate
  // store branch to take: the rows are already this store's own.
  const scoped = scopeItems(fixture.items, merged);
  const items = simulating
    ? scoped.map((item) => applyLevers(item, levers))
    : scoped;

  return buildDrilldown(metricId, items, scopeStores(fixture.stores, merged), {
    // The store split reads the same filtered set the headline does, so a
    // board scoped to one category shows that category across stores rather
    // than quietly widening back to the whole shelf.
    allItems: items,
  });
}

/**
 * Scope raw rows down to the items a board's baseline is built from, without
 * running the whole dashboard payload around them.
 *
 * Factored out of `buildDashboardFromFixture` so a caller that only wants a
 * simulation — the What-If panel's live preview, recomputed on every slider
 * tick — can get to `computeSimulation` without paying for every chart this
 * function also builds.
 *
 * A named store simply narrows the rows. The stored `state`, `rop` and `dos`
 * on a fixture row already describe that SKU AT THAT STORE, so there is
 * nothing to re-derive — which is what this function used to spend an
 * `atStore` pass and a full engine run doing on every store selection.
 * `computeSimulation` treats these as its baseline, which is correct: the
 * scenario is measured against the store you are looking at.
 *
 * The vertical filter is implicit: a store belongs to one vertical, so rows
 * from other verticals cannot survive the `store_id` clause anyway.
 */
function resolveBaselineItems(fixture, merged) {
  const { applyLevers } = engineFor(fixture.formulas);

  const storeRow =
    merged.store_id === ALL
      ? null
      : fixture.stores.find((row) => row.store_id === merged.store_id);

  return {
    baselineItems: scopeItems(fixture.items, merged),
    storeRow,
    applyLevers,
  };
}

/**
 * The What-If panel's own live preview: baseline against whatever the sliders
 * currently hold, recomputed on every tick with no network call and no
 * rebuild of the rest of the board.
 *
 * `fixture` here is the raw rows already fetched for the current scope (see
 * `loadInventoryRiskRows` in `dashboardData.js`) — not the finished dashboard
 * payload, which already committed to one lever position. Row aggregation is
 * in-memory and runs in low single-digit milliseconds over the whole chain,
 * so calling this straight from a slider's `onChange` is instantaneous.
 *
 * @param {object} fixture Parsed rows, same shape `buildDashboardFromFixture` takes.
 * @param {Partial<import("./contract.js").InventoryRiskScope>} [scope]
 * @param {object} levers
 * @param {{horizonWeeks?: number}} [options]
 */
export function computeLiveSimulation(fixture, scope = {}, levers, options = {}) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  const { baselineItems, applyLevers } = resolveBaselineItems(fixture, merged);
  const demandModel = resolveDemandModel(fixture);
  const horizonWeeks = resolveHorizonWeeks(options.horizonWeeks);
  const projectionDays = horizonDays(horizonWeeks);

  return computeSimulation(
    baselineItems,
    levers,
    applyLevers,
    projectionDays,
    demandModel,
  );
}

export function buildDashboardFromFixture(fixture, scope = {}, options = {}) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  const scopedStores = scopeStores(fixture.stores, merged);
  const legalEntities = fixture.filter_options.legal_entities;

  const { baselineItems, storeRow, applyLevers } = resolveBaselineItems(
    fixture,
    merged,
  );

  const levers = { ...BASELINE_LEVERS, ...options.levers };
  const driveWholePage = options.driveWholePage !== false;

  /*
   * Does the scope narrow rows WITHIN a store's shelf? Vertical and store do
   * not - they choose which stores to show, and `fixture.stores` already
   * covers each of those in full. Category, state and search do, and that is
   * exactly when the stored aggregates stop describing the board.
   *
   * When levers are active and driveWholePage is true, store rows are also
   * derived so store, cluster, and legal entity charts follow the simulation.
   */
  const narrowsRows =
    merged.category_group !== ALL ||
    merged.state !== ALL ||
    merged.sku.trim() !== "";

  const hasLevers = !isBaseline(levers) && driveWholePage;

  const stores =
    narrowsRows || hasLevers
      ? deriveStoreRows(
          baselineItems,
          scopedStores,
          storeRow,
          applyLevers,
          hasLevers ? levers : BASELINE_LEVERS,
        )
      : scopedStores;

  /*
   * How far to project (A2 spec section 7a). It is not part of the scope: it
   * narrows nothing, so `serializeScope` has no business sending it to a
   * backend that returns rows either way. It travels with `levers` instead,
   * because it belongs to the same family — a setting that changes what the
   * board computes from rows it already has.
   *
   * Both curves in `computeSimulation` get the same horizon. A baseline drawn
   * over four weeks against a scenario drawn over sixteen would compare two
   * different questions on one axis.
   */
  const horizonWeeks = resolveHorizonWeeks(options.horizonWeeks);
  const projectionDays = horizonDays(horizonWeeks);

  /*
   * The daily-demand model, resolved once from the fixture and handed to every
   * projection this board draws. Resolved rather than read: a provider built
   * before the shape existed omits these blocks and gets the flat burn back,
   * instead of a crash — see `resolveDemandModel`.
   */
  const demandModel = resolveDemandModel(fixture);

  const simulation = computeSimulation(
    baselineItems,
    levers,
    applyLevers,
    projectionDays,
    demandModel,
  );

  /*
   * "Levers drive whole page" (A2 spec 8b). With it on, every panel below
   * reads the re-simulated rows rather than the workbook's stored ones.
   *
   * Two things it cannot reach, and the UI has to admit as much: the store and
   * cluster charts stay on the baseline — whether they come from
   * `fixture.stores` or from `deriveStoreRows`, both describe the workbook's
   * position rather than a scenario — and the reference totals are the
   * workbook's own and belong to the baseline by definition.
   */
  const items =
    simulation.applied && driveWholePage
      ? baselineItems.map((item) => applyLevers(item, levers))
      : baselineItems;

  /*
   * Categories depend on the selected vertical, so the filter bar can reset a
   * child selection the new parent invalidates without a second load.
   *
   * A selected store implies its vertical even when the entity dropdown says
   * ALL, and the category list follows that rather than the dropdown: S001 is
   * a Grocery store, so offering `DGT-C01` under it offered a combination that
   * can only ever draw an empty board.
   */
  const optionEntity =
    storeRow === null ? merged.legal_entity_id : storeRow.vertical_id;
  const categories =
    optionEntity === ALL
      ? fixture.filter_options.categories
      : fixture.filter_options.categories.filter(
          (category) => category.legal_entity_id === optionEntity,
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
      /*
       * Served rather than assumed. The filter bar renders this array, so a
       * provider that cannot honour sixteen weeks shortens it here and the
       * control follows without a component changing.
       */
      horizons_weeks: [...PROJECTION_HORIZONS_WEEKS],
    },
    kpis: computeKpis(items),
    kpi_sparklines: computeKpiSparklines(items),
    projection: {
      ...computeProjection(items, projectionDays, demandModel),
      horizon_weeks: horizonWeeks,
    },
    simulation,
    at_risk_by_state:
      fixture.at_risk_by_state &&
      fixture.at_risk_by_state.length > 0 &&
      merged.store_id === ALL &&
      merged.category_group === ALL &&
      merged.legal_entity_id === ALL &&
      merged.state === ALL &&
      !merged.sku
        ? fixture.at_risk_by_state
        : computeAtRiskByState(items),
    value_by_category: computeValueByCategory(items),
    at_risk_by_category: computeAtRiskByCategory(items),
    stockout_by_store: computeStockoutByStore(stores),
    at_risk_by_cluster: computeAtRiskByCluster(stores),
    at_risk_by_legal_entity: computeAtRiskByLegalEntity(stores, legalEntities),
    expiry_timeline: computeExpiryTimeline(items),
    best_actions: computeBestActions(items),
    risk_register: computeRiskRegister(items),
    reference_by_vertical: fixture.reference_by_vertical,
  };
}
