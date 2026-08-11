import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  load: vi.fn(),
  runScenario: vi.fn(),
}));

vi.mock("./data/dashboardData.js", () => ({
  loadDemandForecastingDashboard: mocks.load,
  loadDemandForecastingScenario: mocks.runScenario,
}));

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import DemandForecastingDashboard from "./DemandForecastingDashboard.jsx";
import { visibleDemandScenarios } from "./components/DemandScenarioComparison.jsx";
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
    mocks.load.mockImplementation((query, levers) => getMockDemandForecastingDashboard(query, levers));
    mocks.runScenario.mockImplementation((query, levers) => getMockDemandForecastingDashboard(query, levers));
  });

  it("renders six KPIs, both forecast panels, trending, and forecast detail", async () => {
    renderDashboard();

    expect((await screen.findAllByText("1,656,179")).length).toBeGreaterThanOrEqual(2);
    expect(document.querySelectorAll(".demand-kpi")).toHaveLength(6);
    expect(screen.getByRole("heading", { name: "Demand forecast — actual vs AI" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Demand forecast · actual vs AI" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Predicted to trend" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Forecast detail" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Forecast by category" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Forecast by store" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Forecast by cluster" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Seasonality curve (12 mo)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "By legal entity" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What-If Simulator" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Compare Scenarios" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Suggested Best Action" })).toBeInTheDocument();
    expect(screen.getByText("No saved scenarios yet")).toBeInTheDocument();
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
      .mockImplementation((query, levers) => getMockDemandForecastingDashboard(query, levers));
    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent("Demand data unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect((await screen.findAllByText("1,656,179")).length).toBeGreaterThanOrEqual(2);
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
      }), expect.any(Object));
    });
    expect((await screen.findAllByText("GRC · Grocery Retail")).length).toBeGreaterThan(0);
  });

  it("updates grain and horizon independently", async () => {
    renderDashboard();
    await screen.findAllByText("1,656,179");

    const overview = screen.getByRole("heading", { name: "Demand forecast — actual vs AI" }).closest("section");
    const daily = within(overview).getByRole("button", { name: "Daily" });
    fireEvent.click(daily);
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ grain: "daily" }), expect.any(Object)));
    expect(daily).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "12w" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ grain: "daily", horizon_weeks: 12 }), expect.any(Object)));
    expect(screen.getByRole("button", { name: "12w" })).toHaveAttribute("aria-pressed", "true");
  });

  it("submits SKU search and clear restores the default query", async () => {
    renderDashboard();
    await screen.findAllByText("1,656,179");

    const input = screen.getByRole("searchbox", { name: "SKU search" });
    fireEvent.change(input, { target: { value: "GRC-001" } });
    fireEvent.submit(input.closest("form"));

    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ sku: "GRC-001" }), expect.any(Object)));
    expect((await screen.findAllByText("GRC-001")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ sku: "", grain: "weekly", horizon_weeks: 8 }), expect.any(Object)));
    expect(input).toHaveValue("");
  });

  it("applies category and store dimension selections to the existing scope", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "Forecast by category" });

    const categoryPanel = screen.getByRole("heading", { name: "Forecast by category" }).closest("article");
    fireEvent.click(within(categoryPanel).getByRole("button", { name: "Fresh Produce" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(
      expect.objectContaining({ category_group: "GRC-C01" }),
      expect.any(Object),
    ));

    const storePanel = screen.getByRole("heading", { name: "Forecast by store" }).closest("article");
    fireEvent.click(within(storePanel).getByRole("button", { name: "GRC Jakarta 1" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(
      expect.objectContaining({ category_group: "GRC-C01", store_id: "GRC-S1" }),
      expect.any(Object),
    ));
  });

  it("runs, resets, saves, loads, compares, and removes local scenarios", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "What-If Simulator" });

    const loadButton = screen.getByRole("button", { name: "Load" });
    expect(loadButton).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    const demand = screen.getByRole("slider", { name: "Demand shift" });
    fireEvent.change(demand, { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => expect(mocks.runScenario).toHaveBeenCalledWith(
      expect.objectContaining({ grain: "weekly" }),
      expect.objectContaining({ demand: 20 }),
    ));
    await waitFor(() => expect(document.querySelector(".demand-kpi-value")).not.toHaveTextContent("1,656,179"));

    const saveButton = screen.getByRole("button", { name: "Save" });
    await waitFor(() => expect(saveButton).toBeEnabled());
    fireEvent.click(saveButton);
    expect(await screen.findByText("S1")).toBeInTheDocument();
    expect(loadButton).toBeEnabled();

    fireEvent.change(demand, { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(mocks.runScenario).toHaveBeenLastCalledWith(
      expect.any(Object),
      expect.objectContaining({ demand: 10 }),
    ));
    await waitFor(() => expect(saveButton).toBeEnabled());
    fireEvent.click(saveButton);
    expect(await screen.findByText("S2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    await waitFor(() => expect(demand).toHaveValue("10"));

    fireEvent.click(screen.getByRole("button", { name: "Remove S1" }));
    expect(screen.queryByRole("button", { name: "Remove S1" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove S2" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    await waitFor(() => expect(document.querySelector(".demand-kpi-value")).toHaveTextContent("1,656,179"));
    expect(demand).toHaveValue("0");
  });

  it("shows and clears the applied whole-page scenario indicator", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "What-If Simulator" });

    fireEvent.change(screen.getByRole("slider", { name: "Demand shift" }), {
      target: { value: "20" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByRole("status", { name: "What-If scenario applied" }))
      .toHaveTextContent("Demand shift +20%");
    fireEvent.click(screen.getByRole("button", { name: "Clear applied scenario" }));

    await waitFor(() => {
      expect(screen.queryByRole("status", { name: "What-If scenario applied" }))
        .not.toBeInTheDocument();
      expect(document.querySelector(".demand-kpi-value")).toHaveTextContent("1,656,179");
    });
    expect(screen.getByRole("slider", { name: "Demand shift" })).toHaveValue("0");
  });

  it("hides saved scenarios outside their scope, grain, or horizon and restores compatibility", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "What-If Simulator" });
    const demand = screen.getByRole("slider", { name: "Demand shift" });

    fireEvent.change(demand, { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("button", { name: "Remove S1" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Legal entity"), { target: { value: "GRC" } });
    await waitFor(() => expect(screen.getByText(/1 hidden by current scope/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Remove S1" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Legal entity"), { target: { value: "ALL" } });
    expect(await screen.findByRole("button", { name: "Remove S1" })).toBeInTheDocument();

    const overview = screen.getByRole("heading", { name: "Demand forecast — actual vs AI" }).closest("section");
    fireEvent.click(within(overview).getByRole("button", { name: "Monthly" }));
    await waitFor(() => expect(screen.getByText(/1 hidden by current scope/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Remove S1" })).not.toBeInTheDocument();

    fireEvent.click(within(overview).getByRole("button", { name: "Weekly" }));
    expect(await screen.findByRole("button", { name: "Remove S1" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "12w" }));
    await waitFor(() => expect(screen.getByText(/1 hidden by current scope/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Remove S1" })).not.toBeInTheDocument();
  });

  it("Load restores a saved scenario's dashboard context and lever values", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "What-If Simulator" });

    fireEvent.change(screen.getByLabelText("Legal entity"), { target: { value: "GRC" } });
    const overview = screen.getByRole("heading", { name: "Demand forecast — actual vs AI" }).closest("section");
    fireEvent.click(within(overview).getByRole("button", { name: "Monthly" }));
    fireEvent.click(screen.getByRole("button", { name: "12w" }));
    fireEvent.change(screen.getByRole("slider", { name: "Demand shift" }), {
      target: { value: "20" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(screen.getByLabelText("Legal entity")).toHaveValue("ALL"));
    fireEvent.click(screen.getByRole("button", { name: "Load" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Legal entity")).toHaveValue("GRC");
      expect(within(overview).getByRole("button", { name: "Monthly" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "12w" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("slider", { name: "Demand shift" })).toHaveValue("20");
      expect(screen.getByRole("button", { name: "Remove S1" })).toBeInTheDocument();
    });
  });

  it("keeps the latest-four overlay limit among compatible scenarios", () => {
    const scenarios = Array.from({ length: 6 }, (_, index) => ({ id: `S${index + 1}` }));
    expect(visibleDemandScenarios(scenarios).map((scenario) => scenario.id))
      .toEqual(["S3", "S4", "S5", "S6"]);
  });

  it("surfaces an incomplete API contract as a visible dashboard error", async () => {
    mocks.load.mockRejectedValueOnce(
      new Error("Demand Forecasting API contract field dimensions is required."),
    );
    renderDashboard();

    expect(await screen.findByRole("alert"))
      .toHaveTextContent("Demand Forecasting API contract field dimensions is required.");
  });

  it("renders mock best actions while every transactional control stays disabled", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "Suggested Best Action" });

    expect(screen.getByText("Send 7-day forecast basket to Replenishment")).toBeInTheDocument();
    expect(screen.getByText(/Raise safety stock on 302 stockout-risk SKUs/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send to Replenishment" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Flag to Inventory Risk" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Preview forecast basket" }));
    expect(screen.getByRole("button", { name: "Generate forecast basket" })).toBeDisabled();
  });
});
