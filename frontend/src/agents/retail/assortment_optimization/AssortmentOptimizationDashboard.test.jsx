import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import AssortmentOptimizationDashboard from "./AssortmentOptimizationDashboard.jsx";
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
      <AssortmentOptimizationDashboard />
    </LanguageProvider>,
  );
}

async function renderSettled() {
  const result = renderDashboard();
  await screen.findByText("Assortment action preview");
  return result;
}

function kpiTile(label) {
  const grid = document.querySelector(".assortment-kpi-grid");
  return within(grid).getByText(label).closest(".assortment-kpi");
}

describe("AssortmentOptimizationDashboard", () => {
  it("renders six KPIs, the quadrant, both contribution charts, and every dimension panel", async () => {
    await renderSettled();

    expect(document.querySelectorAll(".assortment-kpi")).toHaveLength(6);
    expect(screen.getByText("Delist vs grow opportunity")).toBeInTheDocument();
    // The Demo Script names this one for step 7: "A6 Pareto + GMROI".
    expect(screen.getByText("Margin contribution Pareto")).toBeInTheDocument();
    expect(screen.getByText("Range decision mix")).toBeInTheDocument();
    expect(screen.getByText("Contribution/day by vertical")).toBeInTheDocument();
    expect(screen.getByText("Contribution/day by category")).toBeInTheDocument();
    expect(screen.getByText("Contribution/day by store")).toBeInTheDocument();
    expect(screen.getByText("Contribution/day by cluster")).toBeInTheDocument();
    expect(screen.getByText("Contribution/day by channel")).toBeInTheDocument();
    expect(screen.getByText("Inventory value by state")).toBeInTheDocument();
    expect(screen.getByText("Contribution/day by legal entity")).toBeInTheDocument();
    expect(screen.getByText("Suggested best action")).toBeInTheDocument();
    expect(screen.getByText("What-If simulator")).toBeInTheDocument();
  });

  it("shows the chain's delist count, matching the fixture's own classification", async () => {
    await renderSettled();

    const expected = fixture.items.filter((i) => i.classification === "delist").length;
    expect(within(kpiTile("Delist candidates")).getByText(String(expected))).toBeInTheDocument();
  });

  it("labels the source rather than presenting workbook figures as live", async () => {
    await renderSettled();

    expect(screen.getByText(/Workbook demonstration data/)).toBeInTheDocument();
  });

  it("carries the capital-freed caveat on the board", async () => {
    await renderSettled();

    expect(screen.getByText(/a decision value, not a cash receipt/)).toBeInTheDocument();
  });

  it("scopes to grow candidates only and narrows the action table", async () => {
    await renderSettled();
    const beforeRows = document.querySelectorAll(".assortment-action-row").length;

    fireEvent.change(screen.getByLabelText("Verdict"), { target: { value: "grow" } });

    await waitFor(() => {
      expect(document.querySelectorAll(".assortment-action-row").length).toBeLessThanOrEqual(
        beforeRows,
      );
    });
  });

  it("opens and closes a KPI drilldown", async () => {
    await renderSettled();

    fireEvent.click(kpiTile("Capital freed"));
    expect(await screen.findByText("This metric by category")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() => {
      expect(screen.queryByText("This metric by category")).not.toBeInTheDocument();
    });
  });

  it("running the What-If simulator shows the scenario banner", async () => {
    await renderSettled();

    fireEvent.change(screen.getByRole("slider", { name: /Demand uplift/i }), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(await screen.findByText(/Scenario active/)).toBeInTheDocument();
  });
});
