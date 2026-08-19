/**
 * The only place Pricing & Markdown chooses where its data comes from.
 *
 * Components import `loadPricingMarkdownDashboard` and never touch the
 * fixture, the selectors, or `fetch` directly. Same seam as Replenishment
 * and Promotion Effectiveness: a failed request propagates to the caller's
 * existing error state instead of being swapped for the bundled fixture —
 * silently substituting demo data for a real backend failure reads as the
 * board working when it is not.
 */

import { fetchDashboard } from "../../../../api/dashboard.js";
import { normalizePricingDashboard, serializeScope } from "./contract.js";
import fixture from "./fixture.json";
import { buildDashboardFromFixture } from "./selectors.js";
import { buildDrilldown, drillableMetrics } from "./drilldown.js";

import { DATA_SOURCE } from "../../common/dataSource.js";

export { DATA_SOURCE };

/** Workbook-derived data, computed locally. Resolves immediately (no latency). */
async function loadFromFixture(scope, options) {
  return buildDashboardFromFixture(fixture, scope, options);
}

/**
 * The canonical dashboard route every agent is served through. The response
 * is the same row shape the fixture holds, so it runs through the identical
 * selectors — the API returns rows, not a finished dashboard, deliberately.
 */
async function loadFromApi(scope, options) {
  const rows = await fetchDashboard("retail.pricing_markdown", serializeScope(scope));
  return buildDashboardFromFixture(rows, scope, options);
}

/**
 * Load the Pricing & Markdown dashboard for one scope.
 *
 * @param {Partial<import("./contract.js").PricingScope>} [scope]
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadPricingMarkdownDashboard(scope = {}, options = {}) {
  const payload = DATA_SOURCE === "api" ? await loadFromApi(scope, options) : await loadFromFixture(scope, options);
  return normalizePricingDashboard(payload);
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
  const rows =
    DATA_SOURCE === "api"
      ? await fetchDashboard("retail.pricing_markdown", serializeScope(scope))
      : fixture;

  // The drawer needs the scoped, lever-driven candidate rows, not the
  // finished dashboard. `candidates` on the built dashboard is the preview
  // table's population (capped at 300, comfortably above the ~234-candidate
  // baseline); reusing it here — rather than exposing a separate uncapped
  // accessor — is the same tradeoff promotion_effectiveness's drilldown makes
  // with its own (smaller, 12-row) `largest_margin_skus` population.
  const dashboard = buildDashboardFromFixture(rows, scope, options);
  return buildDrilldown(metricId, dashboard.candidates);
}
