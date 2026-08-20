import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import DemandKpiGrid from "./DemandKpiGrid.jsx";

function renderGrid(value, comparisonLabel = "Calculated", sparkline = []) {
  return render(
    <LanguageProvider>
      <DemandKpiGrid
        kpis={[
          {
            id: "demand_trend",
            label: "Demand trend",
            value,
            unit: "%",
            comparison_label: comparisonLabel,
            direction: value == null ? "flat" : value >= 0 ? "up" : "down",
            status: value == null ? "neutral" : value >= 0 ? "good" : "warn",
            sparkline,
          },
        ]}
      />
    </LanguageProvider>,
  );
}

function renderAccuracyGrid() {
  return render(
    <LanguageProvider>
      <DemandKpiGrid
        kpis={[
          {
            id: "forecast_accuracy",
            label: "Forecast accuracy",
            value: 92.4,
            unit: "%",
            comparison_label: "Calculated",
            direction: "flat",
            status: "good",
          },
        ]}
      />
    </LanguageProvider>,
  );
}

describe("Demand Trend KPI card", () => {
  it("displays the calculated backend value and source label", () => {
    renderGrid(5.5954);

    expect(screen.getByText("+5.6%")).toBeInTheDocument();
    expect(screen.getByText("Calculated")).toBeInTheDocument();
    expect(screen.queryByText("Workbook constant")).not.toBeInTheDocument();
  });

  it("keeps the existing negative percentage formatting", () => {
    renderGrid(-5.5954);

    expect(screen.getByText("-5.6%")).toBeInTheDocument();
  });

  it("renders the supplied live series with the shared KPI sparkline", () => {
    renderGrid(5.5954, "Calculated", [10, 11, 12, 13, 14, 15, 16, 17]);

    const sparkline = screen.getByRole("img", { name: "Trend" });
    expect(sparkline).toBeInTheDocument();
    const points = sparkline.querySelector("polyline").getAttribute("points").split(" ");
    expect(points).toHaveLength(8);
    expect(points[0]).toBe("0,22");
    expect(points.at(-1)).toBe("100,4");
    expect(points[3]).toContain(",14.285714285714286");
  });

  it("shows unavailable instead of turning a missing aggregate into zero", () => {
    renderGrid(null, "Unavailable");

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });
});

describe("Forecast Accuracy KPI card", () => {
  it("renders the calculated source label without changing the value", () => {
    renderAccuracyGrid();

    expect(screen.getByText("92.4%")).toBeInTheDocument();
    expect(screen.getByText("Calculated")).toBeInTheDocument();
    expect(screen.queryByText("Workbook constant")).not.toBeInTheDocument();
  });
});
