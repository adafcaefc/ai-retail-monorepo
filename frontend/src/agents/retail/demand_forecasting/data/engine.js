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
import { DEFAULT_DEMAND_LEVERS, normalizeDemandLevers } from "./contract.js";
import { REPLENISH_STATES } from "../../common/inventoryStates.js";

const REQUIRED_FORMULAS = [
  "f01-ads-per-store",
  "f03-open-po-per-store",
  "f04-position",
  "f05-rop",
  "f07-inventory-state",
  "f08-forecast-7-days",
  "f20-days-of-supply",
];

/** True when nothing has been moved, so the board can skip recomputing. */
export function isDemandBaseline(levers) {
  return Object.keys(DEFAULT_DEMAND_LEVERS).every(
    (key) => Number(levers?.[key] ?? 0) === DEFAULT_DEMAND_LEVERS[key],
  );
}

/**
 * The dashboard contract currently carries the ROP calculated from the
 * designated Trade Agreement lead time, while its `lead_days` field comes
 * from the SKU master. Those are different workbook inputs. Prefer an
 * explicit designated value when a future payload supplies one; otherwise
 * recover the baseline lead term from the already-loaded baseline ROP so a
 * zero-lever re-run remains the same scenario as the displayed baseline.
 */
export function baselineLeadTimeDays(item) {
  const explicit = Number(item?.designated_lead_days);
  if (Number.isFinite(explicit)) return explicit;

  const ads = Number(item?.ads);
  const rop = Number(item?.rop);
  const safety = Number(item?.safety_days);
  const inferred = rop / ads - safety;
  if (Number.isFinite(inferred) && inferred >= 0) return inferred;

  return Number(item?.lead_days) || 0;
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
    const lever = normalizeDemandLevers(levers);

    const ads = run("f01-ads-per-store", {
      base_ads: item.base_ads,
      seasonality: item.seasonality,
      arch_horizon_factor: item.arch_horizon_factor,
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
      lead_time_days: baselineLeadTimeDays(item),
      lead_time_adjust: lever.lead,
      safety_days: item.safety_days,
      safety_adjust: lever.safety,
    });

    const dos = run("f20-days-of-supply", { ads, position });

    const state = run("f07-inventory-state", {
      position,
      rop,
      days_of_supply: dos,
      perishable: item.perishable,
      shelf_life_days: item.shelf_life_days,
      velocity: item.growth,
    });

    return {
      ...item,
      ads,
      open_po: openPo,
      position,
      rop,
      dos,
      state,
      forecast_7d: run("f08-forecast-7-days", { ads, week_factor: weekFactor }),
      /*
       * The flag follows f07's state rather than re-testing `position < rop`.
       * f07 assigns Stockout below 0.6 x ROP and Low below ROP, so those two
       * states ARE the reorder zone by construction -- a second comparison
       * can drift from f07, reading it off the state cannot. Same rule and
       * same source as `inventory_risk/data/engine.js` and as this board's
       * own Python baseline, so the two boards cannot report a different
       * "Stockout-risk SKUs" under the same levers.
       *
       * `is_trending` is deliberately absent: fc10 reads `is_viral` and
       * `growth_index`, neither of which any lever touches, so the spread
       * above carries the baseline's catalogue-evaluated answer through
       * unchanged rather than re-running a rule that cannot move.
       */
      is_stockout_risk: REPLENISH_STATES.includes(state),
    };
  };
}
