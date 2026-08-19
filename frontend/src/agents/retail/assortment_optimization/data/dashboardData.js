/**
 * The only place Assortment Optimization chooses where its data comes from.
 *
 * Components import `loadAssortmentDashboard` and never touch the fixture,
 * the selectors, or `fetch` directly.
 */

import { fetchDashboard } from "../../../../api/dashboard.js";
import { normalizeAssortmentDashboard, serializeScope } from "./contract.js";
import fixture from "./fixture.json";
import { buildDashboardFromFixture, scopedDrivenItems } from "./selectors.js";
import { buildDrilldown, drillableMetrics } from "./drilldown.js";

import { DATA_SOURCE } from "../../common/dataSource.js";

export { DATA_SOURCE };

/** Workbook-derived data, computed locally. Resolves immediately (no latency). */
async function loadFromFixture(scope, options) {
  return buildDashboardFromFixture(fixture, scope, options);
}

/** Resolve the rows for one scope. In api mode, directly fetch from live backend. */
async function resolveRows(scope) {
  if (DATA_SOURCE !== "api") return fixture;
  return fetchDashboard("retail.assortment_optimization", serializeScope(scope));
}

/**
 * Load the Assortment Optimization dashboard for one scope.
 *
 * @param {Partial<import("./contract.js").AssortmentScope>} [scope]
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadAssortmentDashboard(scope = {}, options = {}) {
  const payload =
    DATA_SOURCE === "api"
      ? buildDashboardFromFixture(await resolveRows(scope), scope, options)
      : await loadFromFixture(scope, options);
  return normalizeAssortmentDashboard(payload);
}

/**
 * Break one KPI tile down, for the drill-down drawer.
 *
 * @param {Partial<import("./contract.js").AssortmentScope>} scope
 * @param {string} metricId
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadAssortmentDrilldown(scope, metricId, options = {}) {
  if (!drillableMetrics().includes(metricId)) {
    throw new Error(`Assortment Optimization KPI ${metricId} is not drillable`);
  }

  // The FULL scoped population, not `dashboard.action_preview`: that block
  // has already dropped every "hold" SKU, which would understate a
  // contribution/day or GMROI breakdown by most of the range. Each metric
  // narrows to its own population itself (capital freed to delist only).
  const rows = await resolveRows(scope);
  const { items } = scopedDrivenItems(rows, scope, options);
  return buildDrilldown(metricId, items);
}
