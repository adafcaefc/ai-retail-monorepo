/**
 * The only place Demand Forecasting chooses where its data comes from.
 *
 * Components import `loadDemandForecastingDashboard` and never touch the
 * fixture, the selectors, or `fetch` directly. `DATA_SOURCE` selects either
 * the checked-in fixture or the backend row payload; both use these selectors.
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
 * Where the rows come from — one definition for all three boards, so the
 * rule cannot drift between them. Re-exported because callers and tests
 * import it from the board they are working on.
 */
import { DATA_SOURCE } from "../../common/dataSource.js";

export { DATA_SOURCE };


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
        requireDemandForecastSeries: true,
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
 * them to the page.
 *
 * There is no dedicated scenario backend route. In fixture builds this is
 * fully local; in API builds it first fetches the current dashboard rows, then
 * applies the same browser-side selectors and formulas. A lever moves the
 * arithmetic, not the rows — the source of the rows is the only network
 * dependency that varies here.
 *
 * This used to throw "backend integration is pending" whenever DATA_SOURCE was
 * "api", which is every run outside the test suite. The board caught it and
 * showed it as a scenario error, so Run scenario was dead in the browser and
 * green in CI — the fixture path was the only one the tests could reach.
 */
export async function loadDemandForecastingScenario(
  inputQuery = {},
  simulationLevers = {},
) {
  const query = normalizeDemandQuery(inputQuery);
  const rows =
    DATA_SOURCE === "api"
      ? await fetchDashboard(DEMAND_AGENT_ID, serializeScope(query))
      : fixture;

  return normalizeDemandDashboard(
    buildDashboardFromFixture(rows, query, {
      levers: simulationLevers,
      driveWholePage: true,
      requireDemandForecastSeries: DATA_SOURCE === "api",
    }),
    { requirePhase2: DATA_SOURCE === "api" },
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
