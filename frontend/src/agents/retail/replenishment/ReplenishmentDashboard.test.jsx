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
    const tile = screen.getByText("SKUs to reorder").closest(".po-kpi");
    expect(within(tile).getByText("302")).toBeInTheDocument();
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
      const tile = screen.getByText("SKUs to reorder").closest(".po-kpi");
      expect(
        within(tile).getByText(String(grocery.skus_to_reorder)),
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
