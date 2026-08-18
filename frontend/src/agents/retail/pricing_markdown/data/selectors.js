/**
 * Pricing & Markdown selectors — the single owner of aggregation.
 *
 * Rows in, dashboard out. Components read only the normalized shape these
 * produce. WHAT IS NOT HERE: no state-classification threshold, no
 * best-action rule. Both are resolved upstream in
 * scripts/build_pricing_markdown_fixture.py and arrive as `state` and
 * `best_action_tab` on each item; these selectors only count and sum.
 */

import {
  ALL,
  BASELINE_LEVERS,
  BEST_ACTION_TABS,
  SIMULATION_METRICS,
} from "./contract.js";
import { createEngine, isBaseline } from "./engine.js";

/** Case-insensitive search across the identifiers a reader might type. */
export function matchesSearch(item, term) {
  if (!term) return true;
  const needle = term.toLowerCase();
  return [item.sku_id, item.name, item.category_label, item.vertical_id, item.brand, item.vendor]
    .filter(Boolean)
    .some((field) => String(field).toLowerCase().includes(needle));
}

/** Narrow chain-net items by vertical, category, state and free-text search. */
export function scopeItems(items, scope) {
  const vertical = scope?.legal_entity_id;
  const category = scope?.category_group;
  const state = scope?.state;
  const term = scope?.sku?.trim();
  return items.filter((item) => {
    if (vertical && vertical !== ALL && item.vertical_id !== vertical) return false;
    if (category && category !== ALL && item.category_id !== category) return false;
    if (state && state !== ALL && item.state !== state) return false;
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

/** Markdown candidates: at least one store in {Expiry, Overstock, Slow-mover}. */
export function candidatesOf(items) {
  return items.filter((item) => item.is_markdown_candidate);
}

/** Chain-level headline KPIs, from candidates only (spec section 11). */
export function computeKpis(items) {
  const candidates = candidatesOf(items);
  const atRisk = sum(candidates, "at_risk_value");
  const recoverable = sum(candidates, "recoverable_value");
  return {
    markdown_candidates: candidates.length,
    avg_depth_pct: 0, // overwritten from reference_by_vertical by the caller — vertical-level, no per-SKU source
    at_risk_value: round(atRisk),
    recoverable_value: round(recoverable),
    write_off_value: round(Math.max(0, atRisk - recoverable)),
    comp_idx: round(mean(candidates.map((i) => i.comp_idx)), 1),
    recovery_rate_pct: atRisk ? round((recoverable / atRisk) * 100, 2) : 0,
  };
}

/** Per-tile sparkline payloads (one bucket per vertical, candidates only). */
export function computeKpiSparklines(items) {
  const candidates = candidatesOf(items);
  return {
    markdown_candidates: {
      kind: "distribution",
      values: topGroups(candidates, "vertical_id", (rows) => rows.length).map((g) => g.value),
    },
    at_risk_value: {
      kind: "distribution",
      values: topGroups(candidates, "vertical_id", (rows) => round(sum(rows, "at_risk_value"))).map((g) => g.value),
    },
    recoverable_value: {
      kind: "distribution",
      values: topGroups(candidates, "vertical_id", (rows) => round(sum(rows, "recoverable_value"))).map((g) => g.value),
    },
    write_off_value: {
      kind: "distribution",
      values: topGroups(candidates, "vertical_id", (rows) =>
        round(sum(rows, "at_risk_value") - sum(rows, "recoverable_value")),
      ).map((g) => g.value),
    },
  };
}

/** At-risk/recoverable/write-off rolled up by vertical — the by-vertical chart + table. */
export function computeByVertical(items, reference) {
  const candidates = candidatesOf(items);
  const groups = new Map();
  for (const item of candidates) {
    const key = item.vertical_id;
    if (!groups.has(key)) {
      groups.set(key, { vertical_id: key, items: [], at_risk_value: 0, recoverable_value: 0 });
    }
    const g = groups.get(key);
    g.items.push(item);
    g.at_risk_value += Number(item.at_risk_value) || 0;
    g.recoverable_value += Number(item.recoverable_value) || 0;
  }
  const refById = new Map((reference ?? []).map((r) => [r.legal_entity_id, r]));
  return [...groups.values()]
    .map((g) => {
      const ref = refById.get(g.vertical_id) ?? {};
      return {
        vertical_id: g.vertical_id,
        label: ref.vertical_label ?? g.vertical_id,
        markdown_candidates: g.items.length,
        // Stored vertical-level figure — no per-SKU depth exists (spec section 11).
        avg_depth_pct: ref.avg_depth_pct ?? 0,
        at_risk_value: round(g.at_risk_value),
        recoverable_value: round(g.recoverable_value),
        write_off_value: round(Math.max(0, g.at_risk_value - g.recoverable_value)),
        comp_idx: round(mean(g.items.map((i) => i.comp_idx)), 1),
      };
    })
    .sort((a, b) => b.at_risk_value - a.at_risk_value);
}

/** At-risk value by category — the by-category dimension chart. */
export function computeByCategory(items, limit = 8) {
  const candidates = candidatesOf(items);
  return topGroups(candidates, "category_id", (rows) => round(sum(rows, "at_risk_value")), limit).map((g) => ({
    category_id: g.key,
    label: labelFor(candidates, g.key, "category_id", "category_label"),
    value: g.value,
  }));
}

/** Gross at-risk value by store, top N (A5 spec section 6). */
export function computeByStore(stores, limit = 12) {
  return [...stores]
    .map((store) => ({
      store_id: store.store_id,
      label: store.name,
      cluster: store.cluster,
      channel: store.channel,
      expiry_count: store.expiry_count,
      overstock_count: store.overstock_count,
      slow_mover_count: store.slow_mover_count,
      other_count: store.other_count,
      sku_count: store.sku_count,
      at_risk_value: store.at_risk_value,
    }))
    .sort((a, b) => b.at_risk_value - a.at_risk_value)
    .slice(0, limit);
}

/** Gross at-risk value by store cluster (A5 spec section 6). */
export function computeByCluster(stores) {
  return groupStores(stores, "cluster");
}

/** Gross at-risk value by channel (A5 spec section 6 — not carried by inventory_risk). */
export function computeByChannel(stores) {
  return groupStores(stores, "channel");
}

function groupStores(stores, key) {
  const grouped = new Map();
  for (const store of stores) {
    const row = grouped.get(store[key]);
    if (row) {
      row.value += store.at_risk_value;
      row.store_count += 1;
    } else {
      grouped.set(store[key], { [key]: store[key], label: store[key], value: store.at_risk_value, store_count: 1 });
    }
  }
  return [...grouped.values()].sort((a, b) => b.value - a.value);
}

/** Roll store -> legal entity (A5 spec section 6, #ch-dim-le). */
export function computeByLegalEntity(stores, legalEntities) {
  const labelOf = new Map((legalEntities ?? []).map((e) => [e.value, e.label]));
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
 * Inventory VALUE by state, across the FULL population (A5 spec section 6,
 * #ch-dim-state — "broad inventory exposure ... not only markdown
 * candidates"). Deliberately not filtered to candidates.
 */
export function computeByState(items) {
  const groups = new Map();
  for (const item of items) {
    groups.set(item.state, (groups.get(item.state) ?? 0) + (Number(item.inv_value) || 0));
  }
  return [...groups.entries()].map(([state, value]) => ({ state, value: round(value) }));
}

/** The Markdown candidate preview table — A5 spec section 5c. */
export function computeCandidates(items, limit = 300) {
  return candidatesOf(items)
    .sort((a, b) => b.at_risk_value - a.at_risk_value)
    .slice(0, limit)
    .map((i) => ({
      sku_id: i.sku_id,
      name: i.name,
      category_label: i.category_label,
      state: i.state,
      position: i.position,
      dos: round(i.dos, 1),
      price: i.price,
      at_risk_value: round(i.at_risk_value),
      recoverable_value: round(i.recoverable_value),
      write_off_value: round(Math.max(0, i.at_risk_value - i.recoverable_value)),
      vendor: i.vendor,
      brand: i.brand,
      recommendation: i.recommendation,
    }));
}

/** Group candidates into the four best-action tabs by their upstream `best_action_tab`. */
export function computeBestActions(items) {
  const tabs = Object.fromEntries(BEST_ACTION_TABS.map((t) => [t.id, []]));
  for (const item of candidatesOf(items)) {
    if (item.best_action_tab && tabs[item.best_action_tab]) {
      tabs[item.best_action_tab].push(item);
    }
  }
  for (const t of BEST_ACTION_TABS) {
    tabs[t.id].sort((a, b) => (b.at_risk_value ?? 0) - (a.at_risk_value ?? 0));
  }
  return tabs;
}

/**
 * The What-If block. Re-runs the state cascade over every item at the chosen
 * levers, then re-derives the candidate population from the DRIVEN state —
 * a scenario can move a SKU out of (or into) a markdown state, not just
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

  const baseline = summarize(candidatesOf(items.map((i) => applyLevers(i, BASELINE_LEVERS))));
  const scenario = summarize(candidatesOf(items.map((i) => applyLevers(i, levers))));

  const index = SIMULATION_METRICS.map((m) => {
    const b = baseline[m.id] ?? 0;
    const s = scenario[m.id] ?? 0;
    const scenarioIndex = b ? round((s / b) * 100) : 0;
    return { ...m, baseline_value: b, scenario_value: s, baseline_index: 100, scenario_index: scenarioIndex, delta: round(s - b) };
  });

  return { applied: true, levers, baseline, scenario, index };
}

function summarize(items) {
  const atRisk = sum(items, "at_risk_value");
  const recoverable = sum(items, "recoverable_value");
  return {
    markdown_candidates: items.length,
    at_risk_value: round(atRisk),
    recoverable_value: round(recoverable),
    write_off_value: round(Math.max(0, atRisk - recoverable)),
  };
}

// --------------------------------------------------------------------- helpers

function labelFor(items, key, keyField, labelField) {
  const found = items.find((i) => i[keyField] === key);
  return found?.[labelField] ?? key;
}

function mean(values) {
  const present = values.map((v) => Number(v) || 0);
  return present.length ? present.reduce((a, b) => a + b, 0) / present.length : 0;
}

/**
 * Weighted mean of `reference[].avg_depth_pct`, weighted by each vertical's
 * LIVE at-risk value from `byVertical` (joined on legal_entity_id) — not by
 * anything read from the reference sheet itself, which carries no reliable
 * money figure post-audit (see contract.js's module docstring).
 */
function weightedAvgDepth(reference, byVertical) {
  const atRiskByVertical = new Map(byVertical.map((v) => [v.vertical_id, v.at_risk_value]));
  let totalWeight = 0;
  let totalValue = 0;
  for (const row of reference ?? []) {
    const weight = atRiskByVertical.get(row.legal_entity_id) ?? 0;
    totalWeight += weight;
    totalValue += (Number(row.avg_depth_pct) || 0) * weight;
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
 * same shape, once one exists). Every component reads what this returns.
 */
export function buildDashboardFromFixture(fixture, scope = {}, options = {}) {
  const items = scopeItems(fixture.items ?? [], scope);
  const stores = scopeStores(fixture.stores ?? [], scope);
  const reference = fixture.reference_by_vertical ?? [];
  const legalEntities = fixture.filter_options?.legal_entities ?? [];

  const levers = { ...BASELINE_LEVERS, ...(options.levers ?? {}) };
  const engine = engineFor(fixture.formulas ?? {});
  const applyLevers = (item, l) => engine(item, l);

  const drivenItems =
    options.driveWholePage && !isBaseline(levers) ? items.map((i) => applyLevers(i, levers)) : items;

  const byVertical = computeByVertical(drivenItems, reference);
  const kpis = computeKpis(drivenItems);
  kpis.avg_depth_pct = round(weightedAvgDepth(reference, byVertical), 2);

  return {
    schema_version: fixture.schema_version ?? 1,
    agent: fixture.agent ?? "retail.pricing_markdown",
    as_of: fixture.generated_at ?? fixture.as_of ?? "",
    is_mock: fixture.is_mock ?? true,
    note: fixture.note ?? "",
    source_workbook: fixture.source_workbook ?? "",
    scope: {
      legal_entity_id: scope?.legal_entity_id ?? ALL,
      category_group: scope?.category_group ?? ALL,
      store_id: scope?.store_id ?? ALL,
      state: scope?.state ?? ALL,
      sku: scope?.sku ?? "",
    },
    formulas: fixture.formulas ?? {},
    filter_options: fixture.filter_options ?? { legal_entities: [], categories: [], stores: [], states: [] },
    kpi_sparklines: computeKpiSparklines(drivenItems),
    kpis,
    by_vertical: byVertical,
    by_category: computeByCategory(drivenItems),
    by_store: computeByStore(stores),
    by_cluster: computeByCluster(stores),
    by_channel: computeByChannel(stores),
    by_state: computeByState(drivenItems),
    by_legal_entity: computeByLegalEntity(stores, legalEntities),
    candidates: computeCandidates(drivenItems),
    best_actions: computeBestActions(drivenItems),
    simulation: computeSimulation(items, levers, applyLevers),
    reference_by_vertical: reference,
  };
}
