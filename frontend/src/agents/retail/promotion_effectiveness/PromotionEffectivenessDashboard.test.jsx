import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import PromotionEffectivenessDashboard from "./PromotionEffectivenessDashboard.jsx";
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
      <PromotionEffectivenessDashboard />
    </LanguageProvider>,
  );
}

/*
 * The skeleton and the loaded board share `data-testid`, deliberately — it is
 * the same board in two states. Wait for content only the loaded board renders.
 */
async function renderSettled() {
  const result = renderDashboard();
  await screen.findByText("Promotion calendar preview");
  return result;
}

/*
 * KPI labels are not unique on the board and should not be: "Uplift %" also
 * labels a calendar-table column and a best-action-table column, so a scoped
 * query beats a bare text match.
 */
function kpiTile(label) {
  const grid = document.querySelector(".promo-kpi-grid");
  return within(grid).getByText(label).closest(".promo-kpi");
}

const grocery = fixture.reference_by_vertical.find(
  (row) => row.legal_entity_id === "GRC",
);
const groceryItemCount = fixture.items.filter((i) => i.vertical_id === "GRC").length;

describe("PromotionEffectivenessDashboard", () => {
  it("renders six KPIs, the mainHTML block, the full dimension row, and the plan panels", async () => {
    renderDashboard();

    await screen.findByTestId("promotion-effectiveness-dashboard");

    expect(document.querySelectorAll(".promo-kpi")).toHaveLength(6);
    expect(screen.getByText("Promotion uplift vs margin quality")).toBeInTheDocument();
    expect(screen.getByText("Incremental margin by vertical")).toBeInTheDocument();
    expect(screen.getByText("Incremental margin by channel")).toBeInTheDocument();
    expect(screen.getByText("Promotion calendar preview")).toBeInTheDocument();
    expect(screen.getByText("Incremental margin by category")).toBeInTheDocument();
    expect(screen.getByText("Incremental margin by store")).toBeInTheDocument();
    expect(screen.getByText("Incremental margin by cluster")).toBeInTheDocument();
    expect(screen.getByText("Campaign mix by season (pre-buy units)")).toBeInTheDocument();
    expect(screen.getByText("Inventory value by state")).toBeInTheDocument();
    expect(screen.getByText("Suggested best action")).toBeInTheDocument();
    expect(screen.getByText("Promo margin leaders")).toBeInTheDocument();
    expect(screen.getByText("What-If simulator")).toBeInTheDocument();
  });

  it("labels the source rather than presenting workbook figures as live", async () => {
    renderDashboard();

    expect(await screen.findByText(/Workbook data/)).toBeInTheDocument();
    expect(screen.getByText(/not a live ERP or D365 Commerce position/)).toBeInTheDocument();
  });

  it("carries the store-grain reconciliation caveat, distinct from the chain-net one", async () => {
    renderDashboard();

    expect(
      await screen.findByText(/reconciles exactly to the chain-net headline/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Incremental margin is chain-net gross/),
    ).toBeInTheDocument();
  });

  it("scopes to one vertical and narrows the KPI grid to that vertical's numbers", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Vertical"), {
      target: { value: "GRC" },
    });

    await waitFor(() => {
      expect(
        within(kpiTile("Active promo SKUs")).getByText(String(groceryItemCount)),
      ).toBeInTheDocument();
    });

    const summary = document.querySelector(".promo-scope-summary");
    expect(within(summary).getByText(/GRC/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));

    await waitFor(() => {
      expect(screen.getByText("All retail promotions")).toBeInTheDocument();
    });
  });

  it("narrows uplift and ROI to the selected vertical, not the chain average", async () => {
    // Regression test for the bug this redesign fixed: uplift_pct/roi_x used
    // to always average across every vertical regardless of scope, so the
    // Vertical filter silently left these two tiles unchanged.
    await renderSettled();

    const chainUplift = kpiTile("Uplift %").textContent;

    fireEvent.change(screen.getByLabelText("Vertical"), {
      target: { value: "GRC" },
    });

    await waitFor(() => {
      expect(kpiTile("Uplift %").textContent).not.toBe(chainUplift);
    });
  });

  it("scopes the board to one store, showing that store's own reconstructed position", async () => {
    await renderSettled();

    const store = fixture.stores[0];
    const chainMargin = kpiTile("Incremental margin").textContent;

    const select = screen.getByLabelText("Store");
    expect(select).toBeEnabled();
    fireEvent.change(select, { target: { value: store.store_id } });

    await waitFor(() => {
      expect(screen.getByLabelText("Store")).toHaveValue(store.store_id);
    });

    // Active promo SKUs stays at the store's own vertical total — the
    // workbook carries no per-store assortment restriction — while
    // Incremental margin narrows to that store's own share of it.
    const verticalItemCount = fixture.items.filter(
      (i) => i.vertical_id === store.vertical_id,
    ).length;
    await waitFor(() => {
      expect(
        within(kpiTile("Active promo SKUs")).getByText(String(verticalItemCount)),
      ).toBeInTheDocument();
    });
    expect(kpiTile("Incremental margin").textContent).not.toBe(chainMargin);
  });

  it("does not change the campaign calendar or season mix under a store scope", async () => {
    await renderSettled();

    const rowsBefore = document.querySelectorAll(".promo-calendar-row").length;

    fireEvent.change(screen.getByLabelText("Store"), {
      target: { value: fixture.stores[0].store_id },
    });

    await waitFor(() => {
      expect(screen.getByLabelText("Store")).toHaveValue(fixture.stores[0].store_id);
    });
    expect(document.querySelectorAll(".promo-calendar-row").length).toBe(rowsBefore);
  });

  it("narrows to a single campaign with a promo-name search", async () => {
    await renderSettled();

    const target = fixture.campaigns[0];
    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: target.promo_id },
    });

    await waitFor(() => {
      const rows = document.querySelectorAll(".promo-calendar-row");
      expect(rows.length).toBeGreaterThan(0);
      for (const row of rows) {
        expect(row.textContent).toContain(target.promo_id);
      }
    });
  });

  it("offers all six levers and marks the one the workbook cannot model as inert", async () => {
    await renderSettled();

    expect(screen.getByLabelText("Demand uplift")).toBeEnabled();
    expect(screen.getByLabelText("Promo depth")).toBeEnabled();
    expect(screen.getByLabelText("Markdown depth")).toBeEnabled();
    // Inert, not disabled: the lever is still draggable, it just carries no
    // modelled effect on promo margin (spec: the workbook has no markdown term).
    const markdownLever = screen.getByLabelText("Markdown depth").closest(".promo-lever");
    expect(markdownLever.className).toContain("is-inert");
  });

  it("keeps the board on the workbook until Run is pressed", async () => {
    await renderSettled();

    const before = kpiTile("Incremental margin").textContent;
    fireEvent.change(screen.getByLabelText("Promo depth"), {
      target: { value: "30" },
    });

    // Dragging a slider re-runs the engine over every promo-eligible SKU;
    // doing that per pixel would fight the user, so nothing moves until Run.
    expect(kpiTile("Incremental margin").textContent).toBe(before);
    expect(screen.queryByText(/Scenario active/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(kpiTile("Incremental margin").textContent).not.toBe(before);
    });
  });

  it("says the board is showing a scenario, and takes it back", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Promo depth"), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(screen.getByText(/Scenario active/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Promo depth 30%/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back to workbook" }));

    await waitFor(() => {
      expect(screen.queryByText(/Scenario active/)).not.toBeInTheDocument();
    });
  });

  it("drives the whole page when the toggle is on, and only the simulator when it is off", async () => {
    await renderSettled();

    const verticalChart = () =>
      screen.getByText("Incremental margin by vertical").closest(".promo-chart-block")
        .textContent;

    fireEvent.click(screen.getByLabelText("Drive whole page"));
    await waitFor(() => {
      expect(screen.getByLabelText("Drive whole page")).not.toBeChecked();
    });

    const before = verticalChart();
    fireEvent.change(screen.getByLabelText("Promo depth"), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(screen.getByText(/Scenario active/)).toBeInTheDocument();
    });
    // Off: the dimension charts stay put even though a scenario is applied.
    expect(verticalChart()).toBe(before);
  });

  it("saves a scenario and overlays it against the baseline", async () => {
    await renderSettled();

    expect(screen.getByRole("button", { name: "Save scenario" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Promo depth"), { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save scenario" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Save scenario" }));

    await screen.findByText("Compare scenarios");
    await waitFor(() => {
      expect(document.querySelectorAll(".promo-scenario-list li")).toHaveLength(1);
    });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    // The panel renders nothing once the last scenario is gone, rather than
    // an empty list — so the section itself must disappear.
    await waitFor(() => {
      expect(screen.queryByText("Compare scenarios")).not.toBeInTheDocument();
    });
  });

  it("partitions the best-action tabs and lets a reader export either one", async () => {
    await renderSettled();

    const panel = screen.getByText("Suggested best action").closest(".promo-best-action");
    const tabs = within(panel).getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(
      expect.arrayContaining([
        expect.stringContaining("High ROI"),
        expect.stringContaining("Funding Gap"),
        expect.stringContaining("Pre-buy Required"),
      ]),
    );

    // Every campaign lands in exactly one tab.
    const counts = tabs.map((tab) => Number(tab.querySelector(".promo-tab-count").textContent));
    expect(counts.reduce((a, b) => a + b, 0)).toBe(fixture.campaigns.length);

    // CSV export is guarded under jsdom (no createObjectURL) — clicking must
    // not throw, matching the replenishment purchase-order export test.
    expect(() =>
      fireEvent.click(within(panel).getByRole("button", { name: "Export this tab" })),
    ).not.toThrow();
    expect(() =>
      fireEvent.click(within(panel).getByRole("button", { name: "Export all campaigns" })),
    ).not.toThrow();
  });

  it("opens a drill-down drawer for incremental margin, and closes it again", async () => {
    await renderSettled();

    fireEvent.click(kpiTile("Incremental margin"));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("Incremental margin")).toBeInTheDocument();
    expect(within(drawer).getByText(/SUM\(f13/)).toBeInTheDocument();
    expect(within(drawer).getByText("This metric by category")).toBeInTheDocument();
    expect(within(drawer).getByText("This metric by vertical")).toBeInTheDocument();
    expect(within(drawer).getByText("Top contributing SKUs")).toBeInTheDocument();
    // One snapshot day, no date column — the drawer says so rather than
    // fabricating a trend.
    expect(within(drawer).getByText(/No history recorded/)).toBeInTheDocument();

    fireEvent.click(within(drawer).getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("is a no-op to click a non-drillable tile (uplift and ROI are stored KPIs)", async () => {
    await renderSettled();

    fireEvent.click(kpiTile("Uplift %"));

    // Give any errant async work a turn, then confirm no drawer opened and no
    // error banner appeared.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reads the chain-wide reference figures at the default scope", async () => {
    await renderSettled();

    const chainUplift =
      fixture.reference_by_vertical.reduce((t, r) => t + r.uplift_pct, 0) /
      fixture.reference_by_vertical.length;

    // Sanity check that the fixture itself carries Grocery's own figure
    // distinctly from the chain average, so the vertical-scoping test above
    // is actually exercising a real difference and not a coincidence.
    expect(grocery.uplift_pct).not.toBeCloseTo(chainUplift, 1);
  });
});
