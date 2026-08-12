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
import { buildDashboardFromFixture } from "./selectors.js";

/** @type {"fixture" | "api"} */
export const DATA_SOURCE = "fixture";

async function loadFromFixture(scope) {
  return buildDashboardFromFixture(fixture, scope);
}

/**
 * The future path. The dashboard route currently forwards three parameters
 * positionally and drops the rest, so `route`, `store_id` and `reorder_only`
 * need the scope-object change agreed for the Retail boards before this branch
 * returns a correctly filtered purchase order.
 */
async function loadFromApi(scope) {
  return fetchDashboard(AGENT_ID, serializeScope(scope));
}

export async function loadReplenishmentDashboard(scope = {}) {
  const payload =
    DATA_SOURCE === "api" ? await loadFromApi(scope) : await loadFromFixture(scope);
  return normalizeReplenishmentDashboard(payload);
}
