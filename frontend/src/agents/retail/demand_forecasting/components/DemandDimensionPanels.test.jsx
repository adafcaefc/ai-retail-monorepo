import { fireEvent, render, within } from "@testing-library/react";
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

function renderPanels(props = {}) {
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
        {...props}
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

describe("Forecast by category back-to-all control", () => {
  it("hides the back button when no category is selected", () => {
    renderPanels({ selectedCategory: "ALL" });
    const categoryPanel = articleByTitle("Forecast by category");
    expect(within(categoryPanel).queryByText("Back to all categories")).not.toBeInTheDocument();
  });

  it("hides the back button when selectedCategory is not provided", () => {
    renderPanels();
    const categoryPanel = articleByTitle("Forecast by category");
    expect(within(categoryPanel).queryByText("Back to all categories")).not.toBeInTheDocument();
  });

  it("shows the back button once a category is selected and resets on click", () => {
    const onCategory = vi.fn();
    renderPanels({ selectedCategory: "Category-3", onCategory });
    const categoryPanel = articleByTitle("Forecast by category");

    const backButton = within(categoryPanel).getByText("Back to all categories");
    fireEvent.click(backButton);

    expect(onCategory).toHaveBeenCalledWith("ALL");
  });
});

describe("Forecast by store back-to-all control", () => {
  it("hides the back button when no store is selected", () => {
    renderPanels({ selectedStore: "ALL" });
    const storePanel = articleByTitle("Forecast by store");
    expect(within(storePanel).queryByText("Back to all stores")).not.toBeInTheDocument();
  });

  it("hides the back button when selectedStore is not provided", () => {
    renderPanels();
    const storePanel = articleByTitle("Forecast by store");
    expect(within(storePanel).queryByText("Back to all stores")).not.toBeInTheDocument();
  });

  it("shows the back button once a store is selected and resets on click", () => {
    const onStore = vi.fn();
    renderPanels({ selectedStore: "Store-3", onStore });
    const storePanel = articleByTitle("Forecast by store");

    const backButton = within(storePanel).getByText("Back to all stores");
    fireEvent.click(backButton);

    expect(onStore).toHaveBeenCalledWith("ALL");
  });
});

describe("By legal entity back-to-all control", () => {
  it("hides the back button when no legal entity is selected", () => {
    renderPanels({ selectedLegalEntity: "ALL" });
    const entityPanel = articleByTitle("By legal entity");
    expect(within(entityPanel).queryByText("Back to all legal entities")).not.toBeInTheDocument();
  });

  it("hides the back button when selectedLegalEntity is not provided", () => {
    renderPanels();
    const entityPanel = articleByTitle("By legal entity");
    expect(within(entityPanel).queryByText("Back to all legal entities")).not.toBeInTheDocument();
  });

  it("shows the back button once a legal entity is selected and resets on click", () => {
    const onLegalEntity = vi.fn();
    renderPanels({ selectedLegalEntity: "GRC", onLegalEntity });
    const entityPanel = articleByTitle("By legal entity");

    const backButton = within(entityPanel).getByText("Back to all legal entities");
    fireEvent.click(backButton);

    expect(onLegalEntity).toHaveBeenCalledWith("ALL");
  });
});

function articleByTitle(title) {
  return [...document.querySelectorAll("article")].find(
    (article) => article.querySelector("h2")?.textContent === title,
  );
}
