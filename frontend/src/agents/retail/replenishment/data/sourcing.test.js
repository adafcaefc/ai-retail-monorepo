/*
 * The trade-agreement quotes, and what the panel is allowed to conclude
 * from them.
 *
 * `scripts/build_replenishment_fixture.py` already refuses to write a fixture
 * whose quotes cannot rebuild `best_price`, `unit_price_trade` and
 * `saving_vs_designated`, so that identity is not re-asserted here. What is
 * asserted is the part that lives in JavaScript: which lines the panel keeps,
 * what it ranks them by, and that its total is the same money the KPI tile
 * reports rather than a second opinion about it.
 */

import { describe, expect, it } from "vitest";

import { DEFAULT_SCOPE } from "./contract.js";
import fixture from "./fixture.json";
import { buildDashboardFromFixture, computeSourcing } from "./selectors.js";

describe("the quotes behind the saving", () => {
  it("carries every quote on file, three to a SKU", () => {
    expect(fixture.quotes).toHaveLength(2400);

    const perSku = new Map();
    for (const quote of fixture.quotes) {
      perSku.set(quote.sku_id, (perSku.get(quote.sku_id) ?? 0) + 1);
    }
    expect(perSku.size).toBe(800);
    expect([...new Set(perSku.values())]).toEqual([3]);

    // Exactly one designated vendor per SKU: the incumbent the saving is
    // measured against. Two would make "switch away from" ambiguous.
    const designated = new Map();
    for (const quote of fixture.quotes) {
      if (quote.is_designated) {
        designated.set(quote.sku_id, (designated.get(quote.sku_id) ?? 0) + 1);
      }
    }
    expect([...new Set(designated.values())]).toEqual([1]);
  });

  it("totals to the same money the KPI tile reports", () => {
    const board = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const panelTotal = board.sourcing.skus.reduce(
      (running, row) => running + row.saving,
      0,
    );

    /*
     * The KPI sums `saving_vs_designated` over the scoped lines; the panel
     * sums the rows it decided to show. They agree because a line with no
     * saving contributes zero to the first and is excluded from the second —
     * if the panel ever started filtering on something else, this is what
     * would catch a headline that no longer adds up to its own detail.
     */
    expect(panelTotal).toBeCloseTo(board.kpis.recoverable_saving, 6);
  });

  it("ranks by saving, and keeps only lines that have one to take", () => {
    const board = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const { skus, switchable_lines, on_best_lines } = board.sourcing;

    expect(skus.length).toBeGreaterThan(0);
    expect(switchable_lines).toBe(skus.length);

    for (const row of skus) {
      expect(row.saving).toBeGreaterThan(0);
      expect(row.order_qty_buy).toBeGreaterThan(0);
      expect(row.designated_vendor).not.toBe(row.best_price_vendor);
    }

    const savings = skus.map((row) => row.saving);
    expect(savings).toEqual([...savings].sort((a, b) => b - a));

    // Every ordered line is either switchable or already on the best price.
    const ordered = fixture.lines.filter((line) => line.order_qty_buy > 0);
    expect(switchable_lines + on_best_lines).toBe(ordered.length);
  });

  it("prices the saving on whole packs, not on the shortfall", () => {
    const board = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const row = board.sourcing.skus[0];
    const line = fixture.lines.find((entry) => entry.sku_id === row.sku_id);

    expect(row.order_units).toBe(line.order_qty_buy * line.pack_factor);
    // A purchase order buys packs. Pricing the gap on `order_qty_sales` would
    // understate this line by a factor of its pack size.
    expect(row.order_units).not.toBe(line.order_qty_sales);
    expect(row.saving).toBeCloseTo(
      (row.unit_price_trade - row.best_price) * row.order_units,
      3,
    );
  });

  it("ranks on list price and leaves the discount unapplied", () => {
    const board = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);

    /*
     * The workbook picks its winner on list price. Applying `discount_pct`
     * names a different vendor on a substantial minority of SKUs, so a panel
     * that quietly applied it would contradict the saving printed beside it.
     * This asserts the disagreement exists — if it ever stopped existing, the
     * warning in the panel would be describing a problem the data no longer
     * has.
     */
    let wouldChange = 0;
    const bySku = new Map();
    for (const quote of fixture.quotes) {
      const offers = bySku.get(quote.sku_id) ?? [];
      offers.push(quote);
      bySku.set(quote.sku_id, offers);
    }
    for (const offers of bySku.values()) {
      const byList = offers.reduce((a, b) => (b.unit_price < a.unit_price ? b : a));
      const byNet = offers.reduce((a, b) =>
        b.unit_price * (1 - b.discount_pct / 100) <
        a.unit_price * (1 - a.discount_pct / 100)
          ? b
          : a,
      );
      if (byList.vendor_account !== byNet.vendor_account) wouldChange += 1;
    }
    expect(wouldChange).toBeGreaterThan(0);

    // And the panel's own choice is the list-price one, on every row.
    for (const row of board.sourcing.skus) {
      const cheapestList = row.quotes.reduce((a, b) =>
        b.unit_price < a.unit_price ? b : a,
      );
      expect(row.best_price_vendor).toBe(cheapestList.vendor);
      expect(row.best_price).toBe(cheapestList.unit_price);
    }
  });

  it("says nothing rather than something empty when there are no quotes", () => {
    // A backend that predates the block, or a scope with no order in it.
    const empty = computeSourcing(fixture.lines, undefined, undefined);
    expect(empty).toEqual({
      terms: null,
      skus: [],
      switchable_lines: 0,
      on_best_lines: 0,
    });
  });

  it("narrows with the scope it is given", () => {
    const chain = buildDashboardFromFixture(fixture, DEFAULT_SCOPE);
    const grocery = buildDashboardFromFixture(fixture, {
      ...DEFAULT_SCOPE,
      legal_entity_id: "GRC",
    });

    expect(grocery.sourcing.skus.length).toBeLessThan(chain.sourcing.skus.length);
    for (const row of grocery.sourcing.skus) {
      expect(row.sku_id.startsWith("GRC")).toBe(true);
    }
  });
});
