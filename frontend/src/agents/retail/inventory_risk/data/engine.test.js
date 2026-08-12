/*
 * The What-If engine against the workbook.
 *
 * Two questions, and they are not the same question:
 *
 *   1. At zero levers, does the engine return the fixture unchanged? That is
 *      the setting the workbook was calculated at, so agreement means both
 *      engines start from the same place. 800 rows, no tolerance to speak of.
 *
 *   2. With a lever moved, does it still agree? Nothing in (1) can answer
 *      this — every lever appears in the expressions multiplied by zero or
 *      added to nothing, so a flipped sign passes all 800 rows. The workbook
 *      publishes exactly one non-zero scenario, on `What-If · Per Agent`, and
 *      it is the only evidence available that What-If will be right.
 */

import { describe, expect, it } from "vitest";

import { LEVER_DEFINITIONS, STATE_ORDER } from "./contract.js";
import { BASELINE_LEVERS, createEngine, isBaseline } from "./engine.js";
import fixture from "./fixture.json";

const applyLevers = createEngine(fixture.formulas);

const totalsBy = (levers, read) => {
  const totals = new Map();
  for (const item of fixture.items) {
    const row = applyLevers(item, levers);
    totals.set(
      item.vertical_id,
      (totals.get(item.vertical_id) || 0) + read(row),
    );
  }
  return totals;
};

describe("at the workbook's own lever setting", () => {
  it("returns all 800 rows exactly as the fixture holds them", () => {
    const drifted = [];

    for (const item of fixture.items) {
      const row = applyLevers(item, BASELINE_LEVERS);

      // Integers on both sides: these are ROUNDed in the workbook, so an
      // approximate comparison here would hide a real disagreement.
      for (const field of ["position", "rop", "max", "inv_value", "state"]) {
        if (row[field] !== item[field]) {
          drifted.push(`${item.sku_id}.${field}: ${row[field]} ≠ ${item[field]}`);
        }
      }
      for (const field of ["ads", "dos", "at_risk_value", "expiry_units"]) {
        if (Math.abs(row[field] - item[field]) > 1e-6) {
          drifted.push(`${item.sku_id}.${field}: ${row[field]} ≠ ${item[field]}`);
        }
      }
    }

    expect(drifted.slice(0, 5)).toEqual([]);
    expect(drifted).toHaveLength(0);
  });

  it("keeps the flags in step with the state it just derived", () => {
    for (const item of fixture.items) {
      const row = applyLevers(item, BASELINE_LEVERS);

      expect(row.is_stockout_risk).toBe(item.is_stockout_risk);
      expect(row.is_overstock).toBe(item.is_overstock);
      expect(row.is_slow_mover).toBe(item.is_slow_mover);
      expect(row.severity_rank).toBe(STATE_ORDER.indexOf(row.state));
    }
  });

  it("recognises the baseline without recomputing anything", () => {
    expect(isBaseline(BASELINE_LEVERS)).toBe(true);
    expect(isBaseline({})).toBe(true);
    expect(isBaseline({ ...BASELINE_LEVERS, demand: 1 })).toBe(false);
  });
});

describe("with a lever moved", () => {
  const reference = fixture.what_if_reference;
  const scenario = {
    ...BASELINE_LEVERS,
    demand: reference.levers.demand,
    promo: reference.levers.promo,
  };

  it("reproduces the workbook's published +20% demand scenario", () => {
    // Forecast 7d is ADS × the day-of-week weighted week, so the published
    // delta is a statement about f01 under two levers at once.
    const week = fixture.constants.dow_sum;
    const base = totalsBy(BASELINE_LEVERS, (row) => row.ads * week);
    const moved = totalsBy(scenario, (row) => row.ads * week);

    const drifted = [];
    for (const row of reference.by_legal_entity) {
      const delta = moved.get(row.legal_entity_id) - base.get(row.legal_entity_id);
      // The sheet stores the delta as a whole number of units.
      if (Math.abs(delta - row.forecast_delta) > 2) {
        drifted.push(
          `${row.legal_entity_id}: engine ${delta.toFixed(1)}` +
            ` ≠ workbook ${row.forecast_delta}`,
        );
      }
    }

    expect(drifted).toEqual([]);
    expect(reference.by_legal_entity).toHaveLength(8);
  });

  it("pushes each lever the way its label promises", () => {
    // Direction, not magnitude. A flipped sign or a `× 100` where `/ 100`
    // belongs survives every comparison above, all of which sit at zero.
    const sample = fixture.items.slice(0, 120);
    const rise = (lever, read) =>
      sample.every((item) => {
        const low = read(applyLevers(item, { ...BASELINE_LEVERS, [lever]: -2 }));
        const mid = read(applyLevers(item, BASELINE_LEVERS));
        const high = read(applyLevers(item, { ...BASELINE_LEVERS, [lever]: 2 }));
        return low <= mid && mid <= high;
      });

    expect(rise("demand", (row) => row.ads)).toBe(true);
    expect(rise("inbound", (row) => row.open_po)).toBe(true);
    expect(rise("lead", (row) => row.rop)).toBe(true);
    expect(rise("safety", (row) => row.rop)).toBe(true);
  });

  it("holds the reorder floors when a lever pushes lead below one day", () => {
    /*
     * `MAX(1, lead + Δ)` and `MAX(0, safety + Δ)` never bind in the stored
     * workbook — no SKU ships with a lead under 2 or a safety under 1. Pull
     * both levers to their minimum and 75 of 800 SKUs cross a floor, which is
     * the first thing a What-If user reaches and the last thing any
     * zero-lever test can see.
     */
    const levers = { ...BASELINE_LEVERS, lead: -2, safety: -2 };
    let floored = 0;

    for (const item of fixture.items) {
      if (item.lead_days - 2 >= 1 && item.safety_days - 2 >= 0) continue;
      floored += 1;

      const row = applyLevers(item, levers);
      const days =
        Math.max(1, item.lead_days - 2) + Math.max(0, item.safety_days - 2);
      const expected = Math.floor(Math.abs(row.ads * days) + 0.5);

      expect(row.rop).toBe(expected);
    }

    expect(floored).toBeGreaterThan(0);
  });

  it("reclassifies states rather than leaving them where they were", () => {
    // The whole point of the panel: a surge has to move SKUs into the reorder
    // zone, not merely change some numbers underneath an unchanged label.
    const before = fixture.items.filter((item) => item.is_stockout_risk).length;
    const after = fixture.items.filter(
      (item) => applyLevers(item, { ...BASELINE_LEVERS, demand: 40 }).is_stockout_risk,
    ).length;

    expect(after).toBeGreaterThan(before);
  });

  it("leaves the markdown lever declared but inert, and says so", () => {
    // A2 spec 8a lists six levers; the workbook's formulas carry a term for
    // five. Rendering the sixth as if it worked would be the lie.
    const markdown = LEVER_DEFINITIONS.find((lever) => lever.id === "markdown");
    expect(markdown.modelled).toBe(false);

    const item = fixture.items[0];
    expect(applyLevers(item, { ...BASELINE_LEVERS, markdown: 60 })).toEqual(
      applyLevers(item, BASELINE_LEVERS),
    );
  });
});
