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

/** The What-If panel's own metric strip, not the whole-page KPI grid. */
function simMetric(label) {
  const strip = document.querySelector(".risk-scenario-metrics");
  return within(strip).getByText(label).closest("article");
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

  /*
   * Panel order is the deliverable here, not an incidental of how the JSX was
   * typed: the board is meant to read 1:1 against the A2 mockup (`pgA2()` in
   * the suite HTML). Asserting on document position is what stops a later edit
   * from quietly reshuffling the page back.
   */
  it("stacks its panels in the mockup's order", async () => {
    await renderSettled();

    const board = screen.getByTestId("inventory-risk-dashboard");
    const headings = [...board.querySelectorAll(".risk-panel-head h3")].map(
      (heading) => heading.textContent,
    );

    const at = (title) => headings.indexOf(title);

    // Diagnose first: the projection and the two value panels.
    expect(at("Projected on-hand vs demand")).toBeLessThan(
      at("At-risk value by state"),
    );
    // Then the register, before the dimension breakdowns rather than after.
    expect(at("At-risk value by state")).toBeLessThan(
      at("Inventory risk register"),
    );
    expect(at("Inventory risk register")).toBeLessThan(
      at("At-risk value by category"),
    );
    // Hand off last, once the reader has seen what is being routed.
    expect(at("Suggested best action")).toBe(headings.length - 1);
  });

  /*
   * The mockup's `dimRowHTML('a2')` shape: category|store, cluster|expiry,
   * then legal entity spanning the full width on a row of its own.
   */
  it("lays the dimension charts out two-two-one, with expiry beside cluster", async () => {
    await renderSettled();

    const grid = document.querySelector(".risk-dimension-grid");
    const rows = grid.querySelectorAll(".risk-dimension-row");

    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("At-risk value by category")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Stockout-risk by store")).toBeInTheDocument();
    expect(within(rows[1]).getByText("At-risk value by cluster")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Expiry timeline")).toBeInTheDocument();

    // Legal entity is a direct child of the flex column, so it spans both
    // columns instead of being stranded in a half-width cell.
    const entity = within(grid)
      .getByText("At-risk value by legal entity")
      .closest(".risk-panel");
    expect(entity.parentElement).toBe(grid);
  });

  /*
   * 524 distinct SKUs sit below their reorder point (Stockout + Low states)
   * across the ENGINE_STORE grid -- the same `Position < ROP` predicate
   * Replenishment's "SKUs to reorder" and Demand Forecasting's
   * "Stockout-risk SKUs" tile count. This deliberately does NOT read
   * `reference_by_vertical`, which carries the chain-net A2 summary sheet (345
   * below-ROP SKUs over a netted population) — a benchmark from the other
   * grain, not what this tile counts.
   */
  it("shows the whole grid's stockout-risk count, matching the workbook dropdown", async () => {
    renderDashboard();

    const tile = (await screen.findAllByText("Stockout-risk SKUs"))[0];

    expect(
      within(tile.closest(".risk-kpi")).getByText("524"),
    ).toBeInTheDocument();
  });

  it("carries the rows-versus-SKUs caveat on the board", async () => {
    renderDashboard();

    expect(
      await screen.findByText(/count SKU-per-store rows/),
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
      // Grocery's own ENGINE_STORE rows, not the A2 sheet's chain-net figure.
      expect(within(tile).getByText("78")).toBeInTheDocument();
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

  it("submits a SKU search and narrows to that SKU's rows across its stores", async () => {
    await renderSettled();

    // jsdom does not dispatch submit from a submit-button click, so submit the
    // form directly — the same approach the Demand dashboard's test uses.
    const input = screen.getByRole("searchbox", { name: "SKU search" });
    fireEvent.change(input, { target: { value: "GRC-001" } });
    fireEvent.submit(input.closest("form"));

    // One row per store the SKU is stocked in — 20 of them — not one row.
    // The register pages at 50, so all twenty fit on the first page.
    await waitFor(() => {
      expect(document.querySelectorAll(".risk-row")).toHaveLength(20);
    });
    // The term also appears in the search box and the scope chip, so assert
    // against the register row itself. The code shares a line with the store
    // and category, so match the meta line rather than a bare text node.
    const row = document.querySelector(".risk-row");
    expect(row.querySelector(".risk-sku-meta").textContent).toMatch(/^GRC-001 · /);
  });

  it("scopes the board to one store, showing that store's own position", async () => {
    /*
     * The board ships the 16,000-row grid now, so a store scope is a filter on
     * `store_id` rather than a reconstruction. S001 is a Grocery store
     * carrying 100 SKUs, so the register shrinking is the visible proof the
     * scope reached the rows and not just the chip.
     */
    await renderSettled();

    const select = screen.getByLabelText("Store");
    expect(select).toBeEnabled();

    fireEvent.change(select, { target: { value: "S001" } });

    await waitFor(() => {
      expect(screen.getByLabelText("Store")).toHaveValue("S001");
    });
    // ENGINE_STORE's own tally for S001: 51 SKUs below their reorder point.
    await waitFor(() => {
      const tile = screen
        .getAllByText("Stockout-risk SKUs")[0]
        .closest(".risk-kpi");
      expect(within(tile).getByText("51")).toBeInTheDocument();
    });
  });

  it("pages the register rather than rendering all 16,000 rows at once", async () => {
    await renderSettled();

    expect(document.querySelectorAll(".risk-row")).toHaveLength(50);
    expect(screen.getByText(/Page 1 \/ 320/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(screen.getByText(/Page 2 \/ 320/)).toBeInTheDocument();
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

    // The formula rides the tile face, which is the button that opens the
    // drill-down — the article around it is the frame, not the control.
    const face = kpiTile("Stockout-risk SKUs").querySelector(".risk-kpi-open");
    // The tile counts the whole reorder zone -- `Position < ROP` -- the same
    // predicate Replenishment and Demand Forecasting use for their own
    // stockout-risk tiles.
    expect(face).toHaveAttribute(
      "title",
      expect.stringContaining("Position < ROP"),
    );
    expect(face).toHaveAttribute("title", expect.stringContaining("distinct SKU"));
  });

  it("drills to the reorder zone from the stockout tile, and back again", async () => {
    await renderSettled();

    /*
     * Two actions now live on this tile and they are deliberately separate
     * controls: the face opens the decomposition, this one re-scopes the whole
     * board. A single click that could do either would leave the reader
     * guessing which they were about to get.
     */
    const scopeButton = () =>
      within(kpiTile("Stockout-risk SKUs")).getByRole("button", {
        name: "Show only the reorder zone",
      });

    fireEvent.click(scopeButton());
    await waitFor(() => {
      const rows = document.querySelectorAll(".risk-row");
      expect(rows.length).toBeGreaterThan(0);
      for (const row of rows) {
        expect(row.className).toContain("risk-row--stockout");
      }
    });

    // Clicking again clears it rather than trapping the reader in the filter.
    fireEvent.click(scopeButton());
    await waitFor(() => {
      expect(screen.getByText("All retail inventory")).toBeInTheDocument();
    });
  });

  it("draws a chart on every KPI tile, through the normalizer", async () => {
    /*
     * `normalizeInventoryRiskDashboard` returns an explicit object, so a block
     * the selectors add and the normalizer omits is dropped in silence —
     * which is exactly how these charts went missing on this board while
     * working on the other two. Asserting through the rendered dashboard, not
     * the selector, is what makes that catchable.
     */
    await renderSettled();

    const grid = document.querySelector(".risk-kpi-grid");
    expect(grid.querySelectorAll(".risk-kpi")).toHaveLength(6);
    expect(grid.querySelectorAll(".kpi-spark")).toHaveLength(6);
  });

  it("opens a drill-down drawer that decomposes the tile it was opened from", async () => {
    await renderSettled();

    fireEvent.click(kpiTile("Inventory value").querySelector(".risk-kpi-open"));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("Inventory value")).toBeInTheDocument();
    // The formula the tile hints at, stated in full inside the drawer.
    expect(within(drawer).getByText(/Σ Position × unit price/)).toBeInTheDocument();
    expect(within(drawer).getByText("This metric by category")).toBeInTheDocument();
    expect(within(drawer).getByText("This metric by store")).toBeInTheDocument();
    expect(within(drawer).getByText("Top contributing SKUs")).toBeInTheDocument();

    /*
     * The mockup fills this section with a seeded random walk. This dataset
     * holds one snapshot per SKU and no date column, so the drawer says there
     * is no history rather than drawing one nobody can tell is fictional.
     */
    expect(
      within(drawer).getByText(/No history recorded/),
    ).toBeInTheDocument();

    fireEvent.click(within(drawer).getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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

  it("lengthens the projection from the horizon control, and says what that costs", async () => {
    await renderSettled();

    const horizon = screen.getByRole("group", { name: "Horizon" });
    const projectionPanel = () =>
      screen.getByText("Projected on-hand vs demand").closest(".risk-panel");

    // Opens on four weeks, and stays quiet about the flat-demand assumption
    // while the curve is short enough for it to be reasonable.
    expect(within(horizon).getByRole("button", { name: "4w" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      within(projectionPanel()).queryByText(/adds structure, not more measurement/),
    ).not.toBeInTheDocument();

    fireEvent.click(within(horizon).getByRole("button", { name: "16w" }));

    await waitFor(() => {
      expect(
        within(horizon).getByRole("button", { name: "16w" }),
      ).toHaveAttribute("aria-pressed", "true");
    });

    // Sixteen weeks of curve, and the caveat that its level is measured once.
    await waitFor(() => {
      expect(
        within(projectionPanel()).getByText(/adds structure, not more measurement/),
      ).toBeInTheDocument();
    });
  });

  it("keeps the drill-down open across a horizon change, since no row moves", async () => {
    await renderSettled();

    fireEvent.click(kpiTile("Inventory value").querySelector(".risk-kpi-open"));
    await screen.findByRole("dialog");

    fireEvent.click(
      within(screen.getByRole("group", { name: "Horizon" })).getByRole(
        "button",
        { name: "12w" },
      ),
    );

    await waitFor(() => {
      expect(
        within(screen.getByRole("group", { name: "Horizon" })).getByRole(
          "button",
          { name: "12w" },
        ),
      ).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("offers the five levers the workbook can model, and no markdown lever", async () => {
    await renderSettled();

    expect(screen.getByLabelText("Demand surge")).toBeEnabled();
    expect(screen.getByLabelText("Inbound cover")).toBeEnabled();
    // formula.json has no markdown term, so the lever is absent rather than
    // present-and-disabled — see MARKDOWN_INSIGHT_NOTE in contract.js.
    expect(screen.queryByLabelText("Markdown clear")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Pricing & Markdown board/),
    ).toBeInTheDocument();
  });

  it("moves the simulator and board live as the slider moves", async () => {
    await renderSettled();

    const boardBefore = kpiTile("Stockout-risk SKUs").textContent;
    const simBefore = simMetric("Stockout-risk SKUs").textContent;

    fireEvent.change(screen.getByLabelText("Demand surge"), {
      target: { value: "40" },
    });

    // Both the panel's own preview and the board follow the slider immediately
    await waitFor(() => {
      expect(simMetric("Stockout-risk SKUs").textContent).not.toBe(simBefore);
      expect(kpiTile("Stockout-risk SKUs").textContent).not.toBe(boardBefore);
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
