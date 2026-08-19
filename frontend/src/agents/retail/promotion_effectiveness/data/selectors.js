/**
 * Promotion Effectiveness selectors — the single owner of aggregation.
 *
 * Rows in, dashboard out. Components read only the normalized shape these
 * produce. The same selectors run over the fixture and over the API response,
 * which is what makes the data-source switch a one-file change.
 *
 * WHAT IS NOT HERE: no threshold, no classification decision. The
 * promoClassify rule (high ROI / funding gap / pre-buy required) is resolved
 * upstream and arrives on each campaign's `recommendation`. These selectors
 * count and sum; they never re-decide a campaign's tab.
 */

import {
  ALL,
  BASELINE_LEVERS,
  BEST_ACTION_TABS,
  SIMULATION_METRICS,
} from "./contract.js";
import { atStore, createEngine, isBaseline } from "./engine.js";

/**
 * No per-store fact join needed to scope this board to one store. `f01` is
 * purely multiplicative in `store_size` and `f13` is linear in `ads`, so a
 * store's position is reconstructible from four numbers already on every
 * item/store row (see `computeByStore` and `engine.js`'s `atStore`) — unlike
 * `inventory_risk`, which needs the 16,000-row per-store grid for its own
 * (genuinely gross, non-reconstructible) position counts.
 */
export const SUPPORTS_STORE_SCOPE = true;

/** Case-insensitive search across the identifiers a reader might type. */
export function matchesSearch(item, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  return [
    item.sku_id,
    item.name,
    item.category_label,
    item.vertical_id,
    item.brand,
  ]
    .filter(Boolean)
    .some((field) => field.toLowerCase().includes(needle));
}

/**
 * Narrow the promo-eligible items by the two SQL-side filters plus the
 * client-side SKU search. `legal_entity_id` maps to the item's `vertical_id`.
 */
export function scopeItems(items, scope) {
  const vertical = scope?.legal_entity_id;
  const category = scope?.category_group;
  const term = scope?.sku?.trim();
  return items.filter((item) => {
    if (vertical && vertical !== ALL && item.vertical_id !== vertical) return false;
    if (category && category !== ALL && item.category_id !== category) return false;
    if (!matchesSearch(item, term)) return false;
    return true;
  });
}

/** Narrow campaigns by vertical (their target_category is free text, not a dim id). */
export function scopeCampaigns(campaigns, scope) {
  const vertical = scope?.legal_entity_id;
  const term = scope?.sku?.trim();
  return campaigns.filter((c) => {
    if (vertical && vertical !== ALL && c.vertical_id !== vertical) return false;
    if (term) {
      const needle = term.toLowerCase();
      const hay = [c.promo_id, c.promo_name, c.target_category, c.season]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!hay.includes(needle)) return false;
    }
    return true;
  });
}

/**
 * Narrow the store dimension list: one store narrows to itself, else a
 * vertical narrows to its stores, else every store. Mirrors `inventory_risk`'s
 * `scopeStores`.
 */
export function scopeStores(stores, scope) {
  const storeId = scope?.store_id;
  const vertical = scope?.legal_entity_id;
  if (storeId && storeId !== ALL) {
    return stores.filter((store) => store.store_id === storeId);
  }
  if (vertical && vertical !== ALL) {
    return stores.filter((store) => store.vertical_id === vertical);
  }
  return stores;
}

export const sum = (rows, key) =>
  rows.reduce((total, row) => total + (Number(row?.[key]) || 0), 0);

/**
 * Chain-level headline KPIs. `uplift_pct` and `roi_x` are STORED workbook KPIs:
 * they are not derivable from the per-SKU chain rows (the workbook computes
 * them at vertical grain on the A4 Promotion sheet), so they arrive here as 0
 * and are overwritten from `reference_by_vertical` in `buildDashboardFromFixture`.
 *
 * The genuinely-computed fields are: active_promo_skus (count of promo-eligible
 * items), incremental_margin (sum of f13), cannib_pct / funding_pct (means over
 * promo SKUs), and the campaign counts.
 */
export function computeKpis(items, campaigns) {
  const promoSkus = items;
  const incrementalMargin = sum(promoSkus, "incremental_margin");
  const activePromoSkus = promoSkus.length;

  return {
    active_promo_skus: activePromoSkus,
    uplift_pct: 0, // overwritten from reference_by_vertical by the caller
    incremental_margin: round(incrementalMargin),
    roi_x: 0, // overwritten from reference_by_vertical by the caller
    cannib_pct: round(mean(promoSkus.map((i) => i.cannibalisation_pct)), 2),
    funding_pct: round(mean(promoSkus.map((i) => i.supplier_funding_pct ?? 0)), 2),
    campaigns: campaigns.length,
    pre_buy_uplift_units: sum(campaigns, "pre_buy_uplift_units"),
  };
}

/** Per-tile sparkline payloads. `values` is an array of numbers (one per
 *  bucket), the shape KpiSparkline draws. */
export function computeKpiSparklines(items, campaigns) {
  return {
    active_promo_skus: {
      kind: "distribution",
      values: topGroups(items, "vertical_id", (rows) => rows.length).map((g) => g.value),
    },
    incremental_margin: {
      kind: "distribution",
      values: topGroups(items, "vertical_id", (rows) =>
        round(sum(rows, "incremental_margin")),
      ).map((g) => g.value),
    },
    campaigns: {
      kind: "distribution",
      values: topGroups(campaigns, "season", (rows) => rows.length).map((g) => g.value),
    },
    pre_buy_uplift_units: {
      kind: "distribution",
      values: topGroups(campaigns, "vertical_id", (rows) =>
        sum(rows, "pre_buy_uplift_units"),
      ).map((g) => g.value),
    },
  };
}

/** Incremental margin rolled up by vertical — the by-vertical chart + table. */
export function computeByVertical(items, reference) {
  const groups = new Map();
  for (const item of items) {
    const key = item.vertical_id;
    if (!groups.has(key)) {
      groups.set(key, { vertical_id: key, items: [], incremental_margin: 0 });
    }
    const g = groups.get(key);
    g.items.push(item);
    g.incremental_margin += Number(item.incremental_margin) || 0;
  }
  // Merge the workbook's own headline KPIs per vertical where available.
  const refById = new Map(
    (reference ?? []).map((r) => [r.legal_entity_id, r]),
  );
  return [...groups.values()]
    .map((g) => {
      const ref = refById.get(g.vertical_id) ?? {};
      return {
        vertical_id: g.vertical_id,
        label: ref.vertical_label ?? g.vertical_id,
        active_promo_skus: ref.active_promo_skus ?? g.items.length,
        // Uplift and ROI are stored workbook KPIs (vertical grain), read from
        // the reference, not derived from per-SKU chain rows.
        uplift_pct: ref.uplift_pct ?? 0,
        incremental_margin: round(g.incremental_margin),
        roi_x: ref.roi_x ?? 0,
        cannib_pct: ref.cannib_pct ?? round(mean(g.items.map((i) => i.cannibalisation_pct)), 2),
        funding_pct: ref.funding_pct ?? round(mean(g.items.map((i) => i.supplier_funding_pct ?? 0)), 2),
      };
    })
    .sort((a, b) => b.incremental_margin - a.incremental_margin);
}

/** Incremental margin by category — the by-category dimension chart. */
export function computeByCategory(items, limit = 8) {
  return topGroups(items, "category_id", (rows) => round(sum(rows, "incremental_margin")), limit)
    .map((g) => ({
      category_id: g.key,
      label: rows0Label(items, g.key, "category_id", "category_label"),
      value: g.value,
    }));
}

/** Campaign mix by season × discount type — the stacked dimension chart. */
export function computeBySeason(campaigns) {
  const groups = new Map();
  for (const c of campaigns) {
    const key = c.season ?? "Unknown";
    if (!groups.has(key)) groups.set(key, { season: key, byType: new Map() });
    const types = groups.get(key).byType;
    types.set(c.discount_type, (types.get(c.discount_type) ?? 0) + (Number(c.pre_buy_uplift_units) || 0));
  }
  const types = [...new Set(campaigns.map((c) => c.discount_type))];
  return [...groups.values()]
    .sort((a, b) => a.season.localeCompare(b.season))
    .map((g) => ({
      season: g.season,
      segments: types.map((t) => ({
        discount_type: t,
        label: t,
        value: g.byType.get(t) ?? 0,
      })),
      // `sum` reads a named key off each row; these are bare numbers, so
      // they have to be added directly — the keyed call returned 0 for every
      // season.
      total: round([...g.byType.values()].reduce((a, b) => a + b, 0)),
    }));
}

/**
 * Incremental margin by store — the by-store dimension chart.
 *
 * Proportional split, not a re-evaluation: `f01-ads-per-store` is purely
 * multiplicative in `store_size`, and `f13-incremental-promotion-margin` is
 * linear in `ads` with every other input (price, margin, cannib, funding)
 * constant per item regardless of store. So a store's share of an item's
 * incremental margin is exactly `item.incremental_margin * (store.size_index
 * / item.store_size)` — no formula re-evaluation needed. Summing this split
 * across every store in a vertical reproduces that vertical's own chain-net
 * `incremental_margin` exactly (checked in `selectors.test.js`, and checked
 * against the real ENGINE_STORE extract by the fixture builder's
 * `verify_store_split`). `item.store_size` is the vertical's own total store
 * size, already carried on every item.
 */
export function computeByStore(items, stores) {
  const rows = new Map(
    stores.map((store) => [
      store.store_id,
      {
        store_id: store.store_id,
        label: store.name ?? store.store_id,
        vertical_id: store.vertical_id,
        cluster: store.cluster,
        channel: store.channel,
        incremental_margin: 0,
        sku_count: 0,
      },
    ]),
  );
  for (const item of items) {
    const total = Number(item.store_size) || 0;
    if (!total) continue;
    for (const store of stores) {
      if (store.vertical_id !== item.vertical_id) continue;
      const row = rows.get(store.store_id);
      row.incremental_margin +=
        item.incremental_margin * (Number(store.size_index) / total);
      row.sku_count += 1;
    }
  }
  return [...rows.values()]
    .map((row) => ({ ...row, incremental_margin: round(row.incremental_margin) }))
    .filter((row) => row.incremental_margin > 0)
    .sort((a, b) => b.incremental_margin - a.incremental_margin);
}

/** Group `computeByStore`'s own output by cluster — the by-cluster dimension chart. */
export function computeByCluster(storeRows) {
  return groupStoreRows(storeRows, "cluster");
}

/** Group `computeByStore`'s own output by channel — the mainHTML by-channel chart. */
export function computeByChannel(storeRows) {
  return groupStoreRows(storeRows, "channel");
}

function groupStoreRows(storeRows, key) {
  const groups = new Map();
  for (const row of storeRows) {
    const label = row[key] ?? "Unknown";
    const current = groups.get(label) ?? 0;
    groups.set(label, current + row.incremental_margin);
  }
  return [...groups.entries()]
    .map(([label, incremental_margin]) => ({ label, incremental_margin: round(incremental_margin) }))
    .sort((a, b) => b.incremental_margin - a.incremental_margin);
}

/**
 * Inventory value by state — the inventory-state-exposure dimension chart.
 *
 * NOT incremental margin (spec section 11's own warning): state is unrelated
 * to store-size proportionality, so this measure intentionally does not
 * reconcile against the incremental-margin headline.
 */
export function computeByState(items) {
  const groups = new Map();
  for (const item of items) {
    const state = item.state ?? "Unknown";
    groups.set(state, (groups.get(state) ?? 0) + (Number(item.inventory_value) || 0));
  }
  return [...groups.entries()]
    .map(([state, value]) => ({ state, value: round(value) }))
    .filter((row) => row.value > 0)
    .sort((a, b) => b.value - a.value);
}

/** The largest promo SKUs by incremental margin — the margin leaders list. */
export function computeLargestMarginSkus(items, limit = 12) {
  return [...items]
    .filter((i) => i.incremental_margin > 0)
    .sort((a, b) => b.incremental_margin - a.incremental_margin)
    .slice(0, limit)
    .map((i) => ({
      sku_id: i.sku_id,
      name: i.name,
      vertical_id: i.vertical_id,
      category_id: i.category_id,
      category_label: i.category_label,
      brand: i.brand,
      incremental_margin: round(i.incremental_margin),
      cannibalisation_pct: round(i.cannibalisation_pct, 2),
    }));
}

/** Group campaigns into the three best-action tabs by their upstream recommendation. */
export function computeBestActions(campaigns) {
  const tabs = Object.fromEntries(
    BEST_ACTION_TABS.map((t) => [t.id, []]),
  );
  for (const c of campaigns) {
    const tab = BEST_ACTION_TABS.find((t) => t.recommendation === c.recommendation);
    const key = tab ? tab.id : "high_roi";
    tabs[key].push(c);
  }
  for (const t of BEST_ACTION_TABS) {
    tabs[t.id].sort(
      (a, b) => (b.expected_uplift_pct ?? 0) - (a.expected_uplift_pct ?? 0),
    );
  }
  return tabs;
}

/**
 * The What-If block. Re-runs the promo engine over the scoped items at the
 * chosen levers and reports four metrics as paired indices (Baseline = 100).
 *
 * ROI is a stored KPI; under a scenario it is approximated as
 * `scenario_margin / baseline_margin × baseline_roi` so the index moves with
 * margin. That approximation is labelled in the UI, never presented as measured.
 */
export function computeSimulation(items, levers, applyLevers, reference) {
  const applied = !isBaseline(levers);
  if (!applied) {
    return {
      applied: false,
      levers,
      baseline: null,
      scenario: null,
      index: SIMULATION_METRICS.map((m) => ({
        ...m,
        baseline_value: 0,
        scenario_value: 0,
        baseline_index: 100,
        scenario_index: 100,
        delta: 0,
      })),
    };
  }

  const baselineItems = items.map((i) => applyLevers(i, BASELINE_LEVERS));
  const scenarioItems = items.map((i) => applyLevers(i, levers));

  const baselineMargin = sum(baselineItems, "incremental_margin");
  const scenarioMargin = sum(scenarioItems, "incremental_margin");
  // Uplift and ROI are stored vertical KPIs. Under a scenario, the promo lever
  // moves modeled uplift proportionally (spec section 9b: promo lever raises
  // expected uplift on promo-eligible SKUs), and ROI follows the margin ratio.
  const baselineUplift = mean((reference ?? []).map((r) => r.uplift_pct)) || 0;
  const baselineRoi = mean((reference ?? []).map((r) => r.roi_x)) || 0;
  // f01 applies the promo lever as 1 + lever/100 × 1.3 × (1 - cannib); a rough
  // proportional scaling of the stored uplift captures the direction and order
  // of magnitude without claiming a measurement the workbook never made.
  const promoLever = Number(levers.promo) || 0;
  const scenarioUplift = round(baselineUplift * (1 + promoLever / 100), 2);
  const scenarioRoi = baselineMargin
    ? (scenarioMargin / baselineMargin) * baselineRoi
    : 0;

  const baseline = {
    active_promo_skus: baselineItems.length,
    uplift_pct: round(baselineUplift, 2),
    incremental_margin: round(baselineMargin),
    roi_x: round(baselineRoi, 2),
  };
  const scenario = {
    active_promo_skus: scenarioItems.length,
    uplift_pct: scenarioUplift,
    incremental_margin: round(scenarioMargin),
    roi_x: round(scenarioRoi, 2),
  };

  const index = SIMULATION_METRICS.map((m) => {
    const b = baseline[m.id] ?? 0;
    const s = scenario[m.id] ?? 0;
    const baselineIndex = 100;
    const scenarioIndex = b ? round((s / b) * 100) : 0;
    return {
      ...m,
      baseline_value: b,
      scenario_value: s,
      baseline_index: baselineIndex,
      scenario_index: scenarioIndex,
      delta: round(s - b, 2),
    };
  });

  return { applied: true, levers, baseline, scenario, index };
}

// --------------------------------------------------------------------- helpers

function rows0Label(items, key, keyField, labelField) {
  const found = items.find((i) => i[keyField] === key);
  return found?.[labelField] ?? key;
}

function mean(values) {
  const present = values.map((v) => Number(v) || 0);
  return present.length ? present.reduce((a, b) => a + b, 0) / present.length : 0;
}

function round(value, digits = 0) {
  if (!Number.isFinite(value)) return 0;
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function topGroups(rows, key, reduce, limit = 12) {
  const groups = new Map();
  for (const row of rows) {
    const k = row?.[key];
    if (k == null) continue;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(row);
  }
  return [...groups.entries()]
    .map(([k, rs]) => ({ key: k, value: reduce(rs) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

// --------------------------------------------------------------------- caching

let cachedFormulas = null;
let cachedEngine = null;
function engineFor(formulas) {
  if (formulas !== cachedFormulas) {
    cachedEngine = createEngine(formulas);
    cachedFormulas = formulas;
  }
  return cachedEngine;
}

// ---------------------------------------------------------- fixture entrypoint

/**
 * Build the full dashboard payload from a fixture (or an API response of the
 * same shape). The single aggregation entrypoint: every component reads what
 * this returns, via the normalizer.
 */
export function buildDashboardFromFixture(fixture, scope = {}, options = {}) {
  const engine = engineFor(fixture.formulas ?? {});
  const applyLevers = (item, l) => engine(item, l);
  const levers = { ...BASELINE_LEVERS, ...(options.levers ?? {}) };

  const storeId = scope?.store_id;
  const allStores = fixture.stores ?? [];
  const storeRow =
    storeId && storeId !== ALL
      ? allStores.find((store) => store.store_id === storeId) ?? null
      : null;

  let items = scopeItems(fixture.items ?? [], scope);
  // Store scope replaces the item population outright: reconstruct this
  // store's own baseline position first (see engine.js's `atStore`), then let
  // the ordinary lever/driveWholePage logic below run on top of it, so a
  // scenario and the simulator both describe *this* store. Campaigns and the
  // season mix are NOT swapped — promotion_detail carries no store dimension
  // in this schema, so there is nothing to swap them to.
  if (storeRow) {
    items = items
      .filter((item) => item.vertical_id === storeRow.vertical_id)
      .map((item) => applyLevers(atStore(item, storeRow), BASELINE_LEVERS));
  }

  const campaigns = scopeCampaigns(fixture.campaigns ?? [], scope);
  const reference = fixture.reference_by_vertical ?? [];

  // Drive the items through the engine so a scenario reaches the cards and
  // charts, not just the simulator panel.
  const drivenItems =
    options.driveWholePage && !isBaseline(levers)
      ? items.map((i) => applyLevers(i, levers))
      : items;

  // Uplift and ROI are stored workbook KPIs (vertical grain on the A4 sheet),
  // not derivable from per-SKU chain rows. When one vertical is in scope
  // (directly, or via a store that belongs to one), read that vertical's own
  // reference row instead of averaging across the whole chain — otherwise the
  // Vertical/Store filters would narrow four of the six KPI tiles and
  // silently leave Uplift % and ROI showing the unfiltered chain average.
  const activeVertical =
    storeRow?.vertical_id ??
    (scope?.legal_entity_id && scope.legal_entity_id !== ALL ? scope.legal_entity_id : null);
  const referenceInScope = activeVertical
    ? reference.filter((r) => r.legal_entity_id === activeVertical)
    : reference;

  const kpis = computeKpis(drivenItems, campaigns);
  kpis.uplift_pct = round(mean(referenceInScope.map((r) => r.uplift_pct)), 2);
  kpis.roi_x = round(mean(referenceInScope.map((r) => r.roi_x)), 2);

  const byVertical = computeByVertical(drivenItems, reference);
  const stores = scopeStores(allStores, scope);
  const byStore = computeByStore(drivenItems, stores);

  return {
    schema_version: fixture.schema_version ?? 1,
    agent: fixture.agent ?? "retail.promotion_effectiveness",
    as_of: fixture.generated_at ?? fixture.as_of ?? "",
    is_mock: fixture.is_mock ?? true,
    note: fixture.note ?? "",
    source_workbook: fixture.source_workbook ?? "",
    scope: {
      legal_entity_id: scope?.legal_entity_id ?? ALL,
      category_group: scope?.category_group ?? ALL,
      store_id: scope?.store_id ?? ALL,
      sku: scope?.sku ?? "",
    },
    thresholds: fixture.thresholds ?? {
      roi_target: 2,
      uplift_target_pct: 20,
      funding_guardrail_pct: 35,
      cannib_cap_pct: 25,
      pre_buy_material_units: 2000,
    },
    formulas: fixture.formulas ?? {},
    filter_options: fixture.filter_options ?? { legal_entities: [], categories: [], stores: [] },
    kpi_sparklines: computeKpiSparklines(drivenItems, campaigns),
    kpis,
    by_vertical: byVertical,
    by_category: computeByCategory(drivenItems),
    by_season: computeBySeason(campaigns),
    by_store: byStore,
    by_cluster: computeByCluster(byStore),
    by_channel: computeByChannel(byStore),
    by_state: computeByState(drivenItems),
    largest_margin_skus: computeLargestMarginSkus(drivenItems),
    campaigns,
    best_actions: computeBestActions(campaigns),
    simulation: computeSimulation(drivenItems, levers, applyLevers, referenceInScope),
    reference_by_vertical: reference,
  };
}
