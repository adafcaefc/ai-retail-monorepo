import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  load: vi.fn(),
}));

vi.mock("./data/dashboardData.js", () => ({
  loadDemandForecastingDashboard: mocks.load,
}));

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import DemandForecastingDashboard from "./DemandForecastingDashboard.jsx";
import { getMockDemandForecastingDashboard } from "./data/mockDashboard.js";

function renderDashboard() {
  return render(
    <LanguageProvider>
      <DemandForecastingDashboard />
    </LanguageProvider>,
  );
}

describe("DemandForecastingDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    mocks.load.mockImplementation((query) => getMockDemandForecastingDashboard(query));
  });

  it("renders six KPIs, both forecast panels, trending, and forecast detail", async () => {
    renderDashboard();

    expect(await screen.findAllByText("1,656,179")).toHaveLength(2);
    expect(document.querySelectorAll(".demand-kpi")).toHaveLength(6);
    expect(screen.getByRole("heading", { name: "Demand forecast — actual vs AI" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Demand forecast · actual vs AI" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Predicted to trend" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Forecast detail" })).toBeInTheDocument();
    expect(screen.getByText("Saturday ×1.35")).toBeInTheDocument();
    expect(screen.getAllByText("93.0%")).toHaveLength(2);
    expect(document.querySelectorAll(".demand-detail-scroll tbody tr")).toHaveLength(100);
  });

  it("shows a shape-matched loading state", () => {
    mocks.load.mockReturnValue(new Promise(() => {}));
    renderDashboard();

    expect(screen.getByRole("status", { name: "Loading Demand Forecasting dashboard" })).toBeInTheDocument();
  });

  it("shows an initial error and retries successfully", async () => {
    mocks.load
      .mockRejectedValueOnce(new Error("Demand data unavailable"))
      .mockImplementation((query) => getMockDemandForecastingDashboard(query));
    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent("Demand data unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findAllByText("1,656,179")).toHaveLength(2);
    expect(mocks.load).toHaveBeenCalledTimes(2);
  });

  it("updates legal entity and resets dependent filters", async () => {
    renderDashboard();
    await screen.findAllByText("1,656,179");

    fireEvent.change(screen.getByLabelText("Legal entity"), { target: { value: "GRC" } });

    await waitFor(() => {
      expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({
        legal_entity_id: "GRC",
        category_group: "ALL",
        store_id: "ALL",
      }));
    });
    expect((await screen.findAllByText("GRC · Grocery Retail")).length).toBeGreaterThan(0);
  });

  it("updates grain and horizon independently", async () => {
    renderDashboard();
    await screen.findAllByText("1,656,179");

    const overview = screen.getByRole("heading", { name: "Demand forecast — actual vs AI" }).closest("section");
    const daily = within(overview).getByRole("button", { name: "Daily" });
    fireEvent.click(daily);
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ grain: "daily" })));
    expect(daily).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "12w" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ grain: "daily", horizon_weeks: 12 })));
    expect(screen.getByRole("button", { name: "12w" })).toHaveAttribute("aria-pressed", "true");
  });

  it("submits SKU search and clear restores the default query", async () => {
    renderDashboard();
    await screen.findAllByText("1,656,179");

    const input = screen.getByRole("searchbox", { name: "SKU search" });
    fireEvent.change(input, { target: { value: "GRC-001" } });
    fireEvent.submit(input.closest("form"));

    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ sku: "GRC-001" })));
    expect((await screen.findAllByText("GRC-001")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ sku: "", grain: "weekly", horizon_weeks: 8 })));
    expect(input).toHaveValue("");
  });
});
