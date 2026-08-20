import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import ForecastOverviewPanel from "./ForecastOverviewPanel.jsx";
import { buildDemandChartSeries } from "../data/chartSeries.js";

vi.mock("./ForecastLineChart.jsx", () => ({
  default: () => <div data-testid="forecast-line-chart" />,
}));

function source() {
  return {
    source: "synthetic.demand_store_sku_104w",
    ...Object.fromEntries(
      Array.from({ length: 52 }, (_, index) => [`actual_w${52 - index}`, 10]),
    ),
    ...Object.fromEntries(
      Array.from({ length: 52 }, (_, index) => [`forecast_w${index + 1}`, 20]),
    ),
  };
}

function renderPanel(horizonWeeks) {
  const forecast = buildDemandChartSeries(source(), {
    grain: "weekly",
    horizonWeeks,
  });
  return render(
    <LanguageProvider>
      <ForecastOverviewPanel
        forecast={forecast}
        grains={["daily", "weekly", "monthly", "quarterly", "yearly"]}
        onGrainChange={vi.fn()}
      />
    </LanguageProvider>,
  );
}

describe("ForecastOverviewPanel 104W controls", () => {
  it("shows the SQL-backed subtitle and enables the supported grains", () => {
    renderPanel(8);

    expect(screen.getByText("Based on current limited 52-week synthetic demand dataset"))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Daily" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Weekly" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Monthly" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Quarterly" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Yearly" })).toBeEnabled();
  });

  it.each([4, 8, 12, 16])("enables Quarterly and Yearly at the %dw Horizon", (horizon) => {
    renderPanel(horizon);
    expect(screen.getByRole("button", { name: "Quarterly" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Yearly" })).toBeEnabled();
  });
});
