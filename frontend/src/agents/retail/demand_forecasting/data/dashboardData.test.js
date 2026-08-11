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
});

