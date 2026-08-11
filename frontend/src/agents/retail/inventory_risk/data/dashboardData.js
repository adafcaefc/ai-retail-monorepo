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
import { buildDashboardFromFixture } from "./selectors.js";

/** @type {"fixture" | "api"} */
export const DATA_SOURCE = "fixture";

/**
 * Workbook-derived data, computed locally.
 *
 * Async so both branches share one signature, but it resolves immediately —
 * no artificial latency. Tests that need to observe a loading state should
 * supply their own controlled promise rather than have production code wait.
 */
async function loadFromFixture(scope) {
  return buildDashboardFromFixture(fixture, scope);
}

/**
 * The future path: the canonical dashboard route every other agent uses.
 *
 * `serializeScope` drops `ALL` and empty search, which is also what
 * `fetchDashboard` does, so a scope means the same thing on both sides.
 * Note the backend route currently forwards only `legal_entity_id`, `period`,
 * and `category_group` positionally into a module builder — `store_id`,
 * `state` and `sku` need the generic query-context extension agreed for the
 * Retail dashboards before this branch returns a correctly scoped payload.
 */
async function loadFromApi(scope) {
  return fetchDashboard("retail.inventory_risk", serializeScope(scope));
}

/**
 * Load the Inventory Risk dashboard for one scope.
 *
 * @param {Partial<import("./contract.js").InventoryRiskScope>} [scope]
 * @returns {Promise<import("./contract.js").InventoryRiskDashboard>}
 */
export async function loadInventoryRiskDashboard(scope = {}) {
  const payload =
    DATA_SOURCE === "api" ? await loadFromApi(scope) : await loadFromFixture(scope);

  return normalizeInventoryRiskDashboard(payload);
}
