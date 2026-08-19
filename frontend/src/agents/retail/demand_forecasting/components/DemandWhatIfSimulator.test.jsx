import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("recharts", () => ({
  Bar: () => null,
  BarChart: ({ children, data }) => (
    <div data-testid="comparison-chart" data-chart-data={JSON.stringify(data)}>{children}</div>
  ),
  CartesianGrid: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: ({ domain }) => <output data-testid="comparison-y-axis" data-domain={JSON.stringify(domain)} />,
}));

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import DemandWhatIfSimulator from "./DemandWhatIfSimulator.jsx";
import {
  DEFAULT_DEMAND_LEVERS,
  DEMAND_LEVER_DEFINITIONS,
} from "../data/contract.js";

function simulation(scenarioOverrides = {}) {
  return {
    levers: DEMAND_LEVER_DEFINITIONS,
    baseline: {
      forecast_next_7d: 1000,
      stockout_risk_skus: 100,
      forecast_accuracy_pct: 100,
      predicted_to_trend: 100,
    },
    scenario: {
      forecast_next_7d: 1000,
      stockout_risk_skus: 100,
      forecast_accuracy_pct: 100,
      predicted_to_trend: 100,
      ...scenarioOverrides,
    },
  };
}

function renderSimulator(currentSimulation) {
  return render(
    <LanguageProvider>
      <DemandWhatIfSimulator
        simulation={currentSimulation}
        draftLevers={{ ...DEFAULT_DEMAND_LEVERS }}
        onLeverChange={vi.fn()}
        onRun={vi.fn()}
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onReset={vi.fn()}
        driveWholePage
        onDriveWholePageChange={vi.fn()}
        savedCount={0}
        busy={false}
        canSave={false}
      />
    </LanguageProvider>,
  );
}

function chartRows() {
  return JSON.parse(screen.getByTestId("comparison-chart").dataset.chartData);
}

describe("Demand What-If chart integration", () => {
  it("keeps KPI cards and normalized chart values consistent", () => {
    const { rerender } = renderSimulator(simulation({
      forecast_next_7d: 1100,
      stockout_risk_skus: 80,
    }));

    const forecastCard = screen.getByText("Forecast 7d").closest("article");
    expect(forecastCard).toHaveTextContent("1,100");
    expect(forecastCard).toHaveTextContent("Baseline: 1,000");
    const forecastRow = chartRows().find((row) => row.id === "forecast_next_7d");
    expect(forecastRow.baseline).toBe(100);
    expect(forecastRow.scenario).toBeCloseTo(110, 12);
    expect(chartRows().find((row) => row.id === "stockout_risk_skus")).toMatchObject({
      baseline: 100,
      scenario: 80,
    });
    expect(JSON.parse(screen.getByTestId("comparison-y-axis").dataset.domain)).toEqual([70, 120]);

    rerender(
      <LanguageProvider>
        <DemandWhatIfSimulator
          simulation={simulation({ forecast_next_7d: 900, stockout_risk_skus: 120 })}
          draftLevers={{ ...DEFAULT_DEMAND_LEVERS }}
          onLeverChange={vi.fn()}
          onRun={vi.fn()}
          onSave={vi.fn()}
          onLoad={vi.fn()}
          onReset={vi.fn()}
          driveWholePage
          onDriveWholePageChange={vi.fn()}
          savedCount={0}
          busy={false}
          canSave={false}
        />
      </LanguageProvider>,
    );

    expect(screen.getByText("900")).toBeInTheDocument();
    expect(chartRows().find((row) => row.id === "forecast_next_7d")).toMatchObject({
      baseline: 100,
      scenario: 90,
    });
    expect(JSON.parse(screen.getByTestId("comparison-y-axis").dataset.domain)).toEqual([80, 130]);
  });

  it("renders a safe axis and missing scenario bar when a baseline is zero", () => {
    renderSimulator({
      levers: DEMAND_LEVER_DEFINITIONS,
      baseline: {
        forecast_next_7d: 0,
        stockout_risk_skus: 0,
        forecast_accuracy_pct: 100,
        predicted_to_trend: 100,
      },
      scenario: {
        forecast_next_7d: 0,
        stockout_risk_skus: 0,
        forecast_accuracy_pct: 100,
        predicted_to_trend: 100,
      },
    });

    expect(chartRows().filter((row) => row.scenario === null)).toHaveLength(2);
    expect(JSON.parse(screen.getByTestId("comparison-y-axis").dataset.domain)).toEqual([90, 110]);
  });
});
