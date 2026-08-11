import { fetchDashboard } from "../../../../api/dashboard.js";
import {
  DEMAND_AGENT_ID,
  normalizeDemandDashboard,
  normalizeDemandQuery,
} from "./contract.js";
import { getMockDemandForecastingDashboard } from "./mockDashboard.js";

export function demandForecastingDataSource() {
  const configured = String(
    import.meta.env.VITE_DEMAND_FORECASTING_DATA_SOURCE || "mock",
  ).toLowerCase();
  return configured === "api" ? "api" : "mock";
}

export async function loadDemandForecastingDashboard(inputQuery = {}, simulationLevers = {}) {
  const query = normalizeDemandQuery(inputQuery);

  if (demandForecastingDataSource() === "api") {
    const payload = await fetchDashboard(DEMAND_AGENT_ID, query);
    return normalizeDemandDashboard(payload, { requirePhase2: true });
  }

  return getMockDemandForecastingDashboard(query, simulationLevers);
}

/**
 * Mock-only simulation boundary. A future backend contract should accept the
 * normalized query plus lever values and return the same dashboard contract;
 * no production route is invented during this frontend phase.
 */
export async function loadDemandForecastingScenario(inputQuery = {}, simulationLevers = {}) {
  if (demandForecastingDataSource() === "api") {
    throw new Error("Demand Forecasting simulation backend integration is pending.");
  }
  return getMockDemandForecastingDashboard(
    normalizeDemandQuery(inputQuery),
    simulationLevers,
  );
}
