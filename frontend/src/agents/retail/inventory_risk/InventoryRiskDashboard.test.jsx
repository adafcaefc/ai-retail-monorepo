import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import InventoryRiskDashboard from "./InventoryRiskDashboard.jsx";
import fixture from "./data/fixture.json";

/*
 * No mock of the data gateway. The fixture provider is pure and synchronous,
 * so the dashboard renders against the same numbers a reader would see — which
 * makes these assertions a check on the whole chain, not on a stub.
 *
 * Recharts needs a real box to lay out inside; jsdom reports zero for every
 * element, so ResponsiveContainer would render nothing and the SVG assertions
 * would be vacuous. Pinning the container size is what makes the charts real
 * here.
 */
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
      <InventoryRiskDashboard />
    </LanguageProvider>,
  );
}

/*
 * The skeleton and the loaded board share `data-testid`, deliberately — it is
 * the same board in two states. So waiting on the test id can hand back the
 * skeleton, and an interaction fired against it lands on controls that are
 * about to be replaced. Wait for content only the loaded board renders.
 */
async function renderSettled() {
  const result = renderDashboard();
  await screen.findByText("Inventory risk register");
  return result;
}

/*
 * KPI labels are not unique on the board and should not be: the What-If
 * simulator reports the same four measures for its scenario, and calling them
 * something else there would be a worse answer than a scoped query here.
 */
function kpiTile(label) {
  const grid = document.querySelector(".risk-kpi-grid");
  return within(grid).getByText(label).closest(".risk-kpi");
}

const grocery = fixture.reference_by_vertical.find(
  (row) => row.legal_entity_id === "GRC",
);

describe("InventoryRiskDashboard", () => {
  it("renders six KPIs, both value panels, the dimension row, and the register", async () => {
    renderDashboard();

    await screen.findByTestId("inventory-risk-dashboard");

    expect(document.querySelectorAll(".risk-kpi")).toHaveLength(6);
    expect(screen.getByText("At-risk value by state")).toBeInTheDocument();
    expect(screen.getByText("Inventory value by category")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by category")).toBeInTheDocument();
    expect(screen.getByText("Stockout-risk by store")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by cluster")).toBeInTheDocument();
    expect(screen.getByText("At-risk value by legal entity")).toBeInTheDocument();
    expect(screen.getByText("Expiry timeline")).toBeInTheDocument();
    expect(screen.getByText("Inventory risk register")).toBeInTheDocument();
  });

  it("shows the whole chain's stockout count, matching the workbook total", async () => {
    renderDashboard();

    const expected = fixture.reference_by_vertical.reduce(
      (running, row) => running + row.stockout_risk_skus,
      0,
    );
    const tile = (await screen.findAllByText("Stockout-risk SKUs"))[0];

    expect(
      within(tile.closest(".risk-kpi")).getByText(String(expected)),
    ).toBeInTheDocument();
  });

  it("labels the source rather than presenting workbook figures as live", async () => {
    renderDashboard();

    expect(await screen.findByText(/Workbook data/)).toBeInTheDocument();
    expect(screen.getByText(/not a live ERP position/)).toBeInTheDocument();
  });

  it("carries the gross-versus-chain-net caveat on the board", async () => {
    renderDashboard();

    expect(
      await screen.findByText(/Store and cluster breakdowns are gross/),
    ).toBeInTheDocument();
  });

  it("scopes to one vertical and reports that vertical's workbook numbers", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Legal entity"), {
      target: { value: "GRC" },
    });

    await waitFor(() => {
      const tile = screen
        .getAllByText("Stockout-risk SKUs")[0]
        .closest(".risk-kpi");
      expect(
        within(tile).getByText(String(grocery.stockout_risk_skus)),
      ).toBeInTheDocument();
    });

    // The scope chip names the active vertical, and clearing restores the
    // chain. Scoped to the summary row: "Grocery" also appears in the select
    // options and on the legal-entity chart.
    const summary = document.querySelector(".risk-scope-summary");
    expect(within(summary).getByText(/Grocery/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));

    await waitFor(() => {
      expect(screen.getByText("All retail inventory")).toBeInTheDocument();
    });
  });

  it("filters the register by state", async () => {
    await renderSettled();

    fireEvent.click(screen.getByRole("button", { name: "Stockout" }));

    await waitFor(() => {
      const rows = document.querySelectorAll(".risk-row");
      expect(rows.length).toBeGreaterThan(0);
      for (const row of rows) {
        expect(row.className).toContain("risk-row--stockout");
      }
    });
  });

  it("submits a SKU search and narrows to the single matching row", async () => {
    await renderSettled();

    // jsdom does not dispatch submit from a submit-button click, so submit the
    // form directly — the same approach the Demand dashboard's test uses.
    const input = screen.getByRole("searchbox", { name: "SKU search" });
    fireEvent.change(input, { target: { value: "GRC-001" } });
    fireEvent.submit(input.closest("form"));

    await waitFor(() => {
      expect(document.querySelectorAll(".risk-row")).toHaveLength(1);
    });
    // The term also appears in the search box and the scope chip, so assert
    // against the register row itself. The code shares a line with the
    // category, so match the meta line rather than a bare text node.
    const row = document.querySelector(".risk-row");
    expect(row.querySelector(".risk-sku-meta").textContent).toMatch(/^GRC-001 · /);
  });

  it("disables the store filter while the per-store dataset is unavailable", async () => {
    await renderSettled();

    expect(screen.getByLabelText("Store")).toBeDisabled();
  });

  it("pages the register rather than rendering all 800 rows at once", async () => {
    await renderSettled();

    expect(document.querySelectorAll(".risk-row")).toHaveLength(50);
    expect(screen.getByText(/Page 1 \/ 16/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(screen.getByText(/Page 2 \/ 16/)).toBeInTheDocument();
    });
  });

  it("orders the register worst-state first", async () => {
    await renderSettled();

    const first = document.querySelector(".risk-row");
    expect(first.className).toContain("risk-row--stockout");
  });

  it("prices overstock and expiry underneath their counts", async () => {
    await renderSettled();

    const overstock = kpiTile("Overstock SKUs");
    const expiry = kpiTile("Expiry-risk units");

    // A count alone cannot be weighed against anything; the money line is what
    // makes the tile actionable.
    expect(within(overstock).getByText(/excess/)).toBeInTheDocument();
    expect(within(overstock).getByText(/Rp/)).toBeInTheDocument();
    expect(within(expiry).getByText(/write-off risk/)).toBeInTheDocument();
    expect(within(expiry).getByText(/Rp/)).toBeInTheDocument();
  });

  it("shows the days-of-supply target band", async () => {
    await renderSettled();

    const tile = kpiTile("Avg days of supply");
    expect(within(tile).getByText(/target 7–21d/)).toBeInTheDocument();
  });

  it("carries each KPI's formula on the tile itself", async () => {
    await renderSettled();

    const tile = kpiTile("Stockout-risk SKUs");
    expect(tile).toHaveAttribute("title", expect.stringContaining("Position < ROP"));
  });

  it("drills to the reorder zone from the stockout tile, and back again", async () => {
    await renderSettled();

    const tile = kpiTile("Stockout-risk SKUs");
    expect(tile.tagName).toBe("BUTTON");

    fireEvent.click(tile);
    await waitFor(() => {
      const rows = document.querySelectorAll(".risk-row");
      expect(rows.length).toBeGreaterThan(0);
      for (const row of rows) {
        expect(row.className).toContain("risk-row--stockout");
      }
    });

    // Clicking again clears it rather than trapping the reader in the filter.
    fireEvent.click(kpiTile("Stockout-risk SKUs"));
    await waitFor(() => {
      expect(screen.getByText("All retail inventory")).toBeInTheDocument();
    });
  });

  it("routes non-healthy SKUs to the agent that owns the fix", async () => {
    await renderSettled();

    const panel = screen
      .getByText("Suggested best action")
      .closest(".risk-panel");

    expect(within(panel).getByText("→ 3 Replenish")).toBeInTheDocument();
    expect(within(panel).getByText("→ 5 Markdown")).toBeInTheDocument();
    expect(panel.querySelectorAll(".risk-action")).toHaveLength(2);
  });

  it("puts the product name ahead of its code in the register", async () => {
    await renderSettled();

    const row = document.querySelector(".risk-row");
    const primary = row.querySelector(".risk-sku-name-primary");
    const meta = row.querySelector(".risk-sku-meta");

    expect(primary.textContent).not.toMatch(/^[A-Z]{3}-\d{3}$/);
    expect(meta.textContent).toMatch(/^[A-Z]{3}-\d{3} · /);
  });

  it("projects stock forward and prints the strip under the chart", async () => {
    await renderSettled();

    const panel = screen
      .getByText("Projected on-hand vs demand")
      .closest(".risk-panel");

    expect(within(panel).getByText("Position")).toBeInTheDocument();
    expect(within(panel).getByText("Inbound")).toBeInTheDocument();
    expect(within(panel).getByText("At risk")).toBeInTheDocument();
    // The panel must say there is no history rather than draw one.
    expect(within(panel).getByText(/nothing to plot before day 0/)).toBeInTheDocument();
  });

  it("offers all six levers and disables the one the workbook cannot model", async () => {
    await renderSettled();

    expect(screen.getByLabelText("Demand surge")).toBeEnabled();
    expect(screen.getByLabelText("Inbound cover")).toBeEnabled();
    // A2 spec 8a lists a markdown lever; formula.json has no markdown term.
    expect(screen.getByLabelText("Markdown clear")).toBeDisabled();
  });

  it("keeps the board on the workbook until Run is pressed", async () => {
    await renderSettled();

    const before = kpiTile("Stockout-risk SKUs").textContent;
    fireEvent.change(screen.getByLabelText("Demand surge"), {
      target: { value: "40" },
    });

    // Dragging a slider re-runs 800 SKUs; doing that per pixel would make the
    // control fight the user, so nothing moves until Run.
    expect(kpiTile("Stockout-risk SKUs").textContent).toBe(before);
    expect(screen.queryByText(/simulated figures/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(kpiTile("Stockout-risk SKUs").textContent).not.toBe(before);
    });
  });

  it("says the board is showing a scenario, and takes it back", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Demand surge"), {
      target: { value: "40" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(
        screen.getByText("These are simulated figures, not the workbook position."),
      ).toBeInTheDocument();
    });
    // The banner names the levers, so a screenshot carries its own context.
    expect(screen.getByText(/Demand surge \+40%/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back to workbook" }));

    await waitFor(() => {
      expect(screen.queryByText(/simulated figures/)).not.toBeInTheDocument();
    });
  });

  it("saves a scenario and overlays it against the baseline", async () => {
    await renderSettled();

    // Nothing to save until a lever has actually moved.
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Demand surge"), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const panel = await screen.findByLabelText("Compare scenarios", {
      selector: "section",
    });
    await waitFor(() => {
      expect(panel.querySelectorAll(".risk-scenario-list li")).toHaveLength(1);
    });
    expect(within(panel).getByText(/1 \/ 4/)).toBeInTheDocument();

    fireEvent.click(within(panel).getByRole("button", { name: /Remove/ }));
    await waitFor(() => {
      expect(panel.querySelectorAll(".risk-scenario-list li")).toHaveLength(0);
    });
  });

  it("explains each register figure where the figure is", async () => {
    await renderSettled();

    const cells = document.querySelector(".risk-row").querySelectorAll("td.num");
    const titles = [...cells].map((cell) => cell.getAttribute("title"));

    expect(titles).toContain("Position = On-hand + Open PO");
    expect(titles).toContain("ROP = ADS × (Lead + Safety)");
    expect(titles).toContain("DoS = Position ÷ ADS");
  });
});
