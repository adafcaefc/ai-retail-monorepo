import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../../LanguageProvider.jsx";
import ReplenishmentDetailDashboard from "./ReplenishmentDetailDashboard.jsx";

/*
 * `fetchDashboard` is mocked rather than a fixture being loaded, because this
 * board deliberately ships without one — it reads the API or it reports an
 * error. `common/dataSource.js` forces DATA_SOURCE to "fixture" under Vitest,
 * which for every sibling board means "read the bundled JSON" and here would
 * mean "read nothing at all".
 */
vi.mock("../../../api/dashboard.js", () => ({
  fetchDashboard: vi.fn(),
}));

const { fetchDashboard } = await import("../../../api/dashboard.js");

/** One API-shaped line. The defaults are the spec's worked example. */
function line(overrides = {}) {
  const base = {
    sku_id: "GRC-001",
    name: "Fruit 1",
    category_id: "GRC-C01",
    category_label: "Fruit",
    vertical_id: "GRC",
    qty_on_hand: 1151,
    open_po: 25,
    position: 1176,
    demand_per_day: 496.87,
    rop: 1491,
    max: 3478,
    is_reorder: true,
    required_qty_sales: 2302,
    order_qty_sales: 2302,
    buy_uom: "Crate",
    pack_factor: 12,
    order_qty_buy: 192,
    packs_required_exact: 2302 / 12,
    ordered_sales_units: 2304,
    rounding_uplift: 2,
    designated_vendor: "Vendor E",
    unit_price_ta: 14300,
    amount: 32947200,
    best_price_vendor: "Vendor E",
    best_price: 14300,
    saving_vs_designated: 0,
    saving_pct: 0,
    has_alternate_vendor: false,
    lead_time_days: 2,
    exception_codes: [],
    action_eligibility: "ELIGIBLE",
  };
  return { ...base, ...overrides };
}

const PAYLOAD = {
  schema_version: 1,
  agent: "retail.replenishment_detail",
  generated_at: "2026-07-01T00:00:00Z",
  is_mock: true,
  note: "Workbook demonstration data.",
  source_workbook: "test.xlsx",
  formulas: {},
  exception_codes: ["MISSING_BUY_UOM"],
  filter_options: {
    legal_entities: [
      { value: "GRC", label: "Grocery" },
      { value: "DGT", label: "Digital" },
    ],
    categories: [{ value: "GRC-C01", label: "Fruit", legal_entity_id: "GRC" }],
  },
  lines: [
    line(),
    line({
      sku_id: "DGT-046",
      name: "Toys 1",
      vertical_id: "DGT",
      category_label: "Toys",
      buy_uom: "Case",
      pack_factor: 48,
      order_qty_buy: 129,
      order_qty_sales: 6164,
      ordered_sales_units: 6192,
      rounding_uplift: 28,
      unit_price_ta: 881750,
      amount: 5459796000,
      designated_vendor: "Vendor C",
      best_price_vendor: "Vendor G",
      best_price: 843150,
      saving_vs_designated: 239011200,
      saving_pct: 4.378,
      has_alternate_vendor: true,
    }),
    line({
      sku_id: "GRC-002",
      name: "Fruit 2",
      is_reorder: false,
      order_qty_sales: 0,
      order_qty_buy: 0,
      ordered_sales_units: 0,
      rounding_uplift: 0,
      required_qty_sales: 0,
      amount: 0,
      action_eligibility: "NO_ORDER",
    }),
  ],
  quotes: [
    { sku_id: "DGT-046", vendor: "Vendor C", vendor_account: "V-C", unit_price: 881750, min_qty_break: 10, discount_pct: 0, is_designated: true },
    { sku_id: "DGT-046", vendor: "Vendor G", vendor_account: "V-G", unit_price: 843150, min_qty_break: 50, discount_pct: 0, is_designated: false },
  ],
  quote_terms: {
    currency: "IDR",
    lead_time_days: 6,
    valid_from: "2025-01-01",
    valid_to: "2026-12-31",
  },
  vendors: [],
  reference_by_vertical: [],
};

function renderBoard() {
  return render(
    <LanguageProvider>
      <ReplenishmentDetailDashboard />
    </LanguageProvider>,
  );
}

async function renderSettled() {
  renderBoard();
  await screen.findByTestId("replenishment-detail-grid");
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchDashboard.mockResolvedValue(structuredClone(PAYLOAD));
});

describe("ReplenishmentDetailDashboard", () => {
  it("asks the API for its own agent id, with no filters by default", async () => {
    await renderSettled();

    expect(fetchDashboard).toHaveBeenCalledWith("retail.replenishment_detail", {});
  });

  it("renders the six KPI tiles of the spec", async () => {
    await renderSettled();
    const strip = screen.getByTestId("replenishment-detail-kpis");

    for (const label of [
      "Reorder SKUs",
      "Order qty (sales)",
      "Order qty (buy)",
      "Purchase amount",
      "Potential saving",
      "Alternate-vendor SKUs",
    ]) {
      expect(within(strip).getByText(label)).toBeInTheDocument();
    }
  });

  it("opens on reorder lines, sorted by amount descending", async () => {
    await renderSettled();
    const rows = within(screen.getByTestId("replenishment-detail-grid"))
      .getAllByRole("button")
      .filter((node) => node.tagName === "TR");

    // The resting line is filtered out; the larger amount leads.
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAccessibleName("DGT-046 Toys 1");
    expect(rows[1]).toHaveAccessibleName("GRC-001 Fruit 1");
  });

  it("counts reorder SKUs against the whole scope, not the visible rows", async () => {
    await renderSettled();
    const strip = screen.getByTestId("replenishment-detail-kpis");

    // Two of three, even though the grid shows only the two.
    expect(within(strip).getByText("of 3 SKUs in scope")).toBeInTheDocument();
  });

  it("narrows the grid by a client-side filter without refetching", async () => {
    await renderSettled();
    expect(fetchDashboard).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText("Buy UOM"), {
      target: { value: "Crate" },
    });

    await waitFor(() => {
      const rows = within(screen.getByTestId("replenishment-detail-grid"))
        .getAllByRole("button")
        .filter((node) => node.tagName === "TR");
      expect(rows).toHaveLength(1);
      expect(rows[0]).toHaveAccessibleName("GRC-001 Fruit 1");
    });
    // The whole point of narrowing in the browser: no second round trip.
    expect(fetchDashboard).toHaveBeenCalledTimes(1);
  });

  it("refetches when a server-side filter changes", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Vertical"), {
      target: { value: "GRC" },
    });

    await waitFor(() =>
      expect(fetchDashboard).toHaveBeenLastCalledWith(
        "retail.replenishment_detail",
        { legal_entity_id: "GRC" },
      ),
    );
  });

  it("shows the resting line only when asked for it", async () => {
    await renderSettled();

    fireEvent.change(screen.getByLabelText("Reorder status"), {
      target: { value: "NO_ORDER" },
    });

    await waitFor(() => {
      const rows = within(screen.getByTestId("replenishment-detail-grid"))
        .getAllByRole("button")
        .filter((node) => node.tagName === "TR");
      expect(rows).toHaveLength(1);
      expect(rows[0]).toHaveAccessibleName("GRC-002 Fruit 2");
    });
  });

  it("opens the inspector on a row click and shows the calculation trace", async () => {
    await renderSettled();

    fireEvent.click(screen.getByRole("button", { name: "GRC-001 Fruit 1" }));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText(/Position = 1,151 \+ 25 = 1,176/)).toBeInTheDocument();
    expect(within(drawer).getByText(/CEILING\(2,302 \/ 12\) = 192 Crate/)).toBeInTheDocument();
    expect(within(drawer).getByText(/2,304 × Rp14,300 = Rp32,947,200/)).toBeInTheDocument();
  });

  it("says plainly that execution is not connected in this dataset", async () => {
    await renderSettled();

    fireEvent.click(screen.getByRole("button", { name: "GRC-001 Fruit 1" }));

    const drawer = await screen.findByRole("dialog");
    expect(
      within(drawer).getByText(/recommendation snapshot, not an execution ledger/),
    ).toBeInTheDocument();
  });

  it("ranks the cheaper vendor first in the comparison", async () => {
    await renderSettled();

    fireEvent.click(screen.getByRole("button", { name: "DGT-046 Toys 1" }));

    const drawer = await screen.findByRole("dialog");
    const vendorRows = within(drawer)
      .getAllByRole("row")
      .filter((row) => within(row).queryByText(/Vendor [CG]/));
    expect(within(vendorRows[0]).getByText("Vendor G")).toBeInTheDocument();
  });

  it("segments buy quantity by UOM instead of totalling it", async () => {
    await renderSettled();
    const panel = screen.getByTestId("replenishment-detail-uom");

    expect(within(panel).getByText("Crate")).toBeInTheDocument();
    expect(within(panel).getByText("Case")).toBeInTheDocument();
    expect(
      within(panel).getByText(/not additive across Crates, Pallets and Packs/),
    ).toBeInTheDocument();
  });

  it("renders the error branch with a working retry when the request fails", async () => {
    fetchDashboard.mockRejectedValueOnce(new Error("Dashboard request failed (503)"));

    renderBoard();

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/Dashboard request failed \(503\)/)).toBeInTheDocument();

    // The retry has to actually re-request, not just clear the message.
    fetchDashboard.mockResolvedValueOnce(structuredClone(PAYLOAD));
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));

    await screen.findByTestId("replenishment-detail-grid");
    expect(fetchDashboard).toHaveBeenCalledTimes(2);
  });

  it("never falls back to demo data when the request fails", async () => {
    fetchDashboard.mockRejectedValue(new Error("network down"));

    renderBoard();

    await screen.findByRole("alert");
    // Silently substituting a fixture would render a grid here, and the board
    // would look like it was working.
    expect(screen.queryByTestId("replenishment-detail-grid")).toBeNull();
  });
});

describe("the frozen identifier columns", () => {
  /*
   * REGRESSION. The sticky offsets were hardcoded guesses at the columns'
   * rendered widths, and auto table layout sizes to content -- so they were
   * wrong, and the gap between a frozen column and the next showed the
   * scrolled row through it. On screen that reads as a value in the frozen
   * column: "MN" appeared under a heading that said OMN.
   *
   * jsdom does no layout, so the rendered geometry cannot be asserted. What
   * CAN be asserted is the invariant the pixels depend on: each offset is the
   * running total of the widths before it, plus the cell padding. If someone
   * retunes a width and forgets the offset, this fails.
   */
  const CELL_PADDING_X = 20; // 10px each side, from .rdet-table td

  function stickyRules() {
    // Vitest runs from the frontend root, so the stylesheet is one
    // predictable path away. import.meta.url is not a file URL here.
    const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");
    const rules = [];

    for (const index of [1, 2, 3]) {
      // Plain string scanning rather than a constructed RegExp: a backslash in
      // a template literal collapses before RegExp ever sees it, which is how
      // the first version of this test silently matched nothing.
      const selector = `.rdet-table td.sticky:nth-child(${index})`;
      const at = css.indexOf(selector);
      expect(at, `no sticky rule for column ${index}`).toBeGreaterThan(-1);

      const open = css.indexOf("{", at);
      const body = css.slice(open + 1, css.indexOf("}", open));
      const left = /left:\s*(\d+)px/.exec(body);
      const width = /--rdet-clip-w:\s*(\d+)px/.exec(body);

      expect(width, `column ${index} declares no width`).toBeTruthy();
      rules.push({ left: left ? Number(left[1]) : 0, width: Number(width[1]) });
    }
    return rules;
  }

  it("offsets each frozen column by the running total of the ones before it", () => {
    const rules = stickyRules();
    let running = 0;

    rules.forEach((rule, index) => {
      expect(rule.left, `column ${index + 1} sits at the wrong offset`).toBe(
        running,
      );
      running += rule.width + CELL_PADDING_X;
    });
  });

  it("wraps frozen cell content, which is what the width applies to", async () => {
    // A `td` in an auto-layout table may ignore a width outright, so the
    // constraint has to land on an inner element. No span, no width, and the
    // offsets stop meaning anything again.
    await renderSettled();
    const row = screen.getByRole("button", { name: "GRC-001 Fruit 1" });
    const sticky = row.querySelectorAll("td.sticky");

    expect(sticky).toHaveLength(3);
    for (const cell of sticky) {
      expect(cell.querySelector(".rdet-clip")).not.toBeNull();
    }
  });

  it("keeps the full item name reachable once the column truncates it", async () => {
    await renderSettled();
    const row = screen.getByRole("button", { name: "GRC-001 Fruit 1" });

    expect(row.querySelectorAll("td")[1]).toHaveAttribute("title", "Fruit 1");
  });
});
