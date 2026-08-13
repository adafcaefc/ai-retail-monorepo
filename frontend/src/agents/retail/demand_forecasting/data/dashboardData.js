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
    // Rows, not a finished dashboard — through the same selectors as below.
    const rows = await fetchDashboard(DEMAND_AGENT_ID, serializeScope(query));
    return normalizeDemandDashboard(
      buildDashboardFromFixture(rows, query, {
        levers: simulationLevers,
        driveWholePage: options.driveWholePage,
      }),
      { requirePhase2: true },
    );
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

/**
 * Break one KPI tile down, for the drill-down drawer.
 *
 * A separate call rather than a block on the board payload: six breakdowns the
 * reader may never open is work done on every load for nothing.
 *
 * @param {Partial<import("./contract.js").DemandDashboardQuery>} query
 * @param {string} metricId
 * @param {{levers?: object, driveWholePage?: boolean}} [options]
 */
export async function loadDemandForecastingDrilldown(query, metricId, options = {}) {
  const normalized = normalizeDemandQuery(query);
  const rows =
    DATA_SOURCE === "api"
      ? await fetchDashboard(DEMAND_AGENT_ID, serializeScope(normalized))
      : fixture;

  return buildDrilldownFromFixture(rows, normalized, metricId, {
    levers: options.levers,
    driveWholePage: options.driveWholePage,
  });
}
