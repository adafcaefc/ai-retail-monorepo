/**
 * Re-runs the workbook's engine when a What-If lever moves, then re-derives
 * every assortment measure from the new position.
 *
 * The productivity chain, verified numerically against all 800 chain rows
 * before this was written (each held to ratio 1.0000):
 *
 *     contribution/day = ADS x Price x Margin %
 *     weekly GMV       = ADS x 7 x Price
 *     margin (Rp)      = weekly GMV x Margin %   ( = contribution/day x 7 )
 *     GMROI            = margin (Rp) / inventory value
 *
 * `contribution/day` summed per SKU across its stores equals the chain
 * figure computed this way, because a store's ADS is the chain ADS split by
 * store size and the sizes sum to `sum_vert_size` — which is exactly the
 * `store_size` f01 reads here. That is why one chain-grain evaluation
 * reproduces the store-grain sum the fixture ships.
 *
 * CLASSIFICATION IS RE-DERIVED, NOT CARRIED. A lever that lifts a tail SKU's
 * contribution above the cutoff genuinely changes its verdict, so the
 * delist/grow/hold decision is recomputed here against the SAME thresholds
 * the fixture was built with (`fixture.classification_thresholds`) — frozen
 * cutoffs, not re-percentiled per scenario. Re-percentiling would make a
 * quarter of the range "tail" no matter how well it performed, which would
 * report no change at all.
 */

import { evaluate, parse } from "../../../../formulas/expression.js";
import { BASELINE_LEVERS, DELIST_STATES, HEALTHY_STATE } from "./contract.js";

export { BASELINE_LEVERS };

/** True when nothing has been moved, so the board can skip recomputing. */
export function isBaseline(levers) {
  return Object.keys(BASELINE_LEVERS).every(
    (key) => Number(levers?.[key] ?? 0) === BASELINE_LEVERS[key],
  );
}

/**
 * Bind an engine to one fixture's expressions and classification cutoffs.
 * Parsing happens once here, not per row — a slider drag re-runs this over
 * 800 items.
 *
 * @param {Record<string, string>} formulas
 * @param {{p25_gmroi_chain: number, p25_contribution_chain: number,
 *          p75_gmroi_healthy: number, p75_contribution_healthy: number}} thresholds
 */
export function createEngine(formulas, thresholds = {}) {
  const missing = REQUIRED_FORMULAS.filter((id) => !formulas?.[id]);
  if (missing.length) {
    throw new Error(
      `Assortment Optimization cannot simulate without ${missing.join(", ")}. ` +
        "Rebuild the fixture: python scripts/build_assortment_optimization_fixture.py",
    );
  }

  const ast = Object.fromEntries(REQUIRED_FORMULAS.map((id) => [id, parse(formulas[id])]));
  const run = (id, values) => evaluate(ast[id], values);

  const p25Gmroi = Number(thresholds.p25_gmroi_chain) || 0;
  const p25Contribution = Number(thresholds.p25_contribution_chain) || 0;
  const p75GmroiHealthy = Number(thresholds.p75_gmroi_healthy) || 0;
  const p75ContributionHealthy = Number(thresholds.p75_contribution_healthy) || 0;

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

    const invValue = run("f21-inventory-value", { position, price: item.price });

    // The productivity chain — see the module docstring for the verification.
    const contributionPerDay = ads * item.price * item.margin_pct;
    const weeklyGmv = ads * 7 * item.price;
    const marginRp = weeklyGmv * item.margin_pct;
    const gmroi = invValue ? marginRp / invValue : 0;

    const isTail = contributionPerDay <= p25Contribution;
    const isDelist = DELIST_STATES.includes(state) || gmroi <= p25Gmroi || isTail;
    const isGrow =
      state === HEALTHY_STATE &&
      contributionPerDay >= p75ContributionHealthy &&
      gmroi >= p75GmroiHealthy &&
      item.growth >= 1.0;
    const classification = isGrow && !isDelist ? "grow" : isDelist ? "delist" : "hold";

    return {
      ...item,
      ads,
      open_po: openPo,
      position,
      rop,
      max,
      dos,
      state,
      inv_value: invValue,
      weekly_gmv: weeklyGmv,
      margin_rp: marginRp,
      gmroi,
      contribution_per_day: contributionPerDay,
      is_tail: isTail,
      classification,
      /*
       * `best_action_tab` is deliberately NOT recomputed here. Its three
       * delist sub-tabs depend on chain-wide vendor counts and per-category
       * delist shares — population facts, not row facts, so a per-row engine
       * cannot know them. `selectors.js` reassigns the tabs after driving
       * every row, which is the only place the whole population is in hand.
       */
      best_action_tab: null,
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
  "f20-days-of-supply",
  "f21-inventory-value",
];
