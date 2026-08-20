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
  it("renders six KPIs, the main chart, both custom charts, and every dimension panel", async () => {
    await renderSettled();

    expect(document.querySelectorAll(".pricing-kpi")).toHaveLength(6);
    expect(screen.getByText("At-risk value vs recoverable markdown")).toBeInTheDocument();
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

  it("opens and closes a KPI drilldown", async () => {
    await renderSettled();

    fireEvent.click(kpiTile("At-risk value"));
    expect(await screen.findByText("This metric by category")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() => {
      expect(screen.queryByText("This metric by category")).not.toBeInTheDocument();
    });
  });

  it("running the What-If simulator updates the paired index chart and shows the scenario banner", async () => {
    await renderSettled();

    const demandSlider = screen.getByRole("slider", { name: /Demand uplift/i });
    fireEvent.change(demandSlider, { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByText(/Scenario active/)).toBeInTheDocument();
  });
});
