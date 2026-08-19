import { describe, expect, it } from "vitest";

import { ALL, DEFAULT_SCOPE, DEFAULT_SORT } from "./contract.js";
import { buildDetailCsv } from "./csv.js";
import {
  buildDashboardFromRows,
  buildInspector,
  buildTrace,
  computeExceptionCounts,
  computeFilterFacets,
  computeKpis,
  computeUomBreakdown,
  matchesSearch,
  rowState,
  scopeLines,
  sortLines,
  sum,
} from "./selectors.js";

/*
 * A hand-built population rather than a fixture: this board has none, and
 * inventing one purely to test against would make the test agree with a file
 * nothing else reads. Six lines are enough to cover every branch, and the
 * numbers are the spec's own worked example plus deliberate variations on it.
 */
const GRC_001 = {
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
  exception_codes: [],
  action_eligibility: "ELIGIBLE",
};

function line(overrides) {
  return { ...GRC_001, ...overrides };
}

const LINES = [
  GRC_001,
  // A cheaper vendor exists and the saving is real.
  line({
    sku_id: "DGT-046",
    name: "Toys 1",
    vertical_id: "DGT",
    category_id: "DGT-C03",
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
  // Blocked: no buy UOM, so the pack it orders cannot be named.
  line({
    sku_id: "ELC-010",
    name: "Cable 3",
    vertical_id: "ELC",
    category_id: "ELC-C02",
    category_label: "Cable",
    buy_uom: null,
    exception_codes: ["MISSING_BUY_UOM"],
    action_eligibility: "BLOCKED",
    amount: 1000000,
    saving_vs_designated: 0,
  }),
  // Resting: nothing to order.
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
    saving_vs_designated: 0,
    action_eligibility: "NO_ORDER",
  }),
  // Same UOM as the first, so the breakdown has a group to aggregate.
  line({
    sku_id: "GRC-003",
    name: "Fruit 3",
    order_qty_buy: 8,
    order_qty_sales: 90,
    ordered_sales_units: 96,
    rounding_uplift: 6,
    amount: 1372800,
    saving_vs_designated: 0,
  }),
  // Zero amount but a positive saving, for the divide-by-zero guard.
  line({
    sku_id: "HNB-007",
    name: "Soap 4",
    vertical_id: "HNB",
    category_id: "HNB-C01",
    category_label: "Soap",
    buy_uom: "Pallet",
    pack_factor: 100,
    order_qty_buy: 1,
    order_qty_sales: 50,
    ordered_sales_units: 100,
    rounding_uplift: 50,
    amount: 0,
    unit_price_ta: 0,
    best_price_vendor: "Vendor B",
    best_price: 0,
    saving_vs_designated: 5000,
    has_alternate_vendor: true,
    exception_codes: ["MISSING_TA_PRICE"],
    action_eligibility: "BLOCKED",
  }),
];

const REORDER = LINES.filter((item) => item.is_reorder);

describe("scopeLines", () => {
  it("opens on reorder lines, which is the spec's default view", () => {
    const scoped = scopeLines(LINES, DEFAULT_SCOPE);

    expect(scoped).toHaveLength(REORDER.length);
    expect(scoped.every((item) => item.is_reorder)).toBe(true);
  });

  it("is a no-op with every filter cleared", () => {
    const scoped = scopeLines(LINES, { ...DEFAULT_SCOPE, reorder_status: ALL });

    expect(scoped).toHaveLength(LINES.length);
  });

  it("separates resting lines from blocked ones", () => {
    // Both are un-actionable today; only one is a data problem, and folding
    // them together is what would make the exception queue unreadable.
    const resting = scopeLines(LINES, {
      ...DEFAULT_SCOPE,
      reorder_status: "NO_ORDER",
    });

    expect(resting.map((item) => item.sku_id)).toEqual(["GRC-002"]);
  });

  it("narrows by each vendor field independently", () => {
    const byDesignated = scopeLines(LINES, {
      ...DEFAULT_SCOPE,
      designated_vendor: "Vendor C",
    });
    const byBest = scopeLines(LINES, {
      ...DEFAULT_SCOPE,
      best_price_vendor: "Vendor G",
    });

    expect(byDesignated.map((item) => item.sku_id)).toEqual(["DGT-046"]);
    expect(byBest.map((item) => item.sku_id)).toEqual(["DGT-046"]);
  });

  it("narrows by buy UOM and by eligibility", () => {
    expect(
      scopeLines(LINES, { ...DEFAULT_SCOPE, buy_uom: "Crate" }).map((i) => i.sku_id),
    ).toEqual(["GRC-001", "GRC-003"]);
    expect(
      scopeLines(LINES, { ...DEFAULT_SCOPE, eligibility: "BLOCKED" }).map(
        (i) => i.sku_id,
      ),
    ).toEqual(["ELC-010", "HNB-007"]);
  });

  it("keeps only lines with a positive saving when asked", () => {
    const scoped = scopeLines(LINES, { ...DEFAULT_SCOPE, saving_only: true });

    expect(scoped.every((item) => item.saving_vs_designated > 0)).toBe(true);
    expect(scoped).toHaveLength(2);
  });

  it("treats a blank amount bound as no bound, not as zero", () => {
    // An empty box must not exclude every line, which is what `Number("")`
    // coercing to 0 would do at the other end of the comparison.
    const open = scopeLines(LINES, {
      ...DEFAULT_SCOPE,
      min_amount: "",
      max_amount: "",
    });
    const bounded = scopeLines(LINES, { ...DEFAULT_SCOPE, min_amount: "2000000" });

    expect(open).toHaveLength(REORDER.length);
    expect(bounded.map((item) => item.sku_id)).toEqual(["GRC-001", "DGT-046"]);
  });

  it("searches item code and item name, case-insensitively", () => {
    expect(matchesSearch(GRC_001, "grc-001")).toBe(true);
    expect(matchesSearch(GRC_001, "Fruit")).toBe(true);
    expect(matchesSearch(GRC_001, "Vendor E")).toBe(false);
    expect(matchesSearch(GRC_001, "  ")).toBe(true);
  });
});

describe("computeKpis", () => {
  it("counts reorder SKUs against the whole scope, not the filtered rows", () => {
    // The grid opens filtered to reorder lines. If the denominator came from
    // the same list, "5 of 5" would always be true and the ratio meaningless.
    const kpis = computeKpis(REORDER, LINES);

    expect(kpis.reorder_sku_count).toBe(5);
    expect(kpis.skus_in_scope).toBe(6);
  });

  it("ties every money and unit figure to the rows it sums", () => {
    const kpis = computeKpis(REORDER, LINES);

    expect(kpis.purchase_amount).toBe(sum(REORDER, "amount"));
    expect(kpis.potential_saving).toBe(sum(REORDER, "saving_vs_designated"));
    expect(kpis.order_qty_sales).toBe(sum(REORDER, "order_qty_sales"));
    expect(kpis.ordered_sales_units).toBe(sum(REORDER, "ordered_sales_units"));
  });

  it("reports ordered units at or above the requirement", () => {
    // Pack rounding can only ever add. A scope where it subtracted would mean
    // the conversion had been inverted somewhere.
    const kpis = computeKpis(REORDER, LINES);

    expect(kpis.ordered_sales_units).toBeGreaterThanOrEqual(kpis.order_qty_sales);
    expect(kpis.rounding_uplift).toBe(
      kpis.ordered_sales_units - kpis.order_qty_sales,
    );
  });

  it("counts distinct buy UOMs rather than summing across them", () => {
    const kpis = computeKpis(REORDER, LINES);

    // Crate, Case, Pallet — the null-UOM line is not a unit.
    expect(kpis.buy_uom_count).toBe(3);
  });

  it("counts alternate-vendor lines and blocked lines separately", () => {
    const kpis = computeKpis(REORDER, LINES);

    expect(kpis.alternate_vendor_count).toBe(2);
    expect(kpis.blocked_count).toBe(2);
  });
});

describe("computeUomBreakdown", () => {
  it("partitions the lines it is given", () => {
    const rows = computeUomBreakdown(REORDER);

    expect(sum(rows, "line_count")).toBe(REORDER.length);
    expect(sum(rows, "order_qty_buy")).toBe(sum(REORDER, "order_qty_buy"));
    expect(sum(rows, "amount")).toBe(sum(REORDER, "amount"));
  });

  it("groups the two Crate lines and names the missing UOM", () => {
    const rows = computeUomBreakdown(REORDER);
    const crate = rows.find((row) => row.buy_uom === "Crate");

    expect(crate.line_count).toBe(2);
    expect(crate.order_qty_buy).toBe(200);
    expect(rows.some((row) => row.buy_uom === "(none)")).toBe(true);
  });

  it("orders by amount, so the unit carrying the order leads", () => {
    const rows = computeUomBreakdown(REORDER);
    const amounts = rows.map((row) => row.amount);

    expect(amounts).toEqual([...amounts].sort((a, b) => b - a));
  });
});

describe("sortLines", () => {
  it("defaults to amount descending", () => {
    const sorted = sortLines(REORDER, DEFAULT_SORT);
    const amounts = sorted.map((item) => item.amount);

    expect(amounts).toEqual([...amounts].sort((a, b) => b - a));
  });

  it("breaks ties by saving, then by item, so the order is stable", () => {
    // Hundreds of real lines share an amount of zero. Without a final key the
    // same query renders in a different order each time, which reads as data
    // changing under the reader.
    const tied = [
      line({ sku_id: "B", amount: 0, saving_vs_designated: 0 }),
      line({ sku_id: "A", amount: 0, saving_vs_designated: 0 }),
      line({ sku_id: "C", amount: 0, saving_vs_designated: 10 }),
    ];

    expect(sortLines(tied, DEFAULT_SORT).map((i) => i.sku_id)).toEqual([
      "C",
      "A",
      "B",
    ]);
  });

  it("sorts text columns alphabetically in the direction asked", () => {
    const ascending = sortLines(REORDER, { by: "sku_id", direction: "asc" });
    const codes = ascending.map((item) => item.sku_id);

    expect(codes).toEqual([...codes].sort());
  });

  it("does not mutate the array it was given", () => {
    const before = REORDER.map((item) => item.sku_id);
    sortLines(REORDER, { by: "sku_id", direction: "asc" });

    expect(REORDER.map((item) => item.sku_id)).toEqual(before);
  });
});

describe("rowState", () => {
  it("ranks blocked above every other signal", () => {
    // A line that cannot be actioned outranks one that merely has an
    // opportunity attached, however large the opportunity.
    expect(rowState(LINES.find((i) => i.sku_id === "HNB-007"))).toBe("blocked");
    expect(rowState(LINES.find((i) => i.sku_id === "DGT-046"))).toBe("alternate");
    expect(rowState(LINES.find((i) => i.sku_id === "GRC-002"))).toBe("resting");
    expect(rowState(GRC_001)).toBe("action");
  });
});

describe("computeFilterFacets", () => {
  it("offers every vendor and UOM in the data, not just the visible ones", () => {
    // A dropdown that only offers what is already selected cannot be used to
    // change the selection.
    const facets = computeFilterFacets(LINES);

    expect(facets.vendors.map((o) => o.value)).toEqual(["Vendor C", "Vendor E"]);
    expect(facets.best_price_vendors.map((o) => o.value)).toEqual([
      "Vendor B",
      "Vendor E",
      "Vendor G",
    ]);
    expect(facets.buy_uoms.map((o) => o.value)).toEqual([
      "Case",
      "Crate",
      "Pallet",
    ]);
  });
});

describe("computeExceptionCounts", () => {
  it("counts each code across the lines carrying it", () => {
    expect(computeExceptionCounts(LINES)).toEqual({
      MISSING_BUY_UOM: 1,
      MISSING_TA_PRICE: 1,
    });
  });
});

describe("buildTrace", () => {
  it("reproduces the spec's worked example, line by line", () => {
    const trace = buildTrace(GRC_001).join(" ");

    expect(trace).toContain("Position = 1,151 + 25 = 1,176.");
    expect(trace).toContain("Position 1,176 < ROP 1,491");
    expect(trace).toContain("Max 3,478 − Position 1,176 = 2,302");
    expect(trace).toContain("CEILING(2,302 / 12) = 192 Crate");
    expect(trace).toContain("192 × 12 = 2,304");
    expect(trace).toContain("2,304 × Rp14,300 = Rp32,947,200");
  });

  it("stops after the reorder verdict when there is nothing to order", () => {
    const trace = buildTrace(LINES.find((i) => i.sku_id === "GRC-002"));

    expect(trace.join(" ")).toContain("nothing to convert or price");
    expect(trace.join(" ")).not.toContain("CEILING");
  });

  it("names the winning vendor when a saving exists", () => {
    const trace = buildTrace(LINES.find((i) => i.sku_id === "DGT-046")).join(" ");

    expect(trace).toContain("Rp881,750 − Rp843,150");
    expect(trace).toContain("Rp239,011,200");
  });
});

describe("buildInspector", () => {
  const quotes = {
    "DGT-046": [
      { sku_id: "DGT-046", vendor: "Vendor C", vendor_account: "V-C", unit_price: 881750, min_qty_break: 10, is_designated: true },
      { sku_id: "DGT-046", vendor: "Vendor G", vendor_account: "V-G", unit_price: 843150, min_qty_break: 50, is_designated: false },
    ],
  };
  const terms = { currency: "IDR", lead_time_days: 6, valid_from: "2025-01-01", valid_to: "2026-12-31" };

  it("returns null without a line, so the drawer stays closed", () => {
    expect(buildInspector(null, quotes, terms)).toBeNull();
  });

  it("orders vendor candidates cheapest first", () => {
    const inspector = buildInspector(
      LINES.find((i) => i.sku_id === "DGT-046"),
      quotes,
      terms,
    );

    expect(inspector.vendor.candidates.map((q) => q.vendor)).toEqual([
      "Vendor G",
      "Vendor C",
    ]);
    expect(inspector.vendor.terms).toBe(terms);
  });

  it("carries the four spec sections even with no quotes on file", () => {
    const inspector = buildInspector(GRC_001, {}, terms);

    expect(inspector.inventory).toHaveLength(6);
    expect(inspector.conversion).toHaveLength(7);
    expect(inspector.vendor.candidates).toEqual([]);
    expect(inspector.trace.length).toBeGreaterThan(0);
  });
});

describe("buildDetailCsv", () => {
  it("writes raw numbers, not formatted ones", () => {
    // Spec section 15: exported values stay numeric so they are an input to
    // somebody else's arithmetic rather than a string they have to unpick.
    const csv = buildDetailCsv([GRC_001]);

    expect(csv).toContain("32947200");
    expect(csv).not.toContain("Rp");
    expect(csv).not.toContain("32,947,200");
  });

  it("renders the reorder flag as it reads on screen", () => {
    expect(buildDetailCsv([GRC_001])).toContain("YES");
    expect(buildDetailCsv([LINES.find((i) => i.sku_id === "GRC-002")])).toContain("—");
  });

  it("defuses a vendor name that would run as a formula", () => {
    const csv = buildDetailCsv([line({ designated_vendor: "=cmd|calc" })]);

    expect(csv).toContain("'=cmd|calc");
  });

  it("joins exception codes into one cell", () => {
    const csv = buildDetailCsv([
      line({ exception_codes: ["MISSING_BUY_UOM", "MISSING_VENDOR"] }),
    ]);

    expect(csv).toContain("MISSING_BUY_UOM MISSING_VENDOR");
  });
});

describe("buildDashboardFromRows", () => {
  const payload = {
    schema_version: 1,
    agent: "retail.replenishment_detail",
    generated_at: "2026-07-01T00:00:00Z",
    is_mock: true,
    note: "n",
    filter_options: { legal_entities: [], categories: [] },
    lines: LINES,
    quotes: [{ sku_id: "GRC-001", vendor: "Vendor E", unit_price: 14300 }],
    quote_terms: { currency: "IDR" },
  };

  it("keeps every line, because narrowing is the board's job", () => {
    /*
     * REGRESSION. This used to apply the scope, and the board then re-narrowed
     * the already-narrowed rows — so the unfiltered population was gone the
     * moment the payload loaded, and "All lines" and "No order" both returned
     * nothing. One rule, one home.
     */
    const shaped = buildDashboardFromRows(payload);

    expect(shaped.lines).toHaveLength(LINES.length);
    expect(shaped.lines.some((item) => !item.is_reorder)).toBe(true);
  });

  it("describes the whole payload before anything is filtered", () => {
    const shaped = buildDashboardFromRows(payload);

    expect(shaped.kpis.skus_in_scope).toBe(LINES.length);
    expect(shaped.kpis.purchase_amount).toBe(sum(LINES, "amount"));
  });

  it("indexes quotes by SKU and carries the agreement terms", () => {
    const shaped = buildDashboardFromRows(payload);

    expect(shaped.quotes_by_sku["GRC-001"]).toHaveLength(1);
    expect(shaped.quote_terms.currency).toBe("IDR");
  });

  it("offers dropdown facets derived from every row", () => {
    const shaped = buildDashboardFromRows(payload);

    expect(shaped.filter_options.buy_uoms.map((o) => o.value)).toEqual([
      "Case",
      "Crate",
      "Pallet",
    ]);
  });
});
