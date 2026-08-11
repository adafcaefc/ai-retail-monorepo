import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchDashboard: vi.fn(),
}));

vi.mock("../../../../api/dashboard.js", () => ({
  fetchDashboard: mocks.fetchDashboard,
}));

import { DEMAND_AGENT_ID } from "./contract.js";
import {
  demandForecastingDataSource,
  loadDemandForecastingDashboard,
  loadDemandForecastingScenario,
} from "./dashboardData.js";
import { getMockDemandForecastingDashboard } from "./mockDashboard.js";

describe("Demand Forecasting data gateway", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
  });

  it("defaults safely to mock mode", async () => {
    expect(demandForecastingDataSource()).toBe("mock");
    const dashboard = await loadDemandForecastingDashboard();

    expect(dashboard.is_mock).toBe(true);
    expect(mocks.fetchDashboard).not.toHaveBeenCalled();
  });

  it("uses the canonical dashboard client and normalized query in API mode", async () => {
    vi.stubEnv("VITE_DEMAND_FORECASTING_DATA_SOURCE", "api");
    const apiPayload = await getMockDemandForecastingDashboard({
      legal_entity_id: "GRC",
      horizon_weeks: 12,
    });
    mocks.fetchDashboard.mockResolvedValue({ ...apiPayload, is_mock: false });

    const result = await loadDemandForecastingDashboard({
      legal_entity_id: "GRC",
      horizon_weeks: 12,
      detail_limit: 500,
    });

    expect(demandForecastingDataSource()).toBe("api");
    expect(mocks.fetchDashboard).toHaveBeenCalledWith(
      DEMAND_AGENT_ID,
      expect.objectContaining({
        legal_entity_id: "GRC",
        horizon_weeks: 12,
        detail_offset: 0,
        detail_limit: 100,
      }),
    );
    expect(result.agent).toBe(DEMAND_AGENT_ID);
    expect(result.is_mock).toBe(false);
  });

  it("treats unsupported source values as mock mode", () => {
    vi.stubEnv("VITE_DEMAND_FORECASTING_DATA_SOURCE", "unexpected");
    expect(demandForecastingDataSource()).toBe("mock");
  });

  it("runs frontend scenarios in mock mode without making a backend request", async () => {
    const result = await loadDemandForecastingScenario({}, { demand: 20 });

    expect(result.simulation.applied).toBe(true);
    expect(result.simulation.scenario.forecast_next_7d)
      .toBeGreaterThan(result.simulation.baseline.forecast_next_7d);
    expect(mocks.fetchDashboard).not.toHaveBeenCalled();
  });

  it("does not invent a simulation endpoint in API mode", async () => {
    vi.stubEnv("VITE_DEMAND_FORECASTING_DATA_SOURCE", "api");

    await expect(loadDemandForecastingScenario({}, { demand: 20 }))
      .rejects.toThrow("simulation backend integration is pending");
    expect(mocks.fetchDashboard).not.toHaveBeenCalled();
  });

  it("rejects an incomplete schema-version-2 API payload instead of rendering empty panels", async () => {
    vi.stubEnv("VITE_DEMAND_FORECASTING_DATA_SOURCE", "api");
    const complete = await getMockDemandForecastingDashboard();
    const { dimensions: _dimensions, ...incomplete } = complete;
    mocks.fetchDashboard.mockResolvedValue({ ...incomplete, is_mock: false });

    await expect(loadDemandForecastingDashboard())
      .rejects.toThrow("API contract field dimensions is required");
    expect(mocks.fetchDashboard).toHaveBeenCalledTimes(1);
  });
});
