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
import { createEngine, isBaseline } from "./engine.js";

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
      total: round(sum([...g.byType.values()])),
    }));
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
    .map(([k, rs]) => ({ key, value: reduce(rs) }))
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
  const items = scopeItems(fixture.items ?? [], scope);
  const campaigns = scopeCampaigns(fixture.campaigns ?? [], scope);
  const reference = fixture.reference_by_vertical ?? [];

  const levers = { ...BASELINE_LEVERS, ...(options.levers ?? {}) };
  const engine = engineFor(fixture.formulas ?? {});
  const applyLevers = (item, l) => engine(item, l);

  // Drive the items through the engine so a scenario reaches the cards and
  // charts, not just the simulator panel.
  const drivenItems =
    options.driveWholePage && !isBaseline(levers)
      ? items.map((i) => applyLevers(i, levers))
      : items;

  const kpis = computeKpis(drivenItems, campaigns);
  // Uplift and ROI are stored workbook KPIs (vertical grain on the A4 sheet),
  // not derivable from per-SKU chain rows: read the chain average from reference.
  kpis.uplift_pct = round(mean(reference.map((r) => r.uplift_pct)), 2);
  kpis.roi_x = round(mean(reference.map((r) => r.roi_x)), 2);

  const byVertical = computeByVertical(drivenItems, reference);

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
    largest_margin_skus: computeLargestMarginSkus(drivenItems),
    campaigns,
    best_actions: computeBestActions(campaigns),
    simulation: computeSimulation(drivenItems, levers, applyLevers, reference),
    reference_by_vertical: reference,
  };
}
