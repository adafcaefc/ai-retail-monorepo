import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import ReplenishmentDashboard from "./ReplenishmentDashboard.jsx";
import { DEFAULT_SCOPE } from "./data/contract.js";
import { buildDashboardFromFixture } from "./data/selectors.js";
import fixture from "./data/fixture.json";

/*
 * No stub between the board and its data: the fixture provider is pure and
 * synchronous, so these assertions cover the whole chain rather than a mock.
 *
 * Recharts lays out against real boxes, and jsdom reports zero for every
 * element. Pinning the container is what makes the chart assertions mean
 * anything.
 */
beforeEach(() => {
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

async function renderSettled() {
  const result = render(
    <LanguageProvider>
      <ReplenishmentDashboard />
    </LanguageProvider>,
  );
  await screen.findByText("Purchase order preview");
  return result;
}

const grocery = fixture.reference_by_vertical.find(
  (row) => row.legal_entity_id === "GRC",
);

/*
 * Scoped to the KPI grid on purpose. Three of the four labels the What-If strip
 * compares are also KPI labels — the panel exists to show what a lever does to
 * the headline figures, so of course it repeats them. An unscoped `getByText`
 * would match both and fail on the ambiguity rather than on the number.
 */
function kpiTile(label) {
  const grid = document.querySelector(".po-kpi-grid");
  return within(grid).getByText(label).closest(".po-kpi");
}

describe("the fixture reconciles with the A3 sheet", () => {
  it("carries 800 lines and every vertical's reference totals", () => {
    expect(fixture.lines).toHaveLength(800);
    expect(fixture.stores).toHaveLength(160);
    expect(fixture.reference_by_vertical).toHaveLength(8);
    expect(fixture.is_mock).toBe(true);
  });

  it.each(fixture.reference_by_vertical)(
    "matches $vertical_label on the five computed KPIs",
    (reference) => {
      const scope = {
        ...DEFAULT_SCOPE,
        legal_entity_id: reference.legal_entity_id,
        reorder_only: false,
      };
      const { kpis } = buildDashboardFromFixture(fixture, scope);

      expect(kpis.skus_to_reorder).toBe(reference.skus_to_reorder);
      expect(kpis.order_units).toBe(reference.order_units);
      expect(kpis.order_value_retail).toBe(reference.order_value);
      expect(Number(kpis.fill_rate_pct.toFixed(1))).toBeCloseTo(
        reference.fill_rate_pct,
        6,
      );
      expect(Number(kpis.avg_cover_days.toFixed(1))).toBeCloseTo(
        reference.avg_cover_d,
        6,
      );
    },
  );

  it("routes every line by lead time, covering all three", () => {
    const byRoute = new Map();
    for (const line of fixture.lines) {
      byRoute.set(line.route, (byRoute.get(line.route) || 0) + 1);
    }
    // Lead 2d / 4d / 7d, which is 75 / 625 / 100 in this dataset.
    expect(byRoute.get("direct")).toBe(75);
    expect(byRoute.get("flow")).toBe(625);
    expect(byRoute.get("cross")).toBe(100);

    // The fresh rule and the lead-time rule pick the same rows where they
    // overlap: every 2-day line is perishable, and no other line is.
    for (const line of fixture.lines) {
      expect(line.route === "direct").toBe(line.perishable === "Y");
    }
  });

  it("agrees with Inventory Risk on which SKUs need reordering", () => {
    // A3 reads the workbook's own YES/NO; A2 computes `Position < ROP`. They
    // must select the same 302 rows, or the two boards contradict each other.
    const need = fixture.lines.filter((line) => line.is_reorder);
    expect(need).toHaveLength(302);
    for (const line of fixture.lines) {
      expect(line.is_reorder).toBe(line.position < line.rop);
    }
  });
});

describe("the two order values", () => {
  it("prices the same order at cost and at retail, and they differ", () => {
    const { kpis } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);

    expect(kpis.order_value_cost).toBeGreaterThan(0);
    expect(kpis.order_value_retail).toBeGreaterThan(kpis.order_value_cost);
    // Roughly a fifth apart on this dataset. The board shows both because
    // approving a PO at retail value would overstate the commitment.
    expect(kpis.order_value_cost / kpis.order_value_retail).toBeLessThan(0.95);
  });

  it("buys whole packs, so each line covers at least its shortfall", () => {
    const { purchase_order: rows } = buildDashboardFromFixture(
      fixture,
      DEFAULT_SCOPE,
    );

    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.order_qty_buy * row.pack_factor).toBeGreaterThanOrEqual(
        row.order_qty_sales,
      );
      // And never by a whole extra pack.
      expect(row.order_qty_buy * row.pack_factor - row.order_qty_sales).toBeLessThan(
        row.pack_factor,
      );
    }
  });
});

describe("the dimension grid (mockup ch-dim-cat / -store / -clu / -le)", () => {
  it("carries all four dimensions, legal entity included", () => {
    /*
     * `by_legal_entity` was the one chart of the mockup's four this board
     * never built, while A1 and A2 both had it. Nothing was missing from the
     * data — the store rows already carried `vertical_id`.
     */
    const board = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);

    expect(board.by_legal_entity.length).toBe(8);
    for (const row of board.by_legal_entity) {
      expect(row.order_value_retail).toBeGreaterThan(0);
      expect(row.store_count).toBeGreaterThan(0);
    }
    // Sorted largest first, like every other dimension on the board.
    const values = board.by_legal_entity.map((row) => row.order_value_retail);
    expect([...values].sort((a, b) => b - a)).toEqual(values);
  });

  it("puts every dimension panel on the same measure", () => {
    /*
     * The category panel used to plot cost while store and cluster plotted
     * retail — a fifth apart, in one grid, with nothing saying so. Whatever
     * the panels plot, the store-derived dimensions must agree on a total,
     * because they partition the same stores.
     */
    const board = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const total = (rows) =>
      rows.reduce((running, row) => running + row.order_value_retail, 0);

    expect(total(board.by_cluster)).toBeCloseTo(total(board.by_store), 6);
    expect(total(board.by_legal_entity)).toBeCloseTo(total(board.by_store), 6);
  });
});

describe("the KPI drill-down drawer", () => {
  it("decomposes the tile it was opened from, with no invented history", async () => {
    await renderSettled();

    const tile = screen.getByText("Order value at retail").closest(".po-kpi");
    fireEvent.click(tile.querySelector(".po-kpi-open"));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("This metric by category")).toBeInTheDocument();
    expect(within(drawer).getByText("Top contributing SKUs")).toBeInTheDocument();
    // Retail value is one of the measures the per-store grid does carry.
    expect(within(drawer).getByText("This metric by store")).toBeInTheDocument();
    // The mockup fills this with a seeded random walk; this dataset has no
    // dated source, so the drawer says so instead of drawing one.
    expect(within(drawer).getByText(/No history recorded/)).toBeInTheDocument();
  });

  it("says why a measure has no per-store split rather than allocating one", async () => {
    await renderSettled();

    // Cost is priced from trade agreements, which the per-store grid has none
    // of. Inventing a split here is exactly what the mockup did.
    const tile = screen.getByText("Order value at cost").closest(".po-kpi");
    fireEvent.click(tile.querySelector(".po-kpi-open"));

    const drawer = await screen.findByRole("dialog");
    expect(
      within(drawer).getByText(/no per-store figure to show/),
    ).toBeInTheDocument();
  });
});

describe("ReplenishmentDashboard", () => {
  it("renders the KPIs, the route split, sourcing and the order", async () => {
    await renderSettled();

    expect(document.querySelectorAll(".po-kpi")).toHaveLength(6);
    expect(screen.getByText("Order value by route")).toBeInTheDocument();
    expect(screen.getByText("Vendor sourcing")).toBeInTheDocument();
    expect(screen.getByText("Order value by category")).toBeInTheDocument();
    expect(screen.getByText("Purchase order preview")).toBeInTheDocument();
  });

  it("opens on what needs ordering, not on the whole assortment", async () => {
    await renderSettled();

    // 302 of 800 lines sit below ROP; a buyer opening this board wants those.
    expect(screen.getByLabelText("Only what needs ordering")).toBeChecked();
    expect(within(kpiTile("SKUs to reorder")).getByText("302")).toBeInTheDocument();
  });

  it("labels the source rather than presenting workbook figures as live", async () => {
    await renderSettled();

    expect(screen.getByText(/Workbook data/)).toBeInTheDocument();
    // Twice on purpose: the payload's own note and the standing footnote both
    // say it, because the two order values are the thing most likely to be
    // misread on this board.
    expect(screen.getAllByText(/at selling price/).length).toBeGreaterThanOrEqual(1);
  });

  it("scopes to one vertical and reports that vertical's numbers", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Legal entity"), {
      target: { value: "GRC" },
    });

    await waitFor(() => {
      expect(
        within(kpiTile("SKUs to reorder")).getByText(String(grocery.skus_to_reorder)),
      ).toBeInTheDocument();
    });
  });

  it("filters the order down to one route", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Route"), {
      target: { value: "direct" },
    });

    await waitFor(() => {
      const rows = document.querySelectorAll(".po-row");
      expect(rows.length).toBeGreaterThan(0);
      expect(rows.length).toBeLessThan(302);
    });
  });

  it("pages the purchase order rather than rendering every line", async () => {
    await renderSettled();

    expect(document.querySelectorAll(".po-row")).toHaveLength(40);
    expect(screen.getByText(/Page 1 \/ /)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(screen.getByText(/Page 2 \/ /)).toBeInTheDocument();
    });
  });

  it("explains the arithmetic where the arithmetic is", async () => {
    await renderSettled();

    const cells = document.querySelector(".po-row").querySelectorAll("td.num");
    const titles = [...cells].map((cell) => cell.getAttribute("title"));

    expect(titles).toContain("Position = On-hand + Open PO");
    expect(titles).toContain("Order = max(0, Max − Position)");
    expect(titles).toContain("Buy = CEILING(Order ÷ pack factor)");
  });

  it("names what switching vendor would recover", async () => {
    await renderSettled();

    const tile = screen.getByText("Recoverable").closest(".po-kpi");
    expect(within(tile).getByText(/Rp/)).toBeInTheDocument();
    // The saving is attributed per vendor, not only as a chain total: a
    // saving nobody can attribute is a saving nobody can act on.
    const panel = screen.getByText("Vendor sourcing").closest(".po-panel");
    expect(panel.querySelectorAll(".po-vendor-list li").length).toBeGreaterThan(0);
  });

  it("warns that purchase quantities round up to whole packs", async () => {
    await renderSettled();
    expect(screen.getByText(/round up to whole packs/)).toBeInTheDocument();
  });
});

describe("requirement versus inbound supply (spec 4)", () => {
  it("draws both curves and names when cover runs out", async () => {
    await renderSettled();

    const panel = screen
      .getByText("Requirement vs inbound supply")
      .closest(".po-panel");
    expect(panel).toBeInTheDocument();

    // The four figures spec 4 puts under the chart.
    const strip = panel.querySelector(".po-metric-strip");
    for (const label of ["Reorder", "Order qty", "PO value", "Fill"]) {
      expect(within(strip).getByText(label)).toBeInTheDocument();
    }
  });

  it("says the inbound date is assumed, because the workbook has none", async () => {
    await renderSettled();
    // The one modelled step on an otherwise measured board. If this caveat ever
    // disappears the chart starts reading as a delivery schedule.
    expect(
      screen.getByText(/records how much is on order but never when it arrives/),
    ).toBeInTheDocument();
  });

  it("draws 16 real weeks of history, Today, and 16 real weeks of forecast", () => {
    const { requirement } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);

    // W-16..W-1, Today, W+1..W+16.
    expect(requirement.points).toHaveLength(requirement.weeks_back + 1 + requirement.weeks_forward);
    expect(requirement.points.map((point) => point.label)[16]).toBe("Today");

    const history = requirement.points.slice(0, 16);
    const forward = requirement.points.slice(17);

    // History is a real weekly rate, not fabricated, and not cumulative --
    // there is nothing behind "16 weeks ago" to accumulate against.
    for (const point of history) {
      expect(point.requirement).toBeNull();
      expect(point.cover).toBeNull();
      expect(point.actual_demand).toBeGreaterThan(0);
    }

    expect(requirement.points[16].requirement).toBe(0);

    for (let index = 1; index < forward.length; index += 1) {
      const previous = forward[index - 1];
      const point = forward[index];
      // Demand only accumulates; cover only ever gains an arrival.
      expect(point.requirement).toBeGreaterThan(previous.requirement);
      expect(point.cover).toBeGreaterThanOrEqual(previous.cover);
    }

    /*
     * Over every line in scope, not only the 302 being ordered. The chart
     * answers "can the chain cover its demand", which the reorder subset
     * cannot: those are by definition the lines that cannot.
     */
    const last = forward[forward.length - 1];
    expect(last.cover).toBeCloseTo(
      fixture.lines.reduce((total, line) => total + line.on_hand + line.open_po, 0),
      6,
    );
  });

  it("reconciles the first forecast week's chain total against ads x week_factor", () => {
    // The same calibration scripts/build_replenishment_fixture.py's
    // verify_demand_curves checks at build time -- re-derived here from the
    // shipped fixture so a hand-edited fixture.json cannot silently drift.
    const { requirement } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const week1 = requirement.points[17];
    expect(week1.label).toBe("W+1");
    // requirement at W+1 is the cumulative total through week 1, i.e. week 1
    // alone since Today's requirement is 0.
    const totalAds = fixture.lines.reduce((total, line) => total + line.ads, 0);
    expect(week1.requirement).toBeCloseTo(totalAds * fixture.constants.dow_sum, -1);
  });
});

describe("the route tabs and export (spec 7)", () => {
  it("offers all three routes plus the whole order", async () => {
    await renderSettled();

    const bar = screen.getByRole("tablist", { name: "Purchase order route" });
    const tabs = within(bar).getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      expect.stringContaining("All routes"),
      expect.stringContaining("Direct Store Delivery"),
      expect.stringContaining("Flow-Through"),
      expect.stringContaining("Cross-Docking"),
    ]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
  });

  it("narrows the order to one route without touching the board scope", async () => {
    await renderSettled();

    const before = document.querySelectorAll(".po-row").length;
    fireEvent.click(screen.getByRole("tab", { name: /Direct Store Delivery/ }));

    await waitFor(() => {
      expect(
        screen.getByRole("tab", { name: /Direct Store Delivery/ }),
      ).toHaveAttribute("aria-selected", "true");
    });

    // The tab groups this table only. The board-level route filter is a
    // separate control and must still read "All".
    expect(screen.getByLabelText("Route")).toHaveValue("ALL");
    expect(document.querySelectorAll(".po-row").length).toBeLessThanOrEqual(before);
  });

  it("offers a per-route export only once a route is chosen", async () => {
    await renderSettled();

    expect(screen.getByRole("button", { name: "Export CSV" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export full PO" })).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: /Cross-Docking/ }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Export this route" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Export full PO" })).toBeInTheDocument();
  });
});

describe("What-If (spec 9)", () => {
  it("opens at the workbook's own lever setting, which is zero", async () => {
    await renderSettled();

    for (const label of ["Demand surge", "Promo pull", "Inbound cover"]) {
      expect(screen.getByLabelText(label)).toHaveValue("0");
    }
    // No scenario banner until something moves.
    expect(screen.queryByText(/simulated order/)).toBeNull();
  });

  it("disables the markdown lever and says why", async () => {
    await renderSettled();

    expect(screen.getByLabelText("Markdown clear")).toBeDisabled();
    expect(
      screen.getByText(/the workbook carries no term for it/),
    ).toBeInTheDocument();
  });

  it("re-runs the order and flags the board as simulated", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Lead time"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(screen.getByText(/simulated order, not one to send/)).toBeInTheDocument();
    });

    // A longer lead raises Max, so more lines fall below ROP than the 302 the
    // workbook stores.
    const reordered = Number(
      within(kpiTile("SKUs to reorder")).getByText(/^\d+$/).textContent,
    );
    expect(reordered).toBeGreaterThan(302);
  });

  it("returns to the workbook position when the scenario is cleared", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Lead time"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() =>
      expect(screen.getByText(/simulated order, not one to send/)).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Back to workbook" }));

    await waitFor(() => {
      expect(within(kpiTile("SKUs to reorder")).getByText("302")).toBeInTheDocument();
    });
    expect(screen.queryByText(/simulated order/)).toBeNull();
  });

  it("cannot save a scenario until one exists", async () => {
    await renderSettled();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("says plainly that saved scenarios do not persist", async () => {
    await renderSettled();
    expect(
      screen.getByText(/held in this browser tab only and are not saved anywhere/),
    ).toBeInTheDocument();
  });
});

describe("the simulation at rest", () => {
  it("returns the baseline object itself rather than recomputing it", () => {
    const { simulation } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);

    expect(simulation.applied).toBe(false);
    // Identity, not equality. Re-running 302 lines at zero levers would land
    // within a float ulp of the stored figures and report a delta on a board
    // nobody has touched.
    expect(simulation.scenario).toBe(simulation.baseline);
    expect(simulation.requirement).toBeNull();
  });

  it("names the lever that reaches no formula", () => {
    const { simulation } = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    expect(simulation.unmodelled).toContain("markdown");
  });
});

/*
 * Asserted through the rendered board, not through the selector.
 *
 * `computeSourcing` was correct and the panel still showed nothing the first
 * time a block like this was added: `normalizeReplenishmentDashboard` returns
 * an explicit object, so a block the selectors produce and the normalizer does
 * not list is dropped silently between them. A selector test passes throughout.
 * This is the shape of test that does not.
 */
describe("the vendor quote panel", () => {
  it("renders the quotes the saving is a difference between", async () => {
    await renderSettled();

    const panel = screen.getByLabelText("Vendor quotes");
    const rows = within(panel).getAllByRole("listitem");
    expect(rows.length).toBeGreaterThan(0);

    // The workbook holds one validity window and one lead time across all
    // 2,400 quotes, so the panel states them once instead of per row.
    expect(within(panel).getByText(/IDR/)).toBeInTheDocument();
  });

  it("opens a line onto its three quotes, flagged", async () => {
    await renderSettled();

    const panel = screen.getByLabelText("Vendor quotes");
    const first = within(panel).getAllByRole("listitem")[0];

    fireEvent.click(first.querySelector("summary"));

    const table = within(first).getByRole("table");
    // Three vendors quote every SKU in this dataset: the incumbent, the
    // cheapest, and one more.
    expect(within(table).getAllByRole("row")).toHaveLength(4); // header + 3
    expect(within(table).getByText("designated")).toBeInTheDocument();
    expect(within(table).getByText("cheapest")).toBeInTheDocument();
  });

  it("shows the incumbent and the vendor it would move to", async () => {
    const board = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const top = board.sourcing.skus[0];

    await renderSettled();
    const panel = screen.getByLabelText("Vendor quotes");
    const first = within(panel).getAllByRole("listitem")[0];

    expect(within(first).getByText(top.sku_id, { exact: false })).toBeInTheDocument();
    // Named twice by design: once in the summary as the vendor being moved
    // away from, once in the table as the row holding the incumbent price.
    expect(
      within(first).getAllByText(top.designated_vendor, { exact: false }).length,
    ).toBeGreaterThan(0);
    expect(
      within(first).getAllByText(top.best_price_vendor, { exact: false }).length,
    ).toBeGreaterThan(0);
  });
});
