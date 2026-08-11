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

export async function loadDemandForecastingDashboard(inputQuery = {}) {
  const query = normalizeDemandQuery(inputQuery);

  if (demandForecastingDataSource() === "api") {
    const payload = await fetchDashboard(DEMAND_AGENT_ID, query);
    return normalizeDemandDashboard(payload);
  }

  return getMockDemandForecastingDashboard(query);
}

