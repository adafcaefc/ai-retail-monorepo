import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import { ALL } from "../data/contract.js";
import { AtRiskByCategoryChart, AtRiskByVerticalChart } from "./PricingCharts.jsx";

// Mirrors demand_forecasting/components/DemandDimensionPanels.test.jsx: the
// bar's own onClick is real code, but Recharts bars are hard to click
// reliably in jsdom, so the filter-shortcut pill row is the tested affordance.
vi.mock("recharts", () => {
  const Empty = () => null;
  return {
    Bar: Empty,
    BarChart: ({ children }) => <div>{children}</div>,
    CartesianGrid: Empty,
    Cell: Empty,
    Legend: Empty,
    Line: Empty,
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
    Tooltip: Empty,
    XAxis: Empty,
    YAxis: Empty,
  };
});

beforeEach(() => {
  window.localStorage.clear();
});

function renderWithLanguage(ui) {
  return render(<LanguageProvider>{ui}</LanguageProvider>);
}

const categoryRows = [
  { category_id: "GRC-C01", label: "Fruit", value: 100 },
  { category_id: "GRC-C02", label: "Vegetable", value: 80 },
];

const verticalRows = [
  { vertical_id: "GRC", label: "Grocery Retail", at_risk_value: 100, recoverable_value: 20 },
  { vertical_id: "GMR", label: "General Merchandise", at_risk_value: 80, recoverable_value: 10 },
];

describe("AtRiskByCategoryChart — click to filter", () => {
  it("hides the reset button when nothing is selected", () => {
    renderWithLanguage(<AtRiskByCategoryChart rows={categoryRows} selected={ALL} onSelect={vi.fn()} />);
    expect(screen.queryByText("Back to all categories")).not.toBeInTheDocument();
  });

  it("shows the reset button once a category is selected, and resets on click", () => {
    const onSelect = vi.fn();
    renderWithLanguage(<AtRiskByCategoryChart rows={categoryRows} selected="GRC-C01" onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Back to all categories"));
    expect(onSelect).toHaveBeenCalledWith(ALL);
  });

  it("renders a filter-shortcut pill per row, calling onSelect with the category id", () => {
    const onSelect = vi.fn();
    renderWithLanguage(<AtRiskByCategoryChart rows={categoryRows} selected={ALL} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Vegetable" }));
    expect(onSelect).toHaveBeenCalledWith("GRC-C02");
  });
});

describe("AtRiskByVerticalChart — click to filter", () => {
  it("hides the reset button when nothing is selected", () => {
    renderWithLanguage(<AtRiskByVerticalChart rows={verticalRows} selected={ALL} onSelect={vi.fn()} />);
    expect(screen.queryByText("Back to all verticals")).not.toBeInTheDocument();
  });

  it("shows the reset button once a vertical is selected, and resets on click", () => {
    const onSelect = vi.fn();
    renderWithLanguage(<AtRiskByVerticalChart rows={verticalRows} selected="GRC" onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Back to all verticals"));
    expect(onSelect).toHaveBeenCalledWith(ALL);
  });

  it("renders a filter-shortcut pill per row, calling onSelect with the vertical id", () => {
    const onSelect = vi.fn();
    renderWithLanguage(<AtRiskByVerticalChart rows={verticalRows} selected={ALL} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "General Merchandise" }));
    expect(onSelect).toHaveBeenCalledWith("GMR");
  });
});
