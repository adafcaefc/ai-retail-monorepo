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
 */

import { describe, expect, it } from "vitest";

import demandFixture from "./demand_forecasting/data/fixture.json";
import riskFixture from "./inventory_risk/data/fixture.json";

const demandItems = new Map(
  demandFixture.items.map((item) => [item.sku_id, item]),
);
const riskItems = new Map(riskFixture.items.map((item) => [item.sku_id, item]));

describe("the two boards share one dataset", () => {
  it("stocks the same 800 SKUs under the same codes", () => {
    expect(demandItems.size).toBe(800);
    expect(riskItems.size).toBe(800);
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
  it("agrees on stockout-risk, SKU for SKU", () => {
    const disagreed = [];
    for (const [sku, demand] of demandItems) {
      if (demand.is_stockout_risk !== riskItems.get(sku).is_stockout_risk) {
        disagreed.push(sku);
      }
    }
    expect(disagreed).toEqual([]);
  });

  it("agrees on the chain total, and on the workbook's", () => {
    const demandCount = demandFixture.items.filter(
      (item) => item.is_stockout_risk,
    ).length;
    const riskCount = riskFixture.items.filter(
      (item) => item.is_stockout_risk,
    ).length;

    expect(demandCount).toBe(riskCount);

    // And both match what the workbook's own A1 sheet types per vertical.
    const workbook = demandFixture.reference_by_vertical.reduce(
      (running, row) => running + row.stockout_risk_skus,
      0,
    );
    expect(demandCount).toBe(workbook);
  });

  it("agrees per legal entity, not only in total", () => {
    for (const row of demandFixture.reference_by_vertical) {
      const scoped = (fixture) =>
        fixture.items.filter(
          (item) =>
            item.vertical_id === row.legal_entity_id && item.is_stockout_risk,
        ).length;

      expect(scoped(demandFixture)).toBe(row.stockout_risk_skus);
      expect(scoped(riskFixture)).toBe(row.stockout_risk_skus);
    }
  });
});

describe("the shared model inputs", () => {
  it("gives every SKU the same reorder parameters on both boards", () => {
    for (const [sku, demand] of demandItems) {
      const risk = riskItems.get(sku);
      for (const field of [
        "base_ads",
        "seasonality",
        "store_size",
        "lead_days",
        "safety_days",
        "promo_eligible",
        "on_hand",
        "open_po",
        "position",
        "rop",
      ]) {
        expect(risk[field]).toBe(demand[field]);
      }
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
