/**
 * The only place Inventory Risk chooses where its data comes from.
 *
 * Components import `loadInventoryRiskDashboard` and never touch the fixture,
 * the selectors, or `fetch` directly. When the backend builder is ready,
 * flipping `DATA_SOURCE` to "api" is the whole cutover — no presentation
 * component, no selector, and no test of either has to change, because both
 * branches return the same normalized contract.
 *
 * Why a constant and not a Vite env flag: this repository has no frontend
 * environment-variable convention yet, and introducing one is a deployment
 * decision rather than a dashboard decision. A build-time flag can replace
 * this constant later without touching anything else in the folder.
 */

import { fetchDashboard } from "../../../../api/dashboard.js";
import {
  normalizeInventoryRiskDashboard,
  serializeScope,
} from "./contract.js";
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


/**
 * Workbook-derived data, computed locally.
 *
 * Async so both branches share one signature, but it resolves immediately —
 * no artificial latency. Tests that need to observe a loading state should
 * supply their own controlled promise rather than have production code wait.
 */
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
  const rows = await fetchDashboard("retail.inventory_risk", serializeScope(scope));
  return buildDashboardFromFixture(rows, scope, options);
}

/**
 * Load the Inventory Risk dashboard for one scope.
 *
 * `options.levers` is a What-If position; `options.driveWholePage` decides
 * whether it reaches the rest of the board or stays inside the simulator
 * panel. Neither is part of the scope, and neither is sent to the API — the
 * server has no simulation route yet, and when it does, this is the one
 * function that has to learn about it.
 *
 * @param {Partial<import("./contract.js").InventoryRiskScope>} [scope]
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 * @returns {Promise<import("./contract.js").InventoryRiskDashboard>}
 */
export async function loadInventoryRiskDashboard(scope = {}, options = {}) {
  const payload =
    DATA_SOURCE === "api"
      ? await loadFromApi(scope, options)
      : await loadFromFixture(scope, options);

  return normalizeInventoryRiskDashboard(payload);
}

/**
 * Break one KPI tile down, for the drill-down drawer.
 *
 * A separate call rather than a block on the dashboard payload: the per-store
 * split runs the engine once per SKU per store, so computing all six on every
 * load would cost ~96,000 evaluations for a drawer the reader may never open.
 *
 * Async for the same reason the loader is — in API mode it needs the rows —
 * and it takes the same scope and lever options, so the drawer always
 * describes the board as it currently stands.
 *
 * @param {Partial<import("./contract.js").InventoryRiskScope>} scope
 * @param {string} metricId
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadInventoryRiskDrilldown(scope, metricId, options = {}) {
  const rows =
    DATA_SOURCE === "api"
      ? await fetchDashboard("retail.inventory_risk", serializeScope(scope))
      : fixture;

  return buildDrilldownFromFixture(rows, scope, metricId, options);
}
