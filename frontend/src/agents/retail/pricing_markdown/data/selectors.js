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
  DEPTH_BY_STATE,
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

/**
 * Chain-level headline KPIs (spec section 11). Every figure here is
 * candidate-scoped EXCEPT comp_idx: that's a per-SKU competitiveness index,
 * not an at-risk metric, so it's averaged over every distinct SKU in scope
 * (matching SKU_Master's own AVERAGEIFS) rather than just markdown
 * candidates — see `distinctBySku`.
 */
export function computeKpis(items, markdownLever = BASELINE_LEVERS.markdown) {
  const candidates = candidatesOf(items);
  const atRisk = sum(candidates, "at_risk_value");
  const recoverable = sum(candidates, "recoverable_value");
  return {
    markdown_candidates: candidates.length,
    // Weighted over THESE candidates, so it moves with every filter (scope
    // AND lever-driven re-states) rather than a vertical-level constant.
    avg_depth_pct: round(depthWeightedAvgPct(candidates, markdownLever), 2),
    at_risk_value: round(atRisk),
    recoverable_value: round(recoverable),
    write_off_value: round(Math.max(0, atRisk - recoverable)),
    comp_idx: round(mean(distinctBySku(items).map((i) => i.comp_idx)), 1),
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
export function computeByVertical(items, reference, markdownLever = BASELINE_LEVERS.markdown) {
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
  // Comp idx per vertical, over every distinct SKU in that vertical — not
  // just this vertical's candidates (see computeKpis).
  const compIdxByVertical = new Map(
    topGroups(
      distinctBySku(items),
      "vertical_id",
      (rows) => round(mean(rows.map((r) => r.comp_idx)), 1),
      Infinity,
    ).map((g) => [g.key, g.value]),
  );
  const refById = new Map((reference ?? []).map((r) => [r.legal_entity_id, r]));
  return [...groups.values()]
    .map((g) => {
      const ref = refById.get(g.vertical_id) ?? {};
      return {
        vertical_id: g.vertical_id,
        label: ref.vertical_label ?? g.vertical_id,
        markdown_candidates: g.items.length,
        // Weighted over this vertical's OWN scoped candidates (see
        // `depthWeightedAvgPct`), not read off `ref` — `reference` only
        // carries the always-unscoped vertical figure, which stayed flat
        // under every filter until a search/category/state filter could
        // change what a vertical's row actually stands for.
        avg_depth_pct: round(depthWeightedAvgPct(g.items, markdownLever), 2),
        at_risk_value: round(g.at_risk_value),
        recoverable_value: round(g.recoverable_value),
        write_off_value: round(Math.max(0, g.at_risk_value - g.recoverable_value)),
        comp_idx: compIdxByVertical.get(g.vertical_id) ?? 0,
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
export function computeCandidates(items, limit = 300, markdownLever = BASELINE_LEVERS.markdown) {
  return candidatesOf(items)
    .sort((a, b) => b.at_risk_value - a.at_risk_value)
    .slice(0, limit)
    .map((i) => ({
      sku_id: i.sku_id,
      store_id: i.store_id,
      name: i.name,
      category_id: i.category_id,
      category_label: i.category_label,
      vertical_id: i.vertical_id,
      comp_idx: i.comp_idx,
      state: i.state,
      position: i.position,
      dos: round(i.dos, 1),
      price: i.price,
      at_risk_value: round(i.at_risk_value),
      // avg_depth_pct's drilldown weight (see depthWeightedAvgPct) — a
      // different figure from at_risk_value, not a display column.
      at_risk_gross: round(i.at_risk_gross),
      recoverable_value: round(i.recoverable_value),
      write_off_value: round(Math.max(0, i.at_risk_value - i.recoverable_value)),
      // Elasticity vs depth chart: SKU_Master-sourced, raw signed value
      // (negative = normal demand response to a price cut).
      elasticity: Number(i.elasticity) || 0,
      // This candidate's own markdown depth at the current lever (itemDepth,
      // the same per-item term depthWeightedAvgPct weights and averages) —
      // not previously exposed per-row, only as a scope-wide weighted mean.
      depth_pct: round((itemDepth(i, markdownLever) ?? 0) * 100, 1),
      vendor: i.vendor,
      brand: i.brand,
      recommendation: i.recommendation,
    }));
}

/**
 * The 33-point (16 back, today, 16 forward) "at-risk value: ladder vs no
 * action" projection for the current scope. `week -16..-1`/`week 1..16`
 * come from `fixture.ladder_by_vertical` (built by `scripts/build_pricing_
 * markdown_fixture.py` / `dashboard.py`'s `_ladder_by_vertical()` from
 * `synthetic.markdown_ladder_store_sku_16w` -- a fabricated, gate-checked
 * projection; NEITHER side is a measured history, see that table's
 * migrations for why at-risk value has no real past to record). `week: 0`
 * ("today") is NOT read from that table at all -- it is injected here from
 * `kpis` (`dashboard.kpis.at_risk_value`/`write_off_value`, the same real,
 * already-computed figures the KPI tiles and the Rescue waterfall show),
 * because today is never modelled and duplicating a live figure into a
 * synthetic table would be a second copy of a number that already exists
 * and already reacts to the full scope (not just legal_entity_id).
 *
 * `ladderByVertical` ships pre-aggregated to (legal_entity_id -> 16 weekly
 * numbers per line, x4 lines: no_action/ladder forward, history_no_action/
 * history_ladder back) -- the grain `reference_by_vertical` already uses for
 * this same board. The -16..-1/1..16 weeks react to the `legal_entity_id`
 * scope filter only (sums every vertical when unscoped, "ALL"), not to
 * category_group/store_id/state -- a documented limitation, same kind
 * `reference_by_vertical` already has. `week: 0`, by contrast, reacts to the
 * FULL scope, since `kpis` already does.
 *
 * Returns one array, oldest week first: `week -16..-1` (history, all zero if
 * the fixture predates migration 013), `week: 0` (today, real), then
 * `week 1..16` (forecast).
 */
export function computeLadderHistory(ladderByVertical, scope = {}, kpis = {}) {
  if (!ladderByVertical?.length) return [];
  const rows =
    scope?.legal_entity_id && scope.legal_entity_id !== ALL
      ? ladderByVertical.filter((r) => r.legal_entity_id === scope.legal_entity_id)
      : ladderByVertical;
  if (!rows.length) return [];

  const weeks = rows[0]?.no_action?.length ?? 0;
  const sumAt = (field, i) => round(rows.reduce((sum, r) => sum + (Number(r[field]?.[i]) || 0), 0));

  // History: history_no_action[0] is "1 week ago" (hist_w1) .. [weeks-1] is
  // "`weeks` weeks ago" (hist_w{weeks}) -- reversed here so the array reads
  // oldest-first, matching a chart's left-to-right axis.
  const history = Array.from({ length: weeks }, (_, i) => {
    const n = weeks - i; // n counts down: weeks, weeks-1, ..., 1
    const idx = n - 1;
    return {
      week: -n,
      no_action: sumAt("history_no_action", idx),
      ladder: sumAt("history_ladder", idx),
    };
  });
  const today = {
    week: 0,
    no_action: round(Number(kpis?.at_risk_value) || 0),
    ladder: round(Number(kpis?.write_off_value) || 0),
  };
  // Forward: no_action[0]/ladder[0] (w1) is +1 week out, not today -- see
  // this function's own docstring and the generator's "TODAY LIVES OUTSIDE
  // THIS TABLE" section for why w1..w16 means +1..+16.
  const forward = Array.from({ length: weeks }, (_, i) => ({
    week: i + 1,
    no_action: sumAt("no_action", i),
    ladder: sumAt("ladder", i),
  }));
  return [...history, today, ...forward];
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

  const baseline = summarize(
    candidatesOf(items.map((i) => applyLevers(i, BASELINE_LEVERS))),
    BASELINE_LEVERS.markdown,
  );
  const scenario = summarize(candidatesOf(items.map((i) => applyLevers(i, levers))), levers.markdown);

  const index = SIMULATION_METRICS.map((m) => {
    const b = baseline[m.id] ?? 0;
    const s = scenario[m.id] ?? 0;
    const scenarioIndex = b ? round((s / b) * 100) : 0;
    return { ...m, baseline_value: b, scenario_value: s, baseline_index: 100, scenario_index: scenarioIndex, delta: round(s - b) };
  });

  return { applied: true, levers, baseline, scenario, index };
}

function summarize(items, markdownLever = BASELINE_LEVERS.markdown) {
  const atRisk = sum(items, "at_risk_value");
  const recoverable = sum(items, "recoverable_value");
  return {
    markdown_candidates: items.length,
    at_risk_value: round(atRisk),
    recoverable_value: round(recoverable),
    write_off_value: round(Math.max(0, atRisk - recoverable)),
    recovery_rate_pct: atRisk ? round((recoverable / atRisk) * 100, 2) : 0,
    avg_depth_pct: round(depthWeightedAvgPct(items, markdownLever), 2),
  };
}

// --------------------------------------------------------------------- helpers

function labelFor(items, key, keyField, labelField) {
  const found = items.find((i) => i[keyField] === key);
  return found?.[labelField] ?? key;
}

/**
 * One row per distinct SKU. `comp_idx` (like every SKU_Master field) is
 * constant across a SKU's ~20 ENGINE_STORE rows, so this is the population
 * SKU_Master's own AVERAGEIFS operates over — `candidatesOf(items)` is a
 * biased ~20% subset (only Expiry/Overstock/Slow-mover rows) and must not
 * be used for a per-SKU figure like comp_idx.
 */
export function distinctBySku(items) {
  const seen = new Map();
  for (const item of items) {
    if (!seen.has(item.sku_id)) seen.set(item.sku_id, item);
  }
  return [...seen.values()];
}

export function mean(values) {
  const present = values.map((v) => Number(v) || 0);
  return present.length ? present.reduce((a, b) => a + b, 0) / present.length : 0;
}

/**
 * Per-item markdown depth, f14's own expression: each state's base depth
 * (`DEPTH_BY_STATE`) scaled by the `markdown` lever and capped at 65%.
 * `markdownLever` is UI-facing and reads exactly like the workbook's "A5
 * Markdown live" B6 cell (25 = rest, matching `BASELINE_LEVERS.markdown`),
 * so `markdownLever / 25` is 1 at rest. `engine.js`'s
 * `f14-recoverable-at-risk-value` binding converts this same UI value back
 * to a delta-from-25 at its own formula boundary, so both stay consistent
 * with each other under a scenario.
 */
export function itemDepth(item, markdownLever) {
  const base = DEPTH_BY_STATE[item.state];
  if (base == null) return null;
  return Math.min(0.65, base * (markdownLever / 25));
}

/**
 * At-risk-GROSS-weighted mean markdown depth over the given candidates —
 * `Σ(depth × at-risk gross) ÷ Σ at-risk gross`, the same computation
 * `reference_by_vertical` was built from (see contract.js and
 * `scripts/build_pricing_markdown_fixture.py`), but run here on whatever
 * items are actually in scope and at whatever the markdown lever is
 * currently set to. Depth is a function of `state` (and the lever), so it
 * is as available per SKU as `at_risk_gross` is — nothing about it required
 * falling back to a vertical-level, always-unscoped figure.
 *
 * The weight is `at_risk_gross` (f23-markdown-at-risk-gross's own output),
 * NOT `at_risk_value` (f12: the row's full position x price for any
 * non-Healthy state, ENGINE_STORE's own "At-risk" column). `at_risk_value`
 * overstates the true at-risk portion 3x-20x per row (it's the whole
 * position's value, not the excess-over-Max/expiry-units slice a markdown
 * actually targets) — using it here was the entire cause of this board's
 * markdown depth reading 34% against a from-scratch, hand-checked 35%.
 */
export function depthWeightedAvgPct(items, markdownLever = BASELINE_LEVERS.markdown) {
  let totalWeight = 0;
  let totalValue = 0;
  for (const item of items) {
    const depth = itemDepth(item, markdownLever);
    const weight = Number(item.at_risk_gross) || 0;
    if (depth == null || weight <= 0) continue;
    totalWeight += weight;
    totalValue += depth * weight;
  }
  return totalWeight ? (totalValue / totalWeight) * 100 : 0;
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

  const pageIsDriven = options.driveWholePage && !isBaseline(levers);
  const drivenItems = pageIsDriven ? items.map((i) => applyLevers(i, levers)) : items;
  // Depth must agree with whichever levers actually produced `drivenItems`
  // above -- baseline (BASELINE_LEVERS.markdown, 25 -- matching the
  // workbook's own B6 default) when the page isn't driven, `levers.markdown`
  // when it is, never a mix of the two.
  const markdownLever = pageIsDriven ? levers.markdown : BASELINE_LEVERS.markdown;

  const byVertical = computeByVertical(drivenItems, reference, markdownLever);
  const kpis = computeKpis(drivenItems, markdownLever);

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
    candidates: computeCandidates(drivenItems, 300, markdownLever),
    best_actions: computeBestActions(drivenItems),
    // `candidates_full`: every markdown candidate, not the preview table's
    // top-300-by-at_risk_value slice above -- the drilldown drawer groups by
    // category/store/SKU and must see the whole population or it silently
    // drops most groups and skews every weighted figure (avg_depth_pct
    // especially, since the top-300 slice is disproportionately Slow-mover).
    // See dashboardData.js's loadPricingMarkdownDrilldown.
    candidates_full: computeCandidates(drivenItems, Infinity, markdownLever),
    simulation: computeSimulation(items, levers, applyLevers),
    reference_by_vertical: reference,
    // 33-point (16 back, today, 16 forward) projection, see
    // computeLadderHistory's own docstring. The -16..-1/1..16 weeks are
    // scoped by legal_entity_id only (the grain `ladder_by_vertical` ships
    // at); `week: 0` (today) reacts to the FULL scope, since it comes
    // straight from `kpis` above.
    ladder_history: computeLadderHistory(fixture.ladder_by_vertical ?? [], scope, kpis),
    // Not part of the normalized dashboard schema (see contract.js) — these
    // are read directly off the raw object by loadPricingMarkdownDrilldown.
    // `markdown_lever`: so a drilldown drawer can be built with the same
    // lever that produced the KPI tile it was opened from.
    markdown_lever: markdownLever,
    // `sku_index`: one row per distinct SKU in scope, for comp_idx's
    // drilldown — that metric averages over every SKU, not just markdown
    // candidates (see computeKpis), so it can't reuse `candidates` below.
    sku_index: distinctBySku(drivenItems).map((i) => ({
      sku_id: i.sku_id,
      name: i.name,
      category_id: i.category_id,
      category_label: i.category_label,
      vertical_id: i.vertical_id,
      comp_idx: i.comp_idx,
    })),
  };
}
