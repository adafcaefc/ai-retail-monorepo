/**
 * The only place Pricing & Markdown chooses where its data comes from.
 *
 * Components import `loadPricingMarkdownDashboard` and never touch the
 * fixture, the selectors, or `fetch` directly. Same seam as Replenishment
 * and Promotion Effectiveness: a failed request propagates to the caller's
 * existing error state instead of being swapped for the bundled fixture —
 * silently substituting demo data for a real backend failure reads as the
 * board working when it is not.
 *
 * FETCH AND BUILD ARE SEPARATE ON PURPOSE. `serializeScope` never encodes
 * levers or `driveWholePage` — the network/fixture read depends only on
 * `scope`, and every lever's effect happens entirely client-side in
 * `buildDashboardFromFixture` (pure, synchronous). So the What-If simulator
 * can be live — every slider move recomputed immediately — without a
 * network round-trip per tick: fetch `rows` once per scope
 * (`loadPricingMarkdownRows`), then rebuild the dashboard synchronously off
 * the same rows as levers change (`buildPricingMarkdownDashboard`).
 */

import { fetchDashboard } from "../../../../api/dashboard.js";
import { normalizePricingDashboard, serializeScope } from "./contract.js";
import fixture from "./fixture.json";
import { buildDashboardFromFixture } from "./selectors.js";
import { buildDrilldown, drillableMetrics } from "./drilldown.js";

import { DATA_SOURCE } from "../../common/dataSource.js";

export { DATA_SOURCE };

/**
 * The raw rows a scope resolves to — workbook fixture or live API, whichever
 * `DATA_SOURCE` selects. No lever/driveWholePage dependency: those apply
 * afterward, client-side, in `buildPricingMarkdownDashboard`.
 *
 * @param {Partial<import("./contract.js").PricingScope>} [scope]
 */
export async function loadPricingMarkdownRows(scope = {}) {
  return DATA_SOURCE === "api"
    ? await fetchDashboard("retail.pricing_markdown", serializeScope(scope))
    : fixture;
}

/**
 * Build the normalized dashboard shape from already-fetched rows. Pure and
 * synchronous, so a caller can re-run it on every lever change with no
 * latency — this is what makes the What-If simulator live.
 *
 * @param {object} rows
 * @param {Partial<import("./contract.js").PricingScope>} [scope]
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export function buildPricingMarkdownDashboard(rows, scope = {}, options = {}) {
  return normalizePricingDashboard(buildDashboardFromFixture(rows, scope, options));
}

/**
 * Load the Pricing & Markdown dashboard for one scope in one call — fetch
 * then build. Components that need to rebuild repeatedly at no latency (the
 * What-If simulator) should call `loadPricingMarkdownRows` once and
 * `buildPricingMarkdownDashboard` on every lever change instead.
 *
 * @param {Partial<import("./contract.js").PricingScope>} [scope]
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadPricingMarkdownDashboard(scope = {}, options = {}) {
  const rows = await loadPricingMarkdownRows(scope);
  return buildPricingMarkdownDashboard(rows, scope, options);
}

/**
 * Break one KPI tile down, for the drill-down drawer.
 *
 * @param {Partial<import("./contract.js").PricingScope>} scope
 * @param {string} metricId
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadPricingMarkdownDrilldown(scope, metricId, options = {}) {
  if (!drillableMetrics().includes(metricId)) {
    throw new Error(`Pricing & Markdown KPI ${metricId} is not drillable`);
  }
  // Same source resolution as the board itself — a drawer that opened
  // against different rows than the tile it came from would be worse than
  // one that does not open.
  const rows = await loadPricingMarkdownRows(scope);

  // The drawer needs the scoped, lever-driven candidate rows, not the
  // finished dashboard. `candidates` on the built dashboard is the preview
  // table's population (capped at 300, comfortably above the ~234-candidate
  // baseline); reusing it here — rather than exposing a separate uncapped
  // accessor — is the same tradeoff promotion_effectiveness's drilldown makes
  // with its own (smaller, 12-row) `largest_margin_skus` population.
  const dashboard = buildDashboardFromFixture(rows, scope, options);
  // comp_idx is a per-SKU figure averaged over every SKU in scope, not just
  // markdown candidates (see computeKpis) — its drawer needs `sku_index`,
  // not `candidates`, or its breakdown would carry the same candidate-only
  // bias the headline tile itself no longer has.
  const drilldownRows = metricId === "comp_idx" ? dashboard.sku_index : dashboard.candidates;
  // Same lever the KPI tile itself was driven by, so a non-additive metric's
  // drawer (avg_depth_pct) shows the same figure the tile does.
  return buildDrilldown(metricId, drilldownRows, { markdownLever: dashboard.markdown_lever });
}
