import { describe, expect, it } from "vitest";

import { BASELINE_LEVERS, LEVER_DEFINITIONS } from "./contract.js";
import { createEngine, isBaseline } from "./engine.js";
import fixture from "./fixture.json";
import { buildPurchaseOrderCsv, purchaseOrderFilename } from "./csv.js";

const applyLevers = createEngine(fixture.formulas);
const ordered = fixture.lines.filter((line) => line.order_qty_sales > 0);

describe("the engine at the workbook's own lever setting", () => {
  /*
   * The load-bearing test of this module.
   *
   * `Constants` B16–B21 are all zero, so zero levers is the setting every
   * stored column in the fixture was calculated at. If the engine reproduces
   * those columns exactly, then it and the workbook are running the same rules
   * — and any difference a slider produces later can only have come from the
   * lever, not from a transcription error.
   */
  it("reproduces all 800 lines exactly", () => {
    for (const line of fixture.lines) {
      const out = applyLevers(line, BASELINE_LEVERS);

      expect(out.ads).toBeCloseTo(line.ads, 9);
      expect(out.position).toBe(line.position);
      expect(out.rop).toBe(line.rop);
      expect(out.max).toBe(line.max);
      expect(out.order_qty_sales).toBe(line.order_qty_sales);
      expect(out.order_qty_buy).toBe(line.order_qty_buy);
      expect(out.is_reorder).toBe(line.is_reorder);
    }
  });

  /*
   * Both order values and the vendor saving are *read* columns at baseline and
   * *computed* ones under a scenario. That seam is where a board silently
   * changes its own numbers the moment a slider is touched and put back, so it
   * gets its own assertion rather than riding along with the quantities.
   */
  it("reproduces both order values and the saving on all 345 ordered lines", () => {
    expect(ordered).toHaveLength(345);

    for (const line of ordered) {
      const out = applyLevers(line, BASELINE_LEVERS);

      expect(out.order_value_cost).toBe(line.order_value_cost);
      expect(out.order_value_retail).toBe(line.order_value_retail);
      expect(out.saving_vs_designated).toBe(line.saving_vs_designated);
    }
  });

  it("recognises the baseline without recomputing it", () => {
    expect(isBaseline(BASELINE_LEVERS)).toBe(true);
    expect(isBaseline({})).toBe(true);
    expect(isBaseline({ demand: 1 })).toBe(false);
  });

  /*
   * The 32-week demand curve rides on the line, and a scenario line is a
   * spread of the baseline one. If a future edit replaces that spread with an
   * explicit field list, the curve is the field most likely to be left behind
   * — and the requirement chart would silently fall back to the flat daily
   * presentation under a lever, which reads as the lever deleting history.
   */
  it("carries the 32-week demand curve through a lever move", () => {
    const line = fixture.lines[0];
    const out = applyLevers(line, { ...BASELINE_LEVERS, demand: 10 });

    expect(out.demand_weekly).toBe(line.demand_weekly);
    expect(out.demand_weekly.actual).toHaveLength(16);
    expect(out.demand_weekly.forecast).toHaveLength(16);
  });
});

describe("what the levers actually reach", () => {
  const sample = fixture.lines.slice(0, 120);

  /*
   * Direction, not magnitude. Asserting an exact figure here would only restate
   * the formula; asserting the sign catches the error that matters — a lever
   * wired backwards, which reads perfectly plausibly on screen and would send
   * a buyer the wrong way.
   */
  it("raises the order when demand rises", () => {
    for (const line of sample) {
      const base = applyLevers(line, BASELINE_LEVERS);
      const up = applyLevers(line, { ...BASELINE_LEVERS, demand: 20 });
      expect(up.max).toBeGreaterThanOrEqual(base.max);
      expect(up.order_qty_sales).toBeGreaterThanOrEqual(base.order_qty_sales);
    }
  });

  it("shrinks the order when inbound cover rises", () => {
    for (const line of sample) {
      const base = applyLevers(line, BASELINE_LEVERS);
      const up = applyLevers(line, { ...BASELINE_LEVERS, inbound: 50 });
      expect(up.position).toBeGreaterThanOrEqual(base.position);
      expect(up.order_qty_sales).toBeLessThanOrEqual(base.order_qty_sales);
    }
  });

  it("raises the order when lead time or safety days rise", () => {
    for (const lever of ["lead", "safety"]) {
      for (const line of sample) {
        const base = applyLevers(line, BASELINE_LEVERS);
        const up = applyLevers(line, { ...BASELINE_LEVERS, [lever]: 3 });
        expect(up.max).toBeGreaterThanOrEqual(base.max);
        expect(up.order_qty_sales).toBeGreaterThanOrEqual(base.order_qty_sales);
      }
    }
  });

  /*
   * The reorder set is not fixed. A longer lead pushes lines below ROP that
   * were healthy at rest — which is the whole reason `computeSimulation`
   * re-filters after simulating instead of holding the baseline's membership.
   */
  it("pulls new lines into the reorder set as lead time grows", () => {
    const base = fixture.lines.filter((line) => line.is_reorder).length;
    const stretched = fixture.lines.filter(
      (line) => applyLevers(line, { ...BASELINE_LEVERS, lead: 6 }).is_reorder,
    ).length;

    expect(base).toBe(345);
    expect(stretched).toBeGreaterThan(base);
  });

  /*
   * `markdown` is declared inert in `LEVER_DEFINITIONS`, and this is what that
   * declaration means: the workbook has no markdown term, so the slider reaches
   * no formula. Asserted rather than commented, because the day somebody adds a
   * markdown expression to the catalogue this test should fail and make them
   * update the label.
   */
  it("leaves everything unchanged when the markdown lever moves", () => {
    const markdown = LEVER_DEFINITIONS.find((lever) => lever.id === "markdown");
    expect(markdown.modelled).toBe(false);

    for (const line of sample) {
      const base = applyLevers(line, BASELINE_LEVERS);
      const moved = applyLevers(line, { ...BASELINE_LEVERS, markdown: 60 });
      expect(moved).toEqual(base);
    }
  });
});

describe("the CSV export", () => {
  it("writes one header and one row per line, unformatted", () => {
    const csv = buildPurchaseOrderCsv(ordered.slice(0, 3));
    const rows = csv.trimEnd().split("\r\n");

    expect(rows).toHaveLength(4);
    expect(rows[0]).toContain("SKU");
    expect(rows[0]).toContain("Line value (cost)");
    // Raw numbers: this file is an input to somebody else's arithmetic.
    expect(rows[1]).toContain(String(ordered[0].order_value_cost));
    expect(rows[1]).not.toMatch(/Rp| /);
  });

  /*
   * A cell beginning `=`, `+`, `-` or `@` is executed as a formula when the
   * file is opened in Excel or Sheets. Vendor and product names come from data,
   * so the export has to defuse them — a CSV that runs code on open is a real
   * vector, not a theoretical one.
   */
  it("defuses fields that a spreadsheet would run as a formula", () => {
    const csv = buildPurchaseOrderCsv([
      { sku_id: "=1+1", name: "@SUM(A1)", designated_vendor: "-cmd", position: 5 },
    ]);
    const row = csv.trimEnd().split("\r\n")[1];

    expect(row).toContain("'=1+1");
    expect(row).toContain("'@SUM(A1)");
    expect(row).toContain("'-cmd");
  });

  it("quotes fields containing a comma or a quote", () => {
    const csv = buildPurchaseOrderCsv([{ name: 'Rice, 5kg "premium"' }]);
    expect(csv).toContain('"Rice, 5kg ""premium"""');
  });

  it("names the file by route and date so exports sort", () => {
    expect(purchaseOrderFilename("direct", "2026-08-12T05:32:30+00:00")).toBe(
      "purchase-order-direct-2026-08-12.csv",
    );
    expect(purchaseOrderFilename(null, "")).toBe("purchase-order-all-export.csv");
  });
});
