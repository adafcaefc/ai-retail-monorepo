/**
 * The only place Pricing & Markdown chooses where its data comes from.
 *
 * Components import `loadPricingMarkdownDashboard` and never touch the
 * fixture, the selectors, or `fetch` directly.
 *
 * THE API BRANCH FALLS BACK TO THE FIXTURE, ON PURPOSE.
 * `retail.pricing_markdown` has no backend module yet: its descriptor is
 * still `navigation_module(..., dashboard_only=True)` in
 * `backend/src/llm/agents/retail/pricing_markdown/__init__.py`, so
 * `GET /api/html/dashboard/retail.pricing_markdown` answers with an empty
 * shell — no `items`, no `formulas`. Handing that to the selectors throws
 * ("cannot simulate without f01-ads-per-store..."), which is a blank error
 * screen where a board should be.
 *
 * So the API branch checks what came back and falls back to the bundled
 * workbook fixture when the backend has nothing to give. The board then
 * renders the same figures the standalone build shows, and its own data
 * note ("Workbook demonstration data, not a live ERP position") is already
 * on screen saying where they came from — the reader is not told these are
 * live numbers.
 *
 * When the backend module lands and starts returning real rows, this file
 * needs no change: `isUnusable` stops matching and the API rows flow
 * through the identical selectors.
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
 * True when a payload carries nothing this board can render.
 *
 * The navigation-stub backend returns a structurally valid but empty
 * dashboard (`{agent, default_view: "", kpis: [], views: {}, ...}`) with no
 * `items` and no `formulas`. That is the case this catches.
 */
function isUnusable(payload) {
  return (
    !payload ||
    !Array.isArray(payload.items) ||
    payload.items.length === 0 ||
    !payload.formulas ||
    Object.keys(payload.formulas).length === 0
  );
}

/**
 * The canonical dashboard route every agent is served through. Falls back to
 * the bundled workbook fixture while the backend module is still a stub —
 * see the module docstring for why that is the honest choice here.
 */
async function loadFromApi(scope, options) {
  let rows = null;
  try {
    rows = await fetchDashboard("retail.pricing_markdown", serializeScope(scope));
  } catch {
    // A 404/503/network failure is the same situation as an empty payload:
    // the backend cannot answer for this agent yet. Fall through.
    rows = null;
  }
  return buildDashboardFromFixture(isUnusable(rows) ? fixture : rows, scope, options);
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
  // Same source resolution as the board itself, fallback included — a drawer
  // that opened against different rows than the tile it came from would be
  // worse than one that does not open.
  let rows = fixture;
  if (DATA_SOURCE === "api") {
    let fetched = null;
    try {
      fetched = await fetchDashboard("retail.pricing_markdown", serializeScope(scope));
    } catch {
      fetched = null;
    }
    rows = isUnusable(fetched) ? fixture : fetched;
  }

  // The drawer needs the scoped, lever-driven candidate rows, not the
  // finished dashboard. `candidates` on the built dashboard is the preview
  // table's population (capped at 300, comfortably above the ~234-candidate
  // baseline); reusing it here — rather than exposing a separate uncapped
  // accessor — is the same tradeoff promotion_effectiveness's drilldown makes
  // with its own (smaller, 12-row) `largest_margin_skus` population.
  const dashboard = buildDashboardFromFixture(rows, scope, options);
  return buildDrilldown(metricId, dashboard.candidates);
}
