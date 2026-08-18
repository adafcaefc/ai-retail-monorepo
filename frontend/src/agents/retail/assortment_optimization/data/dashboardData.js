/**
 * The only place Assortment Optimization chooses where its data comes from.
 *
 * Components import `loadAssortmentDashboard` and never touch the fixture,
 * the selectors, or `fetch` directly.
 *
 * THE API BRANCH FALLS BACK TO THE FIXTURE, ON PURPOSE — same situation as
 * the Pricing & Markdown board. `retail.assortment_optimization` has no
 * backend module yet: its descriptor is still
 * `navigation_module(..., dashboard_only=True)`, so the dashboard route
 * answers with an empty shell carrying no `items` and no `formulas`. Handing
 * that to the selectors throws. The fallback keeps the board rendering the
 * bundled workbook figures, which its own data note already labels as
 * demonstration data rather than a live ERP position.
 *
 * When the backend module lands, this file needs no change: `isUnusable`
 * stops matching and the API rows flow through the identical selectors.
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

/** True when a payload carries nothing this board can render. */
function isUnusable(payload) {
  return (
    !payload ||
    !Array.isArray(payload.items) ||
    payload.items.length === 0 ||
    !payload.formulas ||
    Object.keys(payload.formulas).length === 0
  );
}

/** Resolve the rows for one scope, falling back to the bundled fixture. */
async function resolveRows(scope) {
  if (DATA_SOURCE !== "api") return fixture;
  let fetched = null;
  try {
    fetched = await fetchDashboard("retail.assortment_optimization", serializeScope(scope));
  } catch {
    // A 404/503/network failure is the same situation as an empty payload:
    // the backend cannot answer for this agent yet.
    fetched = null;
  }
  return isUnusable(fetched) ? fixture : fetched;
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

  // Same source resolution as the board itself, fallback included — a drawer
  // that opened against different rows than the tile it came from would be
  // worse than one that does not open.
  //
  // The FULL scoped population, not `dashboard.action_preview`: that block
  // has already dropped every "hold" SKU, which would understate a
  // contribution/day or GMROI breakdown by most of the range. Each metric
  // narrows to its own population itself (capital freed to delist only).
  const rows = await resolveRows(scope);
  const { items } = scopedDrivenItems(rows, scope, options);
  return buildDrilldown(metricId, items);
}
