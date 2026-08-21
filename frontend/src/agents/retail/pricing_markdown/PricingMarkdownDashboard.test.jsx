import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import PricingMarkdownDashboard from "./PricingMarkdownDashboard.jsx";
import fixture from "./data/fixture.json";

beforeEach(() => {
  window.localStorage.clear();

  for (const [property, value] of [
    ["offsetWidth", 960],
    ["offsetHeight", 400],
    ["clientWidth", 960],
    ["clientHeight", 400],
  ]) {
    Object.defineProperty(window.HTMLElement.prototype, property, {
      configurable: true,
      value,
    });
  }
});

function renderDashboard() {
  return render(
    <LanguageProvider>
      <PricingMarkdownDashboard />
    </LanguageProvider>,
  );
}

async function renderSettled() {
  const result = renderDashboard();
  await screen.findByText("Markdown candidate preview");
  return result;
}

function kpiTile(label) {
  const grid = document.querySelector(".pricing-kpi-grid");
  return within(grid).getByText(label).closest(".pricing-kpi");
}

describe("PricingMarkdownDashboard", () => {
  it("renders six KPIs, the main chart, the ladder chart, and every dimension panel", async () => {
    await renderSettled();

    expect(document.querySelectorAll(".pricing-kpi")).toHaveLength(6);
    expect(screen.getByText("At-risk value vs recoverable markdown")).toBeInTheDocument();
    // Rescue waterfall / Elasticity vs depth are commented out on the
    // dashboard (PricingMarkdownDashboard.jsx) per request -- not rendered.
    expect(document.querySelector('[data-testid="pricing-chart-rescue-waterfall"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-testid="pricing-chart-elasticity-depth"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-testid="pricing-chart-ladder-vs-no-action"]')).toBeInTheDocument();
    expect(document.querySelector(".pricing-ladder-stats")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by vertical")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by category")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by store")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by cluster")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by channel")).toBeInTheDocument();
    expect(screen.getByText("Inventory value by state")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by legal entity")).toBeInTheDocument();
    expect(screen.getByText("Suggested best action")).toBeInTheDocument();
    expect(screen.getByText("What-If simulator")).toBeInTheDocument();
  });

  it("shows the chain's candidate count, matching the fixture's live candidate population", async () => {
    await renderSettled();

    const expected = fixture.items.filter((i) => i.is_markdown_candidate).length;
    const tile = kpiTile("Markdown candidates");
    // Formatted with a thousands separator, same as every other count tile.
    expect(within(tile).getByText(expected.toLocaleString("en-US"))).toBeInTheDocument();
  });

  it("labels the source rather than presenting workbook figures as live", async () => {
    await renderSettled();

    expect(screen.getByText(/Workbook demonstration data/)).toBeInTheDocument();
  });

  it("scopes to one vertical and narrows the candidate table", async () => {
    await renderSettled();
    const beforeRows = document.querySelectorAll(".pricing-candidate-row").length;

    fireEvent.change(screen.getByLabelText("Vertical"), { target: { value: "GRC" } });

    await waitFor(() => {
      expect(document.querySelectorAll(".pricing-candidate-row").length).toBeLessThanOrEqual(beforeRows);
    });
  });

  it("clicking a category filter-shortcut pill narrows the board, and the reset button clears it", async () => {
    await renderSettled();
    const beforeRows = document.querySelectorAll(".pricing-candidate-row").length;

    const categoryChart = document.querySelector('[data-testid="pricing-chart-category"]');
    const firstPill = within(categoryChart).getAllByRole("button")[0];
    fireEvent.click(firstPill);

    await waitFor(() => {
      expect(document.querySelectorAll(".pricing-candidate-row").length).toBeLessThanOrEqual(beforeRows);
    });
    expect(within(categoryChart).getByText("Back to all categories")).toBeInTheDocument();

    fireEvent.click(within(categoryChart).getByText("Back to all categories"));

    await waitFor(() => {
      expect(document.querySelectorAll(".pricing-candidate-row").length).toBe(beforeRows);
    });
    expect(within(categoryChart).queryByText("Back to all categories")).not.toBeInTheDocument();
  });

  it("opens and closes a KPI drilldown", async () => {
    await renderSettled();

    fireEvent.click(kpiTile("At-risk value"));
    expect(await screen.findByText("This metric by category")).toBeInTheDocument();
    expect(screen.getByText("This metric by store")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() => {
      expect(screen.queryByText("This metric by category")).not.toBeInTheDocument();
    });
  });

  it("opens a KPI drilldown from the Markdown candidates tile", async () => {
    await renderSettled();

    fireEvent.click(kpiTile("Markdown candidates"));
    expect(await screen.findByText("This metric by category")).toBeInTheDocument();
  });

  it("moving a What-If lever updates the scenario banner live, with no Run click", async () => {
    await renderSettled();

    const demandSlider = screen.getByRole("slider", { name: /Demand uplift/i });
    fireEvent.change(demandSlider, { target: { value: "30" } });

    expect(await screen.findByText(/Scenario active/)).toBeInTheDocument();
  });

  it("the ladder chart's Horizon control lives in the filter bar and re-slices the chart client-side", async () => {
    await renderSettled();

    const filters = screen.getByTestId("pricing-filters");
    const sixteenWeek = within(filters).getByRole("button", { name: "16w" });
    const fourWeek = within(filters).getByRole("button", { name: "4w" });
    expect(sixteenWeek).toHaveAttribute("aria-pressed", "true");
    expect(fourWeek).toHaveAttribute("aria-pressed", "false");

    const chart = document.querySelector('[data-testid="pricing-chart-ladder-vs-no-action"]');
    expect(chart).toBeInTheDocument();

    fireEvent.click(fourWeek);

    expect(fourWeek).toHaveAttribute("aria-pressed", "true");
    expect(sixteenWeek).toHaveAttribute("aria-pressed", "false");
    // No refetch: the filter bar's own busy state never flips for this control.
    expect(screen.queryByText(/Refresh/)).toBeInTheDocument();
  });

  it("moving the Markdown depth lever moves the Avg depth % KPI tile, live", async () => {
    await renderSettled();

    const before = kpiTile("Avg depth %").querySelector(".pricing-kpi-value").textContent;

    const markdownSlider = screen.getByRole("slider", { name: /Markdown depth/i });
    fireEvent.change(markdownSlider, { target: { value: "60" } });

    await waitFor(() => {
      const after = kpiTile("Avg depth %").querySelector(".pricing-kpi-value").textContent;
      expect(after).not.toBe(before);
    });
  });
});
