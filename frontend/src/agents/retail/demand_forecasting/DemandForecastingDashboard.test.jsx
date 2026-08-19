import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  load: vi.fn(),
  runScenario: vi.fn(),
  drilldown: vi.fn(),
}));

vi.mock("./data/dashboardData.js", () => ({
  loadDemandForecastingDashboard: mocks.load,
  loadDemandForecastingScenario: mocks.runScenario,
  loadDemandForecastingDrilldown: mocks.drilldown,
}));

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import DemandForecastingDashboard from "./DemandForecastingDashboard.jsx";
import { visibleDemandScenarios } from "./components/DemandScenarioComparison.jsx";
import { normalizeDemandDashboard } from "./data/contract.js";
import fixture from "./data/fixture.json";
import {
  buildDashboardFromFixture,
  buildDrilldownFromFixture,
} from "./data/selectors.js";

/*
 * The gateway is mocked, but what it returns is not: these render the real
 * provider over the real workbook fixture. Asserting against a hand-written
 * payload would only prove the payload matched itself.
 */
const board = (query, levers, options) =>
  normalizeDemandDashboard(
    buildDashboardFromFixture(fixture, query, { levers, ...options }),
  );

/**
 * The drawer builder is mocked at the gateway and real underneath, exactly as
 * the board is — so these assertions cover the actual decomposition rather
 * than a fixture of one.
 */
mocks.drilldown.mockImplementation(async (query, metricId) =>
  buildDrilldownFromFixture(fixture, query, metricId),
);

/** The chain's Forecast 7d, as the KPI tile prints it. */
const CHAIN_FORECAST = "1,656,178";

function renderDashboard() {
  return render(
    <LanguageProvider>
      <DemandForecastingDashboard />
    </LanguageProvider>,
  );
}

async function renderSettled() {
  const result = renderDashboard();
  // The chain forecast prints on the tile and again in the What-If strip, so
  // wait on "at least one" rather than "exactly one".
  await screen.findAllByText(CHAIN_FORECAST);
  return result;
}

describe("the KPI drill-down drawer", () => {
  // The suite's own harness lives in the describe below; these need the same
  // gateway wired before they render.
  beforeEach(() => {
    mocks.load.mockImplementation(async (query, levers, options) =>
      board(query, levers, options),
    );
  });

  it("decomposes a calculated tile, with no invented history", async () => {
    await renderSettled();

    fireEvent.click(screen.getByText("Forecast next 7 days").closest(".demand-kpi"));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("This metric by category")).toBeInTheDocument();
    expect(within(drawer).getByText("Top contributing SKUs")).toBeInTheDocument();
    // The mockup fills this with a seeded random walk; A1 has no dated source.
    expect(within(drawer).getByText(/No history recorded/)).toBeInTheDocument();
  });

  it("refuses to split a typed constant across categories", async () => {
    await renderSettled();

    // Accuracy is 92.4 in every vertical, typed into the A1 sheet. It has no
    // per-SKU basis, so a category split of it would be invented detail.
    fireEvent.click(screen.getByText("Forecast accuracy").closest(".demand-kpi"));

    const drawer = await screen.findByRole("dialog");
    expect(
      within(drawer).getByText(/constant typed into the A1 sheet/),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByText("This metric by category"),
    ).not.toBeInTheDocument();
  });
});

describe("DemandForecastingDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    mocks.load.mockImplementation((query, levers, options) => board(query, levers, options));
    mocks.runScenario.mockImplementation((query, levers) => board(query, levers));
  });

  it("renders six KPIs, both forecast panels, trending, and forecast detail", async () => {
    renderDashboard();

    expect((await screen.findAllByText(CHAIN_FORECAST)).length).toBeGreaterThanOrEqual(2);
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
    expect(screen.getAllByText("92.4%").length).toBeGreaterThanOrEqual(1);
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
      .mockImplementation((query, levers, options) => board(query, levers, options));
    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent("Demand data unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect((await screen.findAllByText(CHAIN_FORECAST)).length).toBeGreaterThanOrEqual(2);
    expect(mocks.load).toHaveBeenCalledTimes(2);
  });

  it("updates legal entity and resets dependent filters", async () => {
    renderDashboard();
    await screen.findAllByText(CHAIN_FORECAST);

    fireEvent.change(screen.getByLabelText("Legal entity"), { target: { value: "GRC" } });

    await waitFor(() => {
      expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({
        legal_entity_id: "GRC",
        category_group: "ALL",
        store_id: "ALL",
      }), expect.any(Object), expect.any(Object));
    });
    expect((await screen.findAllByText("GRC · Grocery Retail (Hypermarket)")).length).toBeGreaterThan(0);
  });

  it("updates grain and horizon independently", async () => {
    renderDashboard();
    await screen.findAllByText(CHAIN_FORECAST);

    const overview = screen.getByRole("heading", { name: "Demand forecast — actual vs AI" }).closest("section");
    const daily = within(overview).getByRole("button", { name: "Daily" });
    fireEvent.click(daily);
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ grain: "daily" }), expect.any(Object), expect.any(Object)));
    expect(daily).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "12w" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ grain: "daily", horizon_weeks: 12 }), expect.any(Object), expect.any(Object)));
    expect(screen.getByRole("button", { name: "12w" })).toHaveAttribute("aria-pressed", "true");
  });

  it("submits SKU search and clear restores the default query", async () => {
    renderDashboard();
    await screen.findAllByText(CHAIN_FORECAST);

    const input = screen.getByRole("searchbox", { name: "SKU search" });
    fireEvent.change(input, { target: { value: "GRC-001" } });
    fireEvent.submit(input.closest("form"));

    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ sku: "GRC-001" }), expect.any(Object), expect.any(Object)));
    expect((await screen.findAllByText("GRC-001")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(expect.objectContaining({ sku: "", grain: "weekly", horizon_weeks: 8 }), expect.any(Object), expect.any(Object)));
    expect(input).toHaveValue("");
  });

  it("applies category and store dimension selections to the existing scope", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "Forecast by category" });

    const categoryPanel = screen.getByRole("heading", { name: "Forecast by category" }).closest("article");
    fireEvent.click(within(categoryPanel).getByRole("button", { name: "Bakery" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(
      expect.objectContaining({ category_group: "GRC-C05" }),
      expect.any(Object),
      expect.any(Object),
    ));

    const storePanel = screen.getByRole("heading", { name: "Forecast by store" }).closest("article");
    fireEvent.click(within(storePanel).getByRole("button", { name: "Grocery 05 · Medan" }));
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(
      expect.objectContaining({ category_group: "GRC-C05", store_id: "S005" }),
      expect.any(Object),
      expect.any(Object),
    ));
  });

  it("runs, resets, saves, loads, compares, and removes local scenarios", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "What-If Simulator" });
    const storageBeforeSave = { ...window.localStorage };

    const loadButton = screen.getByRole("button", { name: "Load" });
    expect(loadButton).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    const demand = screen.getByRole("slider", { name: "Demand shift" });
    const savedLeverValues = {
      "Demand shift": 20,
      "Promo intensity": 25,
      "Markdown depth": 30,
      "Extra inbound": 40,
      "Vendor lead time": 3,
      "Safety stock": 4,
    };
    Object.entries(savedLeverValues).forEach(([name, value]) => {
      fireEvent.change(screen.getByRole("slider", { name }), { target: { value: String(value) } });
    });
    // Slider movement is draft-only; the page and Save remain unchanged until
    // Run commits the scenario.
    expect(mocks.runScenario).not.toHaveBeenCalled();
    expect(document.querySelector(".demand-kpi-value")).toHaveTextContent(CHAIN_FORECAST);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => expect(mocks.runScenario).toHaveBeenCalledWith(
      expect.objectContaining({ grain: "weekly" }),
      expect.objectContaining({ demand: 20, promo: 25, markdown: 30, inbound: 40, lead: 3, safety: 4 }),
    ));
    await waitFor(() => expect(document.querySelector(".demand-kpi-value")).not.toHaveTextContent(CHAIN_FORECAST));

    // Re-running the same draft is idempotent and sends the same normalized
    // six-lever configuration back through the gateway.
    const firstRunLevers = { ...mocks.runScenario.mock.calls.at(-1)[1] };
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(mocks.runScenario).toHaveBeenCalledTimes(2));
    expect(mocks.runScenario.mock.calls.at(-1)[1]).toEqual(firstRunLevers);

    const saveButton = screen.getByRole("button", { name: "Save" });
    await waitFor(() => expect(saveButton).toBeEnabled());
    fireEvent.click(saveButton);
    expect(await screen.findByText("S1")).toBeInTheDocument();
    expect(loadButton).toBeEnabled();
    expect(screen.getByText("demand 20% · promo 25% · markdown 30% · inbound 40% · lead 3d · safety 4d")).toBeInTheDocument();
    expect({ ...window.localStorage }).toEqual(storageBeforeSave);

    fireEvent.change(demand, { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(mocks.runScenario).toHaveBeenLastCalledWith(
      expect.any(Object),
      expect.objectContaining({ demand: 10, promo: 25, markdown: 30, inbound: 40, lead: 3, safety: 4 }),
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
    await waitFor(() => expect(document.querySelector(".demand-kpi-value")).toHaveTextContent(CHAIN_FORECAST));
    Object.keys(savedLeverValues).forEach((name) => {
      expect(screen.getByRole("slider", { name })).toHaveValue("0");
    });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.queryByRole("status", { name: "What-If scenario applied" })).not.toBeInTheDocument();

    // Reset clears the active scenario but leaves the in-memory saved
    // workspace available for an explicit Load.
    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    await waitFor(() => {
      Object.entries(savedLeverValues).forEach(([name, value]) => {
        expect(screen.getByRole("slider", { name })).toHaveValue(String(name === "Demand shift" ? 10 : value));
      });
      expect(mocks.runScenario).toHaveBeenLastCalledWith(
        expect.any(Object),
        expect.objectContaining({ demand: 10, promo: 25, markdown: 30, inbound: 40, lead: 3, safety: 4 }),
      );
    });
  }, 30000);

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
      expect(document.querySelector(".demand-kpi-value")).toHaveTextContent(CHAIN_FORECAST);
    });
    expect(screen.getByRole("slider", { name: "Demand shift" })).toHaveValue("0");
  });

  it("isolates the preview when whole-page driving is off and propagates it when on", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "What-If Simulator" });

    const toggle = screen.getByRole("checkbox", { name: "Levers drive whole page" });
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(
      expect.any(Object),
      expect.objectContaining({ demand: 0 }),
      expect.objectContaining({ driveWholePage: false }),
    ));

    fireEvent.change(screen.getByRole("slider", { name: "Demand shift" }), {
      target: { value: "20" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(mocks.runScenario).toHaveBeenLastCalledWith(
      expect.any(Object),
      expect.objectContaining({ demand: 20 }),
    ));
    expect(toggle).not.toBeChecked();
    expect(document.querySelector(".demand-kpi-value")).toHaveTextContent(CHAIN_FORECAST);

    fireEvent.click(toggle);
    await waitFor(() => expect(mocks.load).toHaveBeenLastCalledWith(
      expect.any(Object),
      expect.objectContaining({ demand: 20 }),
      expect.objectContaining({ driveWholePage: true }),
    ));
    await waitFor(() => expect(document.querySelector(".demand-kpi-value")).not.toHaveTextContent(CHAIN_FORECAST));
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
  }, 30000);

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
  }, 30000);

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

  it("renders best actions from real counts while every control stays disabled", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "Suggested Best Action" });

    expect(screen.getByText("Cover the reorder zone")).toBeInTheDocument();
    // 302 below ROP and 355 trending, both counted from the workbook rather
    // than written into the copy. 302 is what this workbook arrives at twice
    // over: counting `position < rop` against ENGINE's own stored ROP column,
    // and summing A1's per-vertical stockout_risk_skus (46+31+39+42+35+32+40
    // +37). They agree because ENGINE's ROP is built on sku_master.lead_d.
    // Feeding f05-rop the designated Trade Agreement lead instead lengthens
    // every ROP and yields 438 -- a defensible figure, but one this workbook
    // never computes, so it does not belong in an assertion about it.
    expect(screen.getByText(/302 SKUs sit below their reorder point/)).toBeInTheDocument();
    expect(screen.getByText(/355 SKUs are trending above baseline/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send to Replenishment" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Flag to Inventory Risk" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Preview forecast basket" }));
    expect(screen.getByRole("button", { name: "Generate forecast basket" })).toBeDisabled();
  });
});
