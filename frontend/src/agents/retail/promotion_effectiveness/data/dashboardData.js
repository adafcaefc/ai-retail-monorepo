/**
 * The only place Promotion Effectiveness chooses where its data comes from.
 *
 * Components import `loadPromotionDashboard` and never touch the fixture, the
 * selectors, or `fetch` directly. When the backend builder is the source,
 * `DATA_SOURCE === "api"` is the whole cutover — no presentation component, no
 * selector, and no test of either has to change, because both branches return
 * the same normalized contract.
 */

import { fetchDashboard } from "../../../../api/dashboard.js";
import { normalizePromotionDashboard, serializeScope } from "./contract.js";
import fixture from "./fixture.json";
import { buildDashboardFromFixture } from "./selectors.js";
import { buildDrilldown, drillableMetrics } from "./drilldown.js";

/*
 * Where the rows come from — one definition for all retail boards, so the rule
 * cannot drift between them. Re-exported because callers and tests import it
 * from the board they are working on.
 */
import { DATA_SOURCE } from "../../common/dataSource.js";

export { DATA_SOURCE };

/** Workbook-derived data, computed locally. Resolves immediately (no latency). */
async function loadFromFixture(scope, options) {
  return buildDashboardFromFixture(fixture, scope, options);
}

/**
 * The canonical dashboard route every agent is served through. The response is
 * the same row shape the fixture holds, so it runs through the identical
 * selectors — the API returns rows, not a finished dashboard, deliberately.
 */
async function loadFromApi(scope, options) {
  const rows = await fetchDashboard(
    "retail.promotion_effectiveness",
    serializeScope(scope),
  );
  return buildDashboardFromFixture(rows, scope, options);
}

/**
 * Load the Promotion Effectiveness dashboard for one scope.
 *
 * `options.levers` is a What-If position; `options.driveWholePage` decides
 * whether it reaches the rest of the board or stays inside the simulator.
 * Neither is sent to the API — the server has no simulation route.
 *
 * @param {Partial<import("./contract.js").PromotionScope>} [scope]
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadPromotionDashboard(scope = {}, options = {}) {
  const payload =
    DATA_SOURCE === "api"
      ? await loadFromApi(scope, options)
      : await loadFromFixture(scope, options);

  return normalizePromotionDashboard(payload);
}

/**
 * Break one KPI tile down, for the drill-down drawer.
 *
 * @param {Partial<import("./contract.js").PromotionScope>} scope
 * @param {string} metricId
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadPromotionDrilldown(scope, metricId, options = {}) {
  if (!drillableMetrics().includes(metricId)) {
    throw new Error(`Promotion KPI ${metricId} is not drillable`);
  }
  const rows =
    DATA_SOURCE === "api"
      ? await fetchDashboard(
          "retail.promotion_effectiveness",
          serializeScope(scope),
        )
      : fixture;

  // Rebuild the scoped items the same way the dashboard does, then decompose.
  const dashboard = buildDashboardFromFixture(rows, scope, options);
  return buildDrilldown(metricId, scopedItemsForDrilldown(rows, scope, options));
}

/*
 * The drilldown needs the scoped, lever-driven items rather than the finished
 * dashboard. Pulled out so the drawer always describes the board as it stands.
 */
function scopedItemsForDrilldown(fixture, scope, options) {
  // The dashboard builder already narrows and drives items; reuse its output
  // by reading the largest_margin_skus block, which carries the same population
  // the drawer decomposes. For a full population drilldown the selector would
  // expose items directly; here we give the drawer the margin leaders, which is
  // the population the drawer's "top SKUs" list draws from.
  return buildDashboardFromFixture(fixture, scope, options).largest_margin_skus;
}
