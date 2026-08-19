import { render, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../../../LanguageProvider.jsx";
import DemandDimensionPanels from "./DemandDimensionPanels.jsx";

vi.mock("recharts", () => {
  const Empty = () => null;
  return {
    Bar: Empty,
    BarChart: ({ data, children }) => (
      <div data-testid="dimension-bar-chart" data-labels={data.map((row) => row.label).join("|")}>
        {children}
      </div>
    ),
    CartesianGrid: Empty,
    Cell: Empty,
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
    Tooltip: Empty,
    XAxis: Empty,
    YAxis: Empty,
  };
});

function rows(prefix, count = 21) {
  return Array.from({ length: count }, (_unused, index) => ({
    id: `${prefix}-${index + 1}`,
    label: `${prefix} ${index + 1}`,
    forecast_units: count - index,
  }));
}

function renderPanels() {
  return render(
    <LanguageProvider>
      <DemandDimensionPanels
        dimensions={{
          categories: rows("Category"),
          stores: rows("Store"),
          clusters: [],
          seasonality: [],
          legal_entities: [],
          chain_total: 0,
        }}
        onCategory={vi.fn()}
        onStore={vi.fn()}
        onLegalEntity={vi.fn()}
      />
    </LanguageProvider>,
  );
}

describe("Demand dimension top-20 presentation", () => {
  it("uses the same top-20 rows for category/store charts and pills", () => {
    renderPanels();

    const categoryPanel = articleByTitle("Forecast by category");
    const storePanel = articleByTitle("Forecast by store");

    for (const [panel, prefix] of [[categoryPanel, "Category"], [storePanel, "Store"]]) {
      const expectedLabels = Array.from({ length: 20 }, (_unused, index) => `${prefix} ${index + 1}`);
      expect(within(panel).getByTestId("dimension-bar-chart")).toHaveAttribute(
        "data-labels",
        expectedLabels.join("|"),
      );
      expect(within(panel).getAllByRole("button").map((button) => button.textContent))
        .toEqual(expectedLabels);
      expect(within(panel).queryByRole("button", { name: `${prefix} 21` })).not.toBeInTheDocument();
    }
  });
});

function articleByTitle(title) {
  return [...document.querySelectorAll("article")].find(
    (article) => article.querySelector("h2")?.textContent === title,
  );
}
