/**
 * The only place Replenishment chooses where its data comes from.
 *
 * Same seam as the other two Retail boards: components import
 * `loadReplenishmentDashboard` and never touch the fixture, the selectors or
 * `fetch`. Flipping `DATA_SOURCE` is the whole cutover.
 */

import { fetchDashboard } from "../../../../api/dashboard.js";
import { AGENT_ID, normalizeReplenishmentDashboard, serializeScope } from "./contract.js";
import fixture from "./fixture.json";
import {
  buildDashboardFromFixture,
  buildDrilldownFromFixture,
} from "./selectors.js";

/*
 * Where the rows come from.
 *
 * "api" asks the backend, which reads Postgres; "fixture" reads the copy
 * checked in beside this file. Both then run the SAME selectors over the SAME
 * shape, which is what makes the switch safe: the backend builder returns rows
 * rather than a finished dashboard, and
 * `backend/tests/test_retail_dashboard_builders.py` asserts field for field
 * that its payload equals this fixture. Nothing on screen can move.
 *
 * Tests stay on the fixture because jsdom has no server to answer them, not
 * because the two disagree. `import.meta.env.MODE` is Vite's own flag and is
 * "test" under Vitest.
 */
export const DATA_SOURCE = import.meta.env.MODE === "test" ? "fixture" : "api";


async function loadFromFixture(scope, options) {
  return buildDashboardFromFixture(fixture, scope, options);
}

/**
 * The canonical dashboard route every agent is served through.
 *
 * The response is the same row shape the fixture holds, so it goes through the
 * identical selectors — the API does not return a finished dashboard, and it
 * deliberately does not: the aggregation has one implementation, in
 * `selectors.js`, and a second one in Python would have to be kept in step
 * with it forever.
 *
 * `serializeScope` drops `ALL` and empty search, matching what `fetchDashboard`
 * does, so a scope means the same thing on both sides. The server narrows by
 * legal entity and category in SQL; the selectors apply the rest over the rows
 * that come back.
 */
async function loadFromApi(scope, options) {
  const rows = await fetchDashboard(AGENT_ID, serializeScope(scope));
  return buildDashboardFromFixture(rows, scope, options);
}

/**
 * Load the Replenishment dashboard for one scope.
 *
 * `options.levers` is a What-If position; `options.driveWholePage` decides
 * whether it reaches the rest of the board or stays inside the simulator panel.
 * Neither is part of the scope and neither is sent to the API — the server has
 * no simulation route yet, and when it does, this is the one function that has
 * to learn about it.
 *
 * @param {Partial<import("./contract.js").ReplenishmentScope>} [scope]
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadReplenishmentDashboard(scope = {}, options = {}) {
  const payload =
    DATA_SOURCE === "api"
      ? await loadFromApi(scope, options)
      : await loadFromFixture(scope, options);
  return normalizeReplenishmentDashboard(payload);
}

/**
 * Break one KPI tile down, for the drill-down drawer.
 *
 * It re-derives the scope rather than reading the finished payload, for one
 * reason worth stating: `purchase_order` is filtered to lines actually being
 * ordered (`order_qty_sales > 0`). Fill rate is measured over EVERY line in
 * scope — that is the whole point of it — so a drawer built from the purchase
 * order would report a fill rate near zero and look like a bug.
 *
 * Same scope in, same lines out, same reducers as the tiles above it.
 *
 * @param {Partial<import("./contract.js").ReplenishmentScope>} scope
 * @param {string} metricId
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadReplenishmentDrilldown(scope, metricId, options = {}) {
  const rows =
    DATA_SOURCE === "api"
      ? await fetchDashboard(AGENT_ID, serializeScope(scope))
      : fixture;

  return buildDrilldownFromFixture(rows, scope, metricId, options);
}
