/*
 * Where two Retail boards show the same thing, they must show the same number.
 *
 * Demand Forecasting and Inventory Risk both display `Stockout-risk SKUs`, and
 * both list SKUs by id and category. Until now they could not agree: Demand
 * invented four legal entities (two of which — HBA, HME — do not exist in the
 * dataset), twelve categories and four hundred SKUs from a hash, while
 * Inventory Risk read the real eight, 160 and 800. Same word, same user, two
 * numbers, one tab apart.
 *
 * Both now derive from `schema_with_data.json`. These tests are what keeps them
 * there: dimension values are join keys, and a future cross-agent feature
 * ("this SKU is trending AND at stockout risk") is only possible while the
 * codes mean the same thing on both sides.
 *
 * THE TWO BOARDS ARE NO LONGER AT THE SAME GRAIN. Inventory Risk moved to the
 * workbook's ENGINE_STORE grid (16,000 SKU x store rows) so its cards count
 * the population the workbook's own dropdown shows; Demand Forecasting is
 * still chain-net, one row per SKU. So the comparisons below roll A2 up per
 * SKU first, which is the only honest way to ask whether they agree -- and
 * they do, on every flag and every shared parameter.
 */

import { describe, expect, it } from "vitest";

import demandFixture from "./demand_forecasting/data/fixture.json";
import riskFixture from "./inventory_risk/data/fixture.json";

const demandItems = new Map(
  demandFixture.items.map((item) => [item.sku_id, item]),
);
/*
 * A2 is store grain, so a plain `new Map(items.map(...))` would silently keep
 * whichever store came last and compare 5% of the board. These two are built
 * deliberately instead:
 *
 *   riskAttributes -- one row per SKU, for fields that cannot vary by store
 *                     (name, category, vertical).
 *   riskChain      -- every store row summed back to the chain, for the
 *                     quantities A1 holds netted.
 */
const riskAttributes = new Map();
const riskChain = new Map();
for (const item of riskFixture.items) {
  if (!riskAttributes.has(item.sku_id)) riskAttributes.set(item.sku_id, item);

  const netted = riskChain.get(item.sku_id);
  if (netted) {
    netted.position += item.position;
    netted.rop += item.rop;
    netted.on_hand += item.on_hand;
    netted.open_po += item.open_po;
    netted.ads += item.ads;
    netted.rows += 1;
  } else {
    riskChain.set(item.sku_id, {
      position: item.position,
      rop: item.rop,
      on_hand: item.on_hand,
      open_po: item.open_po,
      ads: item.ads,
      rows: 1,
    });
  }
}
const riskItems = riskAttributes;

describe("the two boards share one dataset", () => {
  it("stocks the same 800 SKUs under the same codes", () => {
    expect(demandItems.size).toBe(800);
    expect(riskItems.size).toBe(800);
    // A2 carries each of them once per store it is stocked in.
    expect(riskFixture.items).toHaveLength(16000);
    for (const netted of riskChain.values()) expect(netted.rows).toBe(20);
    expect([...demandItems.keys()].sort()).toEqual([...riskItems.keys()].sort());
  });

  it("puts each SKU in the same category and the same legal entity", () => {
    for (const [sku, demand] of demandItems) {
      const risk = riskItems.get(sku);
      expect(risk.vertical_id).toBe(demand.vertical_id);
      expect(risk.category_id).toBe(demand.category_id);
      expect(risk.name).toBe(demand.name);
    }
  });

  it("offers the same eight legal entities, none of them invented", () => {
    const ids = (fixture) =>
      fixture.filter_options.legal_entities.map((row) => row.value).sort();

    expect(ids(demandFixture)).toEqual(ids(riskFixture));
    expect(ids(demandFixture)).toEqual([
      "DGT", "ELC", "FSH", "GMR", "GRC", "HNB", "HNL", "OMN",
    ]);
  });

  it("offers the same 160 stores and 160 categories", () => {
    const values = (fixture, key) =>
      fixture.filter_options[key].map((row) => row.value).sort();

    expect(values(demandFixture, "stores")).toEqual(values(riskFixture, "stores"));
    expect(values(demandFixture, "categories")).toEqual(
      values(riskFixture, "categories"),
    );
    expect(values(riskFixture, "stores")).toHaveLength(160);
    expect(values(riskFixture, "categories")).toHaveLength(160);
  });
});

describe("the KPI both boards display", () => {
  /*
   * Rolled back to the chain, A2's rows put every one of the 800 SKUs on the
   * same side of its reorder point as A1 does. That is the claim worth
   * keeping: the boards disagree about how many ROWS are in trouble, because
   * they are counting different things, but never about whether a given SKU
   * is.
   */
  it("agrees on stockout-risk, SKU for SKU, once A2 is netted", () => {
    const disagreed = [];
    for (const [sku, demand] of demandItems) {
      const netted = riskChain.get(sku);
      if (demand.is_stockout_risk !== netted.position < netted.rop) {
        disagreed.push(sku);
      }
    }
    expect(disagreed).toEqual([]);
  });

  it("agrees on the chain total, and on the workbook's", () => {
    const demandCount = demandFixture.items.filter(
      (item) => item.is_stockout_risk,
    ).length;
    const riskCount = [...riskChain.values()].filter(
      (netted) => netted.position < netted.rop,
    ).length;

    expect(demandCount).toBe(riskCount);
    expect(riskCount).toBe(345);

    // And both match what the workbook's own A1 sheet types per vertical.
    const workbook = demandFixture.reference_by_vertical.reduce(
      (running, row) => running + row.stockout_risk_skus,
      0,
    );
    expect(demandCount).toBe(workbook);
  });

  it("agrees per legal entity, not only in total", () => {
    for (const row of demandFixture.reference_by_vertical) {
      const demandScoped = demandFixture.items.filter(
        (item) =>
          item.vertical_id === row.legal_entity_id && item.is_stockout_risk,
      ).length;
      const riskScoped = [...riskChain.entries()].filter(
        ([sku, netted]) =>
          riskAttributes.get(sku).vertical_id === row.legal_entity_id &&
          netted.position < netted.rop,
      ).length;

      expect(demandScoped).toBe(row.stockout_risk_skus);
      expect(riskScoped).toBe(row.stockout_risk_skus);
    }
  });
});

describe("the shared model inputs", () => {
  it("gives every SKU the same reorder parameters on both boards", () => {
    for (const [sku, demand] of demandItems) {
      const risk = riskItems.get(sku);
      // Per-SKU inputs cannot vary by store, so these compare row to row.
      // `store_size` is NOT among them any more: A1 carries the vertical's
      // total, A2 carries the individual store's index, and that difference
      // is the grain rather than a disagreement.
      for (const field of [
        "base_ads",
        "seasonality",
        "lead_days",
        "safety_days",
        "promo_eligible",
      ]) {
        expect(risk[field]).toBe(demand[field]);
      }

      // Quantities compare only after A2 is summed back to the chain. ADS,
      // on-hand and open PO reconcile exactly; `position` and `rop` do not,
      // because f04 and f05 ROUND per row and twenty roundings do not add up
      // to one. The drift is well under a unit per store and never crosses a
      // reorder point -- the SKU-for-SKU test above is what proves that.
      const netted = riskChain.get(sku);
      // ADS is carried on both sides and reconciles exactly.
      expect(netted.ads).toBeCloseTo(demand.ads, 6);

      /*
       * The rest reconcile to a ROUNDING bound, not an exact one, and the
       * bound is derived rather than fitted. Summing twenty ROUNDed rows can
       * differ from rounding the chain once by at most
       * `0.5 x 20 + 0.5 = 10.5` units:
       *
       *   position  f04 ROUNDs per row (observed worst drift: 4 units)
       *   rop       f05 the same, through the per-store ADS (worst: 5)
       *   on_hand   A1 has no on-hand column and derives it as
       *             `position - open_po` off an already-ROUNDed position, so
       *             it is one rounding out, not twenty (worst: 0.4993)
       *   open_po   allocated by size share and stored rounded (worst: 0.0017)
       *
       * What matters is not the drift but that it never crosses a reorder
       * point, and the SKU-for-SKU test above is what proves that on all 800.
       */
      const near = (got, want, bound, label) => {
        expect(`${label}: ${Math.abs(got - want) <= bound}`).toBe(
          `${label}: true`,
        );
      };
      near(netted.open_po, demand.open_po, 0.01, `${sku}.open_po`);
      near(netted.on_hand, demand.on_hand, 0.5, `${sku}.on_hand`);
      near(netted.position, demand.position, 10.5, `${sku}.position`);
      near(netted.rop, demand.rop, 10.5, `${sku}.rop`);
    }
  });

  it("reads the same day-of-week constant, which is the workbook's", () => {
    expect(demandFixture.constants.dow_sum).toBe(riskFixture.constants.dow_sum);
    expect(demandFixture.constants.dow_sum).toBe(7.45);
    // The seven daily factors allocate exactly that total, so a daily view
    // rolls back up to the weekly figure the workbook publishes.
    const profile = demandFixture.constants.dow_profile;
    expect(profile).toHaveLength(7);
    expect(profile.reduce((running, value) => running + value, 0)).toBeCloseTo(
      7.45,
      9,
    );
  });

  it("runs the same catalogue expressions where both use one", () => {
    const shared = Object.keys(demandFixture.formulas).filter(
      (id) => id in riskFixture.formulas,
    );
    expect(shared.length).toBeGreaterThanOrEqual(5);
    for (const id of shared) {
      expect(demandFixture.formulas[id]).toBe(riskFixture.formulas[id]);
    }
  });
});
