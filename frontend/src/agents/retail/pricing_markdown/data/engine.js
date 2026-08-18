/**
 * Re-runs the workbook's state-classification cascade when a What-If lever
 * moves, then re-derives at-risk and recoverable value from the new state.
 *
 * This is the same cascade `inventory_risk/data/engine.js` runs (f01 through
 * f07, plus f12/f20/f21/f22). f23 and f14 are the additions, run on top of
 * the re-derived state/position/ads/max to get `recoverable_value` — a lever
 * position the workbook never calculated, so unlike the shipped baseline
 * (summed from ENGINE_STORE's own resolved columns), this one genuinely has
 * to be computed.
 *
 * f14-recoverable-at-risk-value takes {gross, state, elasticity,
 * markdown_lever} — it is NOT a function of position/ads/shelf_life/price
 * directly, those feed f23-markdown-at-risk-gross, whose `gross` output is
 * f14's own first input. f14 is also the one formula in this cascade that
 * reads the `markdown` lever (Constants B18) — see contract.js's
 * LEVER_DEFINITIONS, where it is the only lever marked `modelled: true`.
 *
 * Zero levers must return the fixture's state/candidacy unchanged (its
 * money figures may drift by the same floating-point noise
 * inventory_risk's own engine tolerates, since f12/f23/f14 here re-derive
 * from re-derived inputs rather than reading the shipped SUMIFS total).
 */

import { evaluate, parse } from "../../../../formulas/expression.js";
import { BASELINE_LEVERS, CANDIDATE_STATES } from "./contract.js";

export { BASELINE_LEVERS };

/** True when nothing has been moved, so the board can skip recomputing. */
export function isBaseline(levers) {
  return Object.keys(BASELINE_LEVERS).every(
    (key) => Number(levers?.[key] ?? 0) === BASELINE_LEVERS[key],
  );
}

/**
 * A5 spec section 7's markdownClassify, mirrored from
 * scripts/build_pricing_markdown_fixture.py's classify(). Not a new
 * threshold: `state` already came from f07, and "open PO exists" is a plain
 * field read — the same kind of state-derived boolean
 * inventory_risk's engine already computes (`is_overstock`, `is_slow_mover`).
 */
function classifyBestActionTab(state, openPo) {
  if (state === "Expiry") return "expiry_markdown";
  if (state === "Overstock") return openPo > 0 ? "suppress_reorder" : "overstock_clearance";
  if (state === "Slow-mover") return "slow_mover_price_cut";
  return null;
}

/**
 * Bind an engine to one fixture's expressions. Parsing happens once here,
 * not per row — a slider drag re-runs this over 800 items.
 */
export function createEngine(formulas) {
  const missing = REQUIRED_FORMULAS.filter((id) => !formulas?.[id]);
  if (missing.length) {
    throw new Error(
      `Pricing & Markdown cannot simulate without ${missing.join(", ")}. ` +
        "Rebuild the fixture: python scripts/build_pricing_markdown_fixture.py",
    );
  }

  const ast = Object.fromEntries(REQUIRED_FORMULAS.map((id) => [id, parse(formulas[id])]));
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
      open_po_total: item.open_po,
      store_size: item.store_size,
      total_store_size: item.total_store_size ?? item.store_size,
      inbound_lever: lever.inbound,
    });

    const position = run("f04-position", { on_hand: item.on_hand, open_po: openPo });

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

    const atRiskValue = run("f12-at-risk-value", { state, position, price: item.price });
    const gross = run("f23-markdown-at-risk-gross", {
      state,
      position,
      ads,
      shelf_life_days: item.shelf_life_days,
      max_inventory: max,
      price: item.price,
    });
    const recoverableValue = run("f14-recoverable-at-risk-value", {
      gross,
      state,
      elasticity: item.elasticity,
      markdown_lever: lever.markdown,
    });
    const isCandidate = CANDIDATE_STATES.includes(state);

    return {
      ...item,
      ads,
      open_po: openPo,
      position,
      rop,
      max,
      dos,
      state,
      at_risk_value: atRiskValue,
      recoverable_value: recoverableValue,
      write_off_value: Math.max(0, atRiskValue - recoverableValue),
      is_markdown_candidate: isCandidate,
      best_action_tab: isCandidate ? classifyBestActionTab(state, openPo) : null,
      inv_value: run("f21-inventory-value", { position, price: item.price }),
      expiry_units: run("f22-expiry-units", {
        perishable: item.perishable,
        position,
        ads,
        shelf_life_days: item.shelf_life_days,
      }),
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
  "f14-recoverable-at-risk-value",
  "f20-days-of-supply",
  "f21-inventory-value",
  "f22-expiry-units",
  "f23-markdown-at-risk-gross",
];
