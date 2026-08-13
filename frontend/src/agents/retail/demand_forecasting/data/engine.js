/**
 * Re-runs the workbook's formulas over the chain when a Demand lever moves.
 *
 * Deliberately the same shape as `agents/retail/inventory_risk/data/engine.js`,
 * and deliberately fed the same expressions from the same catalogue. Both
 * boards display `Stockout-risk SKUs`; if they computed it two ways they would
 * disagree the moment a slider moved, and a reader with both tabs open would
 * have no way to tell which was wrong.
 *
 * WHAT THE LEVERS REACH
 * Four of the six move something, because four appear as parameters in the
 * catalogue:
 *
 *     demand   f01, scales ADS -> Forecast 7d and days of cover
 *     promo    f01, lifts promo-eligible SKUs only
 *     inbound  f03, scales open PO -> Position -> reorder zone
 *     lead     f05, pushes ROP up  -> reorder zone
 *     safety   f05, pushes ROP up  -> reorder zone
 *
 * `markdown` reaches nothing. The workbook has no markdown term anywhere, and
 * the simulator says so rather than moving a slider that does nothing.
 *
 * Accuracy and Trending do not move either, for the same reason: they are
 * constants typed into the A1 sheet, with no formula to take a lever.
 */

import { evaluate, parse } from "../../../../formulas/expression.js";
import { DEFAULT_DEMAND_LEVERS } from "./contract.js";

const REQUIRED_FORMULAS = [
  "f01-ads-per-store",
  "f03-open-po-per-store",
  "f04-position",
  "f05-rop",
  "f08-forecast-7-days",
];

/** True when nothing has been moved, so the board can skip recomputing. */
export function isDemandBaseline(levers) {
  return Object.keys(DEFAULT_DEMAND_LEVERS).every(
    (key) => Number(levers?.[key] ?? 0) === DEFAULT_DEMAND_LEVERS[key],
  );
}

export function createDemandEngine(formulas, weekFactor) {
  const missing = REQUIRED_FORMULAS.filter((id) => !formulas?.[id]);
  if (missing.length) {
    throw new Error(
      `Demand Forecasting cannot simulate without ${missing.join(", ")}. ` +
        "Rebuild the fixture: python scripts/build_demand_forecasting_fixture.py",
    );
  }

  const ast = Object.fromEntries(
    REQUIRED_FORMULAS.map((id) => [id, parse(formulas[id])]),
  );
  const run = (id, values) => evaluate(ast[id], values);

  return function applyLevers(item, levers = DEFAULT_DEMAND_LEVERS) {
    const lever = { ...DEFAULT_DEMAND_LEVERS, ...levers };

    const ads = run("f01-ads-per-store", {
      base_ads: item.base_ads,
      seasonality: item.seasonality,
      store_size: item.store_size,
      demand_lever: lever.demand,
      promo_eligible: item.promo_eligible,
      promo_lever: lever.promo,
      promo_depth: item.promo_depth,
    });

    const openPo = run("f03-open-po-per-store", {
      open_po_total: item.open_po,
      store_size: item.store_size,
      total_store_size: item.store_size,
      inbound_lever: lever.inbound,
    });

    const position = run("f04-position", {
      on_hand: item.on_hand,
      open_po: openPo,
    });

    const rop = run("f05-rop", {
      ads,
      lead_time_days: item.lead_days,
      lead_time_adjust: lever.lead,
      safety_days: item.safety_days,
      safety_adjust: lever.safety,
    });

    return {
      ...item,
      ads,
      open_po: openPo,
      position,
      rop,
      forecast_7d: run("f08-forecast-7-days", { ads, week_factor: weekFactor }),
      is_stockout_risk: position < rop,
    };
  };
}
