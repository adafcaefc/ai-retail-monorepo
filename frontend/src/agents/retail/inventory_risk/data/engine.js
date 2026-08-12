/**
 * Re-runs the workbook's engine over the chain when a What-If lever moves.
 *
 * Every dashboard figure elsewhere in this folder is read, never derived —
 * that is the rule, and it is what makes the board reconcilable against the
 * `A2 Inventory Risk` sheet. This module is the one exception the rule always
 * needed: a lever position the workbook never calculated has no stored answer
 * to read, so the answer has to be computed.
 *
 * It computes it without knowing anything. There is no threshold here, no
 * state name, no policy. `fixture.formulas` carries ten expressions and
 * `expression.js` runs them; this file only decides the order, because each
 * formula consumes the one above it. Swap a threshold in `formula.json` and
 * this module changes behaviour without being edited, which is the point.
 *
 * Zero levers must return the fixture unchanged. `engine.test.js` asserts that
 * over all 800 rows, and `build_inventory_risk_fixture.py` asserts the same
 * thing from the other side before the fixture is written. A lever at zero is
 * the setting the workbook itself was calculated at (`Constants` B16–B21), so
 * agreement there means the two engines start from the same place.
 *
 * Delete this when the backend builder can answer scoped What-If queries. Two
 * implementations are defensible while one of them is the only way to get an
 * answer; two out of habit are not.
 */

import { evaluate, parse } from "../../../../formulas/expression.js";
import {
  BASELINE_LEVERS,
  HEALTHY_STATE,
  REPLENISH_STATES,
  STATE_ORDER,
} from "./contract.js";

export { BASELINE_LEVERS };

/** True when nothing has been moved, so the board can skip recomputing. */
export function isBaseline(levers) {
  return Object.keys(BASELINE_LEVERS).every(
    (key) => Number(levers?.[key] ?? 0) === BASELINE_LEVERS[key],
  );
}

/**
 * Bind an engine to one fixture's expressions.
 *
 * Parsing is done once here rather than per row: a slider drag re-runs this
 * over 800 items, and re-parsing ten expressions each time turns a keystroke
 * into 8,000 parses.
 */
export function createEngine(formulas) {
  const missing = REQUIRED_FORMULAS.filter((id) => !formulas?.[id]);
  if (missing.length) {
    throw new Error(
      `Inventory Risk cannot simulate without ${missing.join(", ")}. ` +
        "Rebuild the fixture: python scripts/build_inventory_risk_fixture.py",
    );
  }

  const ast = Object.fromEntries(
    REQUIRED_FORMULAS.map((id) => [id, parse(formulas[id])]),
  );
  const run = (id, values) => evaluate(ast[id], values);

  return function applyLevers(item, levers = BASELINE_LEVERS) {
    const lever = { ...BASELINE_LEVERS, ...levers };

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
      // A chain-net row already covers every store, so there is no allocation
      // left to do and the size ratio is one.
      open_po_total: item.open_po,
      store_size: item.store_size,
      total_store_size: item.store_size,
      inbound_lever: lever.inbound,
    });

    const position = run("f04-position", {
      on_hand: item.on_hand,
      open_po: openPo,
    });

    const reorder = {
      ads,
      lead_time_days: item.lead_days,
      lead_time_adjust: lever.lead,
      safety_days: item.safety_days,
      safety_adjust: lever.safety,
    };
    const rop = run("f05-rop", reorder);
    const max = run("f06-maximum-inventory", reorder);

    const dos = run("f20-days-of-supply", { ads, position });

    const state = run("f07-inventory-state", {
      position,
      rop,
      perishable: item.perishable,
      days_of_supply: dos,
      shelf_life_days: item.shelf_life_days,
      velocity: item.growth,
    });

    return {
      ...item,
      ads,
      open_po: openPo,
      position,
      rop,
      max,
      dos,
      state,
      severity_rank: STATE_ORDER.indexOf(state),
      inv_value: run("f21-inventory-value", {
        position,
        price: item.price,
      }),
      at_risk_value: run("f12-at-risk-value", {
        state,
        position,
        price: item.price,
      }),
      expiry_units: run("f22-expiry-units", {
        perishable: item.perishable,
        position,
        ads,
        shelf_life_days: item.shelf_life_days,
      }),
      /*
       * The KPI flags follow the state rather than re-testing a threshold —
       * the same choice the fixture builder makes, and for the same reason:
       * a card that disagrees with the chart beneath it is worse than either
       * number alone. `Stockout` and `Low` are exactly the rows below ROP, by
       * construction of f07, so the reorder zone is those two states.
       */
      is_stockout_risk: REPLENISH_STATES.includes(state),
      is_overstock: state === "Overstock",
      is_slow_mover: state === "Slow-mover",
      next_agent: REPLENISH_STATES.includes(state) ? "3 Replenish" : "5 Markdown",
      is_healthy: state === HEALTHY_STATE,
    };
  };
}

const REQUIRED_FORMULAS = [
  "f01-ads-per-store",
  "f03-open-po-per-store",
  "f04-position",
  "f05-rop",
  "f06-maximum-inventory",
  "f07-inventory-state",
  "f12-at-risk-value",
  "f20-days-of-supply",
  "f21-inventory-value",
  "f22-expiry-units",
];
