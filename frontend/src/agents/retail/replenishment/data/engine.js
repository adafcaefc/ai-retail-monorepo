/**
 * Re-runs the workbook's order engine when a What-If lever moves.
 *
 * Same exception, same justification as `inventory_risk/data/engine.js`: every
 * other figure on this board is read from the workbook, but a lever position
 * the workbook never calculated has no stored answer to read.
 *
 * And the same discipline. There is no threshold here, no pack rule, no price
 * policy — `fixture.formulas` carries nine expressions and `expression.js` runs
 * them. This file only decides the order, because each formula consumes the one
 * above it:
 *
 *     f01 ads -> f03 open PO -> f04 position -> f05 ROP / f06 Max
 *                            -> f09 order (sales units)
 *                            -> f10 buy (whole packs)
 *                            -> f11 order value
 *
 * Zero levers must return the fixture unchanged. `engine.test.js` asserts that
 * across all 800 lines — including both order values and the vendor saving,
 * which are read columns at baseline and computed ones under a scenario. If
 * those two paths ever disagree, the board would silently change its own
 * numbers the moment a slider was touched and put back.
 *
 * Delete this when the backend builder can answer scoped What-If queries.
 */

import { evaluate, parse } from "../../../../formulas/expression.js";
import { BASELINE_LEVERS } from "./contract.js";

export { BASELINE_LEVERS };

/** True when nothing has been moved, so the board can skip recomputing. */
export function isBaseline(levers) {
  return Object.keys(BASELINE_LEVERS).every(
    (key) => Number(levers?.[key] ?? 0) === BASELINE_LEVERS[key],
  );
}

const REQUIRED_FORMULAS = [
  "f01-ads-per-store",
  "f03-open-po-per-store",
  "f04-position",
  "f05-rop",
  "f06-maximum-inventory",
  "f09-order-quantity-sales-units",
  "f10-order-quantity-purchase-units",
  "f11-order-value",
  "f20-days-of-supply",
];

/**
 * Bind an engine to one fixture's expressions.
 *
 * Parsed once rather than per line: a slider drag re-runs this over 800 lines,
 * and re-parsing nine expressions each time turns a keystroke into 7,200
 * parses.
 */
export function createEngine(formulas) {
  const missing = REQUIRED_FORMULAS.filter((id) => !formulas?.[id]);
  if (missing.length) {
    throw new Error(
      `Replenishment cannot simulate without ${missing.join(", ")}. ` +
        "Rebuild the fixture: python scripts/build_replenishment_fixture.py",
    );
  }

  const ast = Object.fromEntries(
    REQUIRED_FORMULAS.map((id) => [id, parse(formulas[id])]),
  );
  const run = (id, values) => evaluate(ast[id], values);

  return function applyLevers(line, levers = BASELINE_LEVERS) {
    const lever = { ...BASELINE_LEVERS, ...levers };

    const ads = run("f01-ads-per-store", {
      base_ads: line.base_ads,
      seasonality: line.seasonality,
      arch_horizon_factor: line.arch_horizon_factor,
      store_size: line.store_size,
      demand_lever: lever.demand,
      promo_eligible: line.promo_eligible,
      promo_lever: lever.promo,
      promo_depth: line.promo_depth,
    });

    const openPo = run("f03-open-po-per-store", {
      // A chain-net line already covers every store, so there is no allocation
      // left to do and the size ratio is one.
      open_po_total: line.open_po,
      store_size: line.store_size,
      total_store_size: line.store_size,
      inbound_lever: lever.inbound,
    });

    const position = run("f04-position", {
      on_hand: line.on_hand,
      open_po: openPo,
    });

    const reorder = {
      ads,
      lead_time_days: line.lead_days,
      lead_time_adjust: lever.lead,
      safety_days: line.safety_days,
      safety_adjust: lever.safety,
    };
    const rop = run("f05-rop", reorder);
    const max = run("f06-maximum-inventory", {
      ...reorder,
      horizon_coverage: line.horizon_coverage,
    });

    const orderSales = run("f09-order-quantity-sales-units", {
      position,
      rop,
      max_inventory: max,
    });

    const orderBuy = run("f10-order-quantity-purchase-units", {
      order_sales_units: orderSales,
      pack_factor: line.pack_factor,
    });

    /*
     * The two order values, priced the way the workbook prices each of them.
     *
     * Cost is f11 as written: whole packs at the trade-agreement price, which
     * is what the purchase order actually costs. Retail is `ENGINE!P`, which
     * prices the *shortfall* at the selling price and never rounds up to a
     * pack — so it goes through f11 with a pack factor of one, because sales
     * units need no conversion. Both reproduce the fixture exactly at zero
     * levers, over all 345 lines that carry an order.
     */
    const valueCost = run("f11-order-value", {
      order_buy_units: orderBuy,
      pack_factor: line.pack_factor,
      price: line.unit_price_trade,
    });
    const valueRetail = run("f11-order-value", {
      order_buy_units: orderSales,
      pack_factor: 1,
      price: line.unit_price_retail,
    });

    /*
     * What switching this line to its cheapest quote would recover: the same
     * order, priced twice. Stated as a difference of two f11 evaluations
     * rather than as a margin formula of its own, so no new pricing rule is
     * born in JavaScript. Both forms reproduce the workbook's stored column
     * over all 345 lines; this one keeps the arithmetic in the catalogue.
     */
    const valueAtBest = run("f11-order-value", {
      order_buy_units: orderBuy,
      pack_factor: line.pack_factor,
      price: line.best_price,
    });

    return {
      ...line,
      ads,
      open_po: openPo,
      position,
      rop,
      max,
      dos: run("f20-days-of-supply", { ads, position }),
      order_qty_sales: orderSales,
      order_qty_buy: orderBuy,
      order_value_cost: valueCost,
      order_value_retail: valueRetail,
      saving_vs_designated: valueCost - valueAtBest,
      /*
       * Reorder follows `Position < ROP`, which is f09's own condition. A2
       * decides the same question through the state machine and lands on the
       * same 345 rows; `crossModule.test.js` holds the two boards to it.
       */
      is_reorder: position < rop,
    };
  };
}
