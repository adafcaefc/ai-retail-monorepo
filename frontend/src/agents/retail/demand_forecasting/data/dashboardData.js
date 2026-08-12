/**
 * The only place Demand Forecasting chooses where its data comes from.
 *
 * Components import `loadDemandForecastingDashboard` and never touch the
 * fixture, the selectors, or `fetch` directly. When the backend builder is
 * ready, flipping `DATA_SOURCE` to "api" is the whole cutover.
 *
 * This used to read `mockDataset.js`, which invented four legal entities, a
 * dozen categories and four hundred SKUs from a hash of the row index. It now
 * reads figures derived from the same workbook Inventory Risk reads, so a code
 * like `GRC-001` means one product across both boards.
 */

import { fetchDashboard } from "../../../../api/dashboard.js";
import {
  DEMAND_AGENT_ID,
  normalizeDemandDashboard,
  normalizeDemandQuery,
} from "./contract.js";
import fixture from "./fixture.json";
import { buildDashboardFromFixture } from "./selectors.js";

/** @type {"fixture" | "api"} */
export const DATA_SOURCE = "fixture";

export function demandForecastingDataSource() {
  return DATA_SOURCE;
}

export async function loadDemandForecastingDashboard(
  inputQuery = {},
  simulationLevers = {},
  options = {},
) {
  const query = normalizeDemandQuery(inputQuery);

  if (DATA_SOURCE === "api") {
    const payload = await fetchDashboard(DEMAND_AGENT_ID, query);
    return normalizeDemandDashboard(payload, { requirePhase2: true });
  }

  return normalizeDemandDashboard(
    buildDashboardFromFixture(fixture, query, {
      levers: simulationLevers,
      driveWholePage: options.driveWholePage,
    }),
  );
}

/**
 * Scenario preview: the same board under different levers, without applying
 * them to the page. No backend route is invented for it — when the API can
 * answer a scoped What-If, this is the second call site that has to learn.
 */
export async function loadDemandForecastingScenario(
  inputQuery = {},
  simulationLevers = {},
) {
  if (DATA_SOURCE === "api") {
    throw new Error("Demand Forecasting simulation backend integration is pending.");
  }
  return normalizeDemandDashboard(
    buildDashboardFromFixture(fixture, normalizeDemandQuery(inputQuery), {
      levers: simulationLevers,
      driveWholePage: true,
    }),
  );
}
