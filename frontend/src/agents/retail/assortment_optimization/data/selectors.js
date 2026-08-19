/**
 * Assortment Optimization selectors — the single owner of aggregation.
 *
 * Rows in, dashboard out. Components read only the normalized shape these
 * produce.
 *
 * WHAT IS DECIDED HERE, AND WHY. The delist/grow/hold verdict is resolved
 * upstream (fixture builder at baseline, `engine.js` under a scenario) —
 * these selectors never re-decide it. The best-action TAB is different: its
 * three delist sub-tabs depend on chain-wide vendor counts and per-category
 * delist shares, which are facts about the whole population rather than
 * about a row, so no per-row step can know them. `assignBestActionTabs`
 * below is therefore the one definition, run over the driven population,
 * and `selectors.test.js` asserts it reproduces the fixture's own stored
 * tabs at baseline — so the Python and JS sides cannot drift apart silently.
 */

import {
  ALL,
  BASELINE_LEVERS,
  BEST_ACTION_TABS,
  SIMULATION_METRICS,
} from "./contract.js";
import { createEngine, isBaseline } from "./engine.js";

/*
 * Vendor and category concentration carry no constant. `assignBestActionTabs`
 * compares each group's delist rate with the chain's own, so the cutoff is a
 * fact about the population on screen and re-derives itself under every scope
 * and every lever. The rule it replaced ("a vendor with >= 5 delist SKUs")
 * could not express concentration here: all eight vendors carry 33 to 75, so
 * every one cleared it and all 404 delist rows collapsed into Vendor Review,
 * leaving two of the four tabs empty.
 */

/**
 * The share that makes the contribution chart a Pareto rather than a sorted
 * bar chart. Not a workbook figure and not tunable policy — it is the name of
 * the principle, the way a median is 50%.
 */
export const PARETO_SHARE_PCT = 80;

/**
 * How many bars the Pareto card draws. A rendering limit only: the cumulative
 * curve and the Pareto rank below are computed over every SKU in scope, so
 * changing this moves no number. Matches the mockup's own `rows.slice(0,24)`.
 */
export const PARETO_BARS = 24;

/** Case-insensitive search across the identifiers a reader might type. */
export function matchesSearch(item, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  return [item.sku_id, item.name, item.category_label, item.vertical_id, item.brand, item.vendor]
    .filter(Boolean)
    .some((field) => String(field).toLowerCase().includes(needle));
}

/** Narrow items by vertical, category, classification and free-text search. */
export function scopeItems(items, scope) {
  const vertical = scope?.legal_entity_id;
  const category = scope?.category_group;
  const classification = scope?.classification;
  const term = scope?.sku?.trim();
  return items.filter((item) => {
    if (vertical && vertical !== ALL && item.vertical_id !== vertical) return false;
    if (category && category !== ALL && item.category_id !== category) return false;
    if (classification && classification !== ALL && item.classification !== classification) return false;
    if (!matchesSearch(item, term)) return false;
    return true;
  });
}

/** Narrow the per-store rollup by store and/or vertical. */
export function scopeStores(stores, scope) {
  const storeId = scope?.store_id;
  const vertical = scope?.legal_entity_id;
  return stores.filter((s) => {
    if (storeId && storeId !== ALL && s.store_id !== storeId) return false;
    if (vertical && vertical !== ALL && s.vertical_id !== vertical) return false;
    return true;
  });
}

export const sum = (rows, key) =>
  rows.reduce((total, row) => total + (Number(row?.[key]) || 0), 0);

export const delistOf = (items) => items.filter((i) => i.classification === "delist");
export const growOf = (items) => items.filter((i) => i.classification === "grow");

/**
 * Assign every item's best-action tab. See the module docstring for why this
 * is a population-level step rather than a per-row one. Returns a NEW array;
 * the inputs are not mutated.
 */
export function delistShare(items, key) {
  const totals = new Map();
  const delisted = new Map();
  for (const item of items) {
    const group = item[key];
    totals.set(group, (totals.get(group) ?? 0) + 1);
    if (item.classification === "delist") {
      delisted.set(group, (delisted.get(group) ?? 0) + 1);
    }
  }
  const rates = new Map();
  for (const [group, n] of totals) {
    if (n) rates.set(group, (delisted.get(group) ?? 0) / n);
  }
  return rates;
}

export function assignBestActionTabs(items) {
  if (!items.length) return [];

  const chainRate = delistOf(items).length / items.length;
  const vendorRate = delistShare(items, "vendor");
  const categoryRate = delistShare(items, "category_id");

  return items.map((item) => {
    if (item.classification === "grow") {
      return { ...item, best_action_tab: "grow_winners", recommendation: recommendationFor("grow_winners") };
    }
    if (item.classification !== "delist") {
      return { ...item, best_action_tab: null, recommendation: "Hold assortment" };
    }
    const tab =
      (vendorRate.get(item.vendor) ?? 0) > chainRate
        ? "vendor_brand_review"
        : (categoryRate.get(item.category_id) ?? 0) > chainRate
          ? "rebalance_space"
          : "delist_tail";
    return { ...item, best_action_tab: tab, recommendation: recommendationFor(tab) };
  });
}

function recommendationFor(tabId) {
  return BEST_ACTION_TABS.find((t) => t.id === tabId)?.recommendation ?? "Hold assortment";
}

/** Chain-level headline KPIs — A6 spec section 3. */
export function computeKpis(items) {
  const delist = delistOf(items);
  const grow = growOf(items);
  const tail = items.filter((i) => i.is_tail);
  return {
    delist_candidates: delist.length,
    grow_candidates: grow.length,
    // Inventory-weighted, because an unweighted mean lets a tiny line with a
    // freak ratio outvote the capital that actually sits on the shelf.
    avg_gmroi: round(weightedMean(items, "gmroi", "inv_value"), 2),
    tail_share_pct: items.length ? round((tail.length / items.length) * 100, 2) : 0,
    capital_freed: round(sum(delist, "inv_value")),
    contribution_per_day: round(sum(items, "contribution_per_day")),
    hold_count: items.length - delist.length - grow.length,
    sku_count: items.length,
  };
}

/**
 * Margin contribution Pareto — the mockup's headline A6 card (`#ch-a6`).
 *
 * Every SKU in scope sorted by contribution/day descending, each carrying the
 * running share of total contribution at its rank. Two things come out of it:
 * the curve, over the whole population, and `bars`, its head only — 800 bars
 * is a texture, not a chart.
 *
 * `pareto_rank` is the rank at which the running share first reaches 80%: the
 * count of SKUs carrying the first four fifths of contribution. It is read off
 * the data rather than stored, so it moves with the scope and with any lever
 * that changes contribution.
 *
 * Nothing here is a pasted figure. `contribution_per_day` is `ADS x price x
 * margin %` from the workbook's own columns — the one A6 measure a prior audit
 * did not flag, and the one that reconciles to `A6 Assortment` exactly.
 */
export function computeParetoContribution(items, barCount = PARETO_BARS) {
  const sorted = [...items]
    .filter((i) => (Number(i.contribution_per_day) || 0) > 0)
    .sort((a, b) => b.contribution_per_day - a.contribution_per_day);

  const total = sum(sorted, "contribution_per_day");
  let running = 0;
  let paretoRank = 0;

  const curve = sorted.map((item, index) => {
    running += Number(item.contribution_per_day) || 0;
    const cumulativeShare = total ? (running / total) * 100 : 0;
    if (!paretoRank && cumulativeShare >= PARETO_SHARE_PCT) paretoRank = index + 1;
    return {
      rank: index + 1,
      sku_id: item.sku_id,
      name: item.name,
      category_label: item.category_label,
      classification: item.classification,
      contribution_per_day: item.contribution_per_day,
      gmroi: item.gmroi,
      cumulative_share: round(cumulativeShare, 2),
    };
  });

  return {
    bars: curve.slice(0, barCount),
    sku_count: curve.length,
    total_contribution: round(total),
    pareto_rank: paretoRank,
    pareto_share_pct: PARETO_SHARE_PCT,
  };
}

/** Per-tile sparkline payloads (one bucket per vertical). */
export function computeKpiSparklines(items) {
  return {
    delist_candidates: {
      kind: "distribution",
      values: topGroups(delistOf(items), "vertical_id", (rows) => rows.length).map((g) => g.value),
    },
    grow_candidates: {
      kind: "distribution",
      values: topGroups(growOf(items), "vertical_id", (rows) => rows.length).map((g) => g.value),
    },
    capital_freed: {
      kind: "distribution",
      values: topGroups(delistOf(items), "vertical_id", (rows) => round(sum(rows, "inv_value"))).map((g) => g.value),
    },
    contribution_per_day: {
      kind: "distribution",
      values: topGroups(items, "vertical_id", (rows) => round(sum(rows, "contribution_per_day"))).map((g) => g.value),
    },
  };
}

/** Everything rolled up by vertical — the by-vertical chart + the main chart. */
export function computeByVertical(items, reference) {
  const groups = new Map();
  for (const item of items) {
    if (!groups.has(item.vertical_id)) {
      groups.set(item.vertical_id, { vertical_id: item.vertical_id, items: [] });
    }
    groups.get(item.vertical_id).items.push(item);
  }
  const refById = new Map((reference ?? []).map((r) => [r.legal_entity_id, r]));
  return [...groups.values()]
    .map((g) => {
      const ref = refById.get(g.vertical_id) ?? {};
      const delist = delistOf(g.items);
      const tail = g.items.filter((i) => i.is_tail);
      return {
        vertical_id: g.vertical_id,
        label: ref.vertical_label ?? g.vertical_id,
        delist_candidates: delist.length,
        grow_candidates: growOf(g.items).length,
        avg_gmroi: round(weightedMean(g.items, "gmroi", "inv_value"), 2),
        tail_share_pct: g.items.length ? round((tail.length / g.items.length) * 100, 2) : 0,
        capital_freed: round(sum(delist, "inv_value")),
        contribution_per_day: round(sum(g.items, "contribution_per_day")),
      };
    })
    .sort((a, b) => b.contribution_per_day - a.contribution_per_day);
}

/** Contribution/day by category — the by-category dimension chart. */
export function computeByCategory(items, limit = 8) {
  return topGroups(items, "category_id", (rows) => round(sum(rows, "contribution_per_day")), limit).map((g) => ({
    category_id: g.key,
    label: labelFor(items, g.key, "category_id", "category_label"),
    value: g.value,
  }));
}

/** Gross contribution/day by store, top N (A6 spec section 6). */
export function computeByStore(stores, limit = 12) {
  return [...stores]
    .map((store) => ({
      store_id: store.store_id,
      label: store.name,
      cluster: store.cluster,
      channel: store.channel,
      sku_count: store.sku_count,
      value: store.contribution_per_day,
      inv_value: store.inv_value,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

/** Gross contribution/day by store cluster (A6 spec section 6). */
export function computeByCluster(stores) {
  return groupStores(stores, "cluster");
}

/** Gross contribution/day by channel (A6 spec section 5b / 6). */
export function computeByChannel(stores) {
  return groupStores(stores, "channel");
}

function groupStores(stores, key) {
  const grouped = new Map();
  for (const store of stores) {
    const row = grouped.get(store[key]);
    if (row) {
      row.value += store.contribution_per_day;
      row.store_count += 1;
    } else {
      grouped.set(store[key], {
        [key]: store[key],
        label: store[key],
        value: store.contribution_per_day,
        store_count: 1,
      });
    }
  }
  return [...grouped.values()].sort((a, b) => b.value - a.value);
}

/** Roll store -> legal entity (A6 spec section 6, #ch-dim-le). */
export function computeByLegalEntity(stores, legalEntities) {
  const labelOf = new Map((legalEntities ?? []).map((e) => [e.value, e.label]));
  const grouped = new Map();
  for (const store of stores) {
    const row = grouped.get(store.vertical_id);
    if (row) {
      row.value += store.contribution_per_day;
    } else {
      grouped.set(store.vertical_id, {
        legal_entity_id: store.vertical_id,
        label: labelOf.get(store.vertical_id) ?? store.vertical_id,
        value: store.contribution_per_day,
      });
    }
  }
  return [...grouped.values()].sort((a, b) => b.value - a.value);
}

/**
 * Inventory value by state, across the FULL population (A6 spec section 6,
 * #ch-dim-state). Computed from the driven items so it responds to levers,
 * rather than reading the fixture's pre-baked store-grain block.
 */
export function computeByState(items) {
  const groups = new Map();
  for (const item of items) {
    groups.set(item.state, (groups.get(item.state) ?? 0) + (Number(item.inv_value) || 0));
  }
  return [...groups.entries()].map(([state, value]) => ({ state, value: round(value) }));
}

/**
 * The "Delist vs grow opportunity" quadrant — A6 spec section 4. One point
 * per SKU: GMROI on x, growth on y, inventory value as bubble size, verdict
 * as colour. Capped so the scatter stays readable and the payload small.
 */
export function computeQuadrant(items, limit = 240) {
  return [...items]
    .sort((a, b) => b.inv_value - a.inv_value)
    .slice(0, limit)
    .map((i) => ({
      sku_id: i.sku_id,
      name: i.name,
      vertical_id: i.vertical_id,
      category_label: i.category_label,
      gmroi: round(i.gmroi, 3),
      growth: round(i.growth, 3),
      inv_value: round(i.inv_value),
      contribution_per_day: round(i.contribution_per_day),
      classification: i.classification,
    }));
}

/** The Assortment action preview table — A6 spec section 5c. */
export function computeActionPreview(items, limit = 300) {
  return items
    .filter((i) => i.classification !== "hold")
    .sort((a, b) => {
      // Delist ranks by capital locked, grow by productivity: the two tabs
      // answer different questions and a single sort key would bury one.
      if (a.classification !== b.classification) return a.classification === "delist" ? -1 : 1;
      return a.classification === "delist"
        ? b.inv_value - a.inv_value
        : b.contribution_per_day - a.contribution_per_day;
    })
    .slice(0, limit)
    .map((i) => ({
      sku_id: i.sku_id,
      name: i.name,
      category_label: i.category_label,
      vendor: i.vendor,
      brand: i.brand,
      state: i.state,
      gmroi: round(i.gmroi, 2),
      contribution_per_day: round(i.contribution_per_day),
      inv_value: round(i.inv_value),
      weekly_gmv: round(i.weekly_gmv),
      margin_rp: round(i.margin_rp),
      funding_rp: round(i.funding_rp),
      growth: round(i.growth, 3),
      classification: i.classification,
      recommendation: i.recommendation,
    }));
}

/** Group into the four best-action tabs by the resolved `best_action_tab`. */
export function computeBestActions(items) {
  const tabs = Object.fromEntries(BEST_ACTION_TABS.map((t) => [t.id, []]));
  for (const item of items) {
    if (item.best_action_tab && tabs[item.best_action_tab]) {
      tabs[item.best_action_tab].push(item);
    }
  }
  for (const t of BEST_ACTION_TABS) {
    tabs[t.id].sort((a, b) =>
      t.id === "grow_winners"
        ? (b.contribution_per_day ?? 0) - (a.contribution_per_day ?? 0)
        : (b.inv_value ?? 0) - (a.inv_value ?? 0),
    );
  }
  return tabs;
}

/**
 * The What-If block. Re-runs the engine over every item at the chosen
 * levers, then re-derives the delist/grow populations from the driven
 * verdicts — a scenario can move a SKU out of the tail entirely, not just
 * change its value.
 */
export function computeSimulation(items, levers, applyLevers) {
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

  const baseline = summarize(items.map((i) => applyLevers(i, BASELINE_LEVERS)));
  const scenario = summarize(items.map((i) => applyLevers(i, levers)));

  const index = SIMULATION_METRICS.map((m) => {
    const b = baseline[m.id] ?? 0;
    const s = scenario[m.id] ?? 0;
    const scenarioIndex = b ? round((s / b) * 100) : 0;
    return { ...m, baseline_value: b, scenario_value: s, baseline_index: 100, scenario_index: scenarioIndex, delta: round(s - b, 2) };
  });

  return { applied: true, levers, baseline, scenario, index };
}

function summarize(items) {
  const delist = delistOf(items);
  return {
    delist_candidates: delist.length,
    grow_candidates: growOf(items).length,
    avg_gmroi: round(weightedMean(items, "gmroi", "inv_value"), 2),
    capital_freed: round(sum(delist, "inv_value")),
    contribution_per_day: round(sum(items, "contribution_per_day")),
  };
}

// --------------------------------------------------------------------- helpers

function labelFor(items, key, keyField, labelField) {
  const found = items.find((i) => i[keyField] === key);
  return found?.[labelField] ?? key;
}

function weightedMean(rows, valueKey, weightKey) {
  let totalWeight = 0;
  let totalValue = 0;
  for (const row of rows) {
    const w = Number(row[weightKey]) || 0;
    totalWeight += w;
    totalValue += (Number(row[valueKey]) || 0) * w;
  }
  return totalWeight ? totalValue / totalWeight : 0;
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
function engineFor(formulas, thresholds) {
  if (formulas !== cachedFormulas) {
    cachedEngine = createEngine(formulas, thresholds);
    cachedFormulas = formulas;
  }
  return cachedEngine;
}

// ---------------------------------------------------------- fixture entrypoint

/**
 * The scoped, lever-driven, tab-assigned items a board is built from.
 *
 * Exported because the drill-down drawer needs exactly this population — not
 * the finished dashboard, whose `action_preview` has already dropped every
 * "hold" SKU and would understate a contribution or GMROI breakdown.
 *
 * @param {object} fixture
 * @param {object} [scope]
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export function scopedDrivenItems(fixture, scope = {}, options = {}) {
  const thresholds = fixture.classification_thresholds ?? {};
  const levers = { ...BASELINE_LEVERS, ...(options.levers ?? {}) };
  const engine = engineFor(fixture.formulas ?? {}, thresholds);
  const applyLevers = (item, l) => engine(item, l);

  const allItems = fixture.items ?? [];
  const driveAll =
    options.driveWholePage && !isBaseline(levers) ? allItems.map((i) => applyLevers(i, levers)) : allItems;

  /*
   * Tabs are assigned over the WHOLE driven population before scoping, so a
   * vendor's chain-wide delist count is a chain-wide fact — filtering to one
   * vertical must not silently turn a vendor-level problem into a tail SKU.
   */
  const tabbed = assignBestActionTabs(driveAll);
  return { items: scopeItems(tabbed, scope), applyLevers, levers };
}

/**
 * Build the full dashboard payload from a fixture (or an API response of the
 * same shape, once one exists). Every component reads what this returns.
 */
export function buildDashboardFromFixture(fixture, scope = {}, options = {}) {
  const thresholds = fixture.classification_thresholds ?? {};
  const { items, applyLevers, levers } = scopedDrivenItems(fixture, scope, options);
  const stores = scopeStores(fixture.stores ?? [], scope);
  const reference = fixture.reference_by_vertical ?? [];
  const legalEntities = fixture.filter_options?.legal_entities ?? [];

  return {
    schema_version: fixture.schema_version ?? 1,
    agent: fixture.agent ?? "retail.assortment_optimization",
    as_of: fixture.generated_at ?? fixture.as_of ?? "",
    is_mock: fixture.is_mock ?? true,
    note: fixture.note ?? "",
    source_workbook: fixture.source_workbook ?? "",
    scope: {
      legal_entity_id: scope?.legal_entity_id ?? ALL,
      category_group: scope?.category_group ?? ALL,
      store_id: scope?.store_id ?? ALL,
      classification: scope?.classification ?? ALL,
      sku: scope?.sku ?? "",
    },
    formulas: fixture.formulas ?? {},
    classification_thresholds: thresholds,
    filter_options: fixture.filter_options ?? {
      legal_entities: [],
      categories: [],
      stores: [],
      classifications: [],
    },
    kpi_sparklines: computeKpiSparklines(items),
    kpis: computeKpis(items),
    by_vertical: computeByVertical(items, reference),
    by_category: computeByCategory(items),
    by_store: computeByStore(stores),
    by_cluster: computeByCluster(stores),
    by_channel: computeByChannel(stores),
    by_state: computeByState(items),
    by_legal_entity: computeByLegalEntity(stores, legalEntities),
    pareto: computeParetoContribution(items),
    quadrant: computeQuadrant(items),
    action_preview: computeActionPreview(items),
    best_actions: computeBestActions(items),
    simulation: computeSimulation(items, levers, applyLevers),
    reference_by_vertical: reference,
  };
}
