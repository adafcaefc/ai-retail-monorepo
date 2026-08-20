import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import ForecastLineChart from "./ForecastLineChart.jsx";

vi.mock("recharts", () => ({
  Area: () => null,
  CartesianGrid: () => null,
  ComposedChart: ({ children, data }) => (
    <svg data-testid="composed-chart" data-points={JSON.stringify(data)}>{children}</svg>
  ),
  Line: ({ dataKey, strokeDasharray }) => (
    <output
      data-testid={`line-${dataKey}`}
      data-dash={strokeDasharray || ""}
    />
  ),
  ReferenceLine: ({ x, label, strokeDasharray }) => (
    <output
      data-testid="forecast-divider"
      data-x={x}
      data-label={label?.value}
      data-dash={strokeDasharray}
      data-dy={label?.dy}
    />
  ),
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  Tooltip: () => null,
  XAxis: ({ dataKey, padding }) => (
    <output
      data-testid="x-axis"
      data-key={dataKey}
      data-padding-left={padding?.left ?? ""}
      data-padding-right={padding?.right ?? ""}
    />
  ),
  YAxis: () => null,
  usePlotArea: () => ({ x: 0, y: 0, width: 100, height: 100 }),
  useXAxisScale: () => (value) => (value === "Y-1" ? 32 : 68),
  useYAxisScale: () => (value) => (value === 100 ? 50 : 40),
}));

const points = [
  { key: "W-4", label: "W-4", actual: 80, forecast: null, confidence_low: null, confidence_high: null },
  { key: "W-3", label: "W-3", actual: 90, forecast: null, confidence_low: null, confidence_high: null },
  { key: "W-2", label: "W-2", actual: 100, forecast: null, confidence_low: null, confidence_high: null },
  { key: "W-1", label: "W-1", actual: 110, forecast: null, confidence_low: null, confidence_high: null },
  { key: "W+1", label: "W+1", actual: null, forecast: 120, confidence_low: 100, confidence_high: 140 },
  { key: "W+2", label: "W+2", actual: null, forecast: 130, confidence_low: 105, confidence_high: 155 },
];

const yearlyPoints = [
  { key: "Y-1", label: "Y-1", actual: 100, forecast: null, confidence_low: null, confidence_high: null },
  { key: "Y+1", label: "Y+1", actual: null, forecast: 200, confidence_low: null, confidence_high: null },
];

function renderChart(includeConfidence = false) {
  return render(
    <LanguageProvider>
      <ForecastLineChart
        points={points}
        ariaLabel="Demand forecast chart"
        compact={includeConfidence}
        includeConfidence={includeConfidence}
      />
    </LanguageProvider>,
  );
}

function renderYearlyChart() {
  return render(
    <LanguageProvider>
      <ForecastLineChart
        points={yearlyPoints}
        ariaLabel="Yearly demand forecast chart"
      />
    </LanguageProvider>,
  );
}

describe("Demand Forecasting line-chart transition", () => {
  it.each([false, true])("connects both chart variants without creating W0", (includeConfidence) => {
    renderChart(includeConfidence);

    const chartPoints = JSON.parse(screen.getByTestId("composed-chart").dataset.points);
    expect(chartPoints.map((point) => point.label)).not.toContain("W0");
    expect(chartPoints.find((point) => point.key === "W-1").forecast_transition).toBe(110);
    expect(chartPoints.find((point) => point.key === "W+1").forecast_transition).toBe(120);
    expect(chartPoints.filter((point) => point.forecast_transition != null)).toHaveLength(2);

    expect(screen.getByTestId("line-actual")).toBeInTheDocument();
    expect(screen.getByTestId("line-forecast")).toHaveAttribute("data-dash", "6 3");
    expect(screen.getByTestId("line-forecast_transition")).toHaveAttribute("data-dash", "2 3");
  });

  it("renders the forecast divider and readable transition annotation at W+1", () => {
    renderChart(true);

    const divider = screen.getByTestId("forecast-divider");
    expect(divider).toHaveAttribute("data-x", "W+1");
    expect(divider).toHaveAttribute("data-label", "Forecast starts");
    expect(divider).toHaveAttribute("data-dash", "4 4");
    expect(divider).toHaveAttribute("data-dy", "-4");
  });

  it("adds Yearly styling stubs without adding data points or ticks", () => {
    renderYearlyChart();

    const chartPoints = JSON.parse(screen.getByTestId("composed-chart").dataset.points);
    expect(chartPoints.map((point) => point.label)).toEqual(["Y-1", "Y+1"]);
    expect(chartPoints).toHaveLength(2);
    expect(screen.getByTestId("x-axis")).toHaveAttribute("data-key", "label");
    expect(screen.getByTestId("x-axis")).toHaveAttribute("data-padding-left", "32");
    expect(screen.getByTestId("x-axis")).toHaveAttribute("data-padding-right", "32");
    expect(screen.getByTestId("forecast-divider")).toHaveAttribute("data-x", "Y+1");

    const actualStub = screen.getByTestId("yearly-actual-stub");
    const forecastStub = screen.getByTestId("yearly-forecast-stub");
    expect(Number(actualStub.getAttribute("x1"))).toBeGreaterThan(0);
    expect(Number(actualStub.getAttribute("x2"))).toBeLessThan(100);
    expect(Number(forecastStub.getAttribute("x1"))).toBeGreaterThan(0);
    expect(Number(forecastStub.getAttribute("x2"))).toBeLessThan(100);
    expect(actualStub.parentElement).toHaveAttribute("clip-path", "none");

    expect(actualStub).toHaveAttribute(
      "stroke",
      "var(--demand-actual)",
    );
    expect(actualStub).not.toHaveAttribute("stroke-dasharray");
    expect(forecastStub).toHaveAttribute(
      "stroke",
      "var(--demand-forecast)",
    );
    expect(forecastStub).toHaveAttribute("stroke-dasharray", "6 3");
  });
});
