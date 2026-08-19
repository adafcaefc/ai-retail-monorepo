/**
 * Re-runs the workbook's promotion engine when a What-If lever moves.
 *
 * Every figure elsewhere in this folder is read, never derived — that is the
 * rule, and it is what makes the board reconcilable against the A4 Promotion
 * sheet. This module is the one exception: a lever position the workbook never
 * calculated has no stored answer, so the answer has to be computed.
 *
 * The engine knows nothing about thresholds or policy. `fixture.formulas`
 * carries the expressions and `expression.js` runs them; this file only feeds
 * each formula the values it consumes. Swap a constant in `formula.json` and
 * the engine changes behaviour without being edited.
 *
 * Zero levers must return the fixture unchanged. `engine.test.js` asserts that
 * over every promo-eligible SKU, and the fixture builder asserts the same from
 * the Python side before the fixture is written.
 */

import {
  evaluate,
  parse,
  referencedNames,
} from "../../../../formulas/expression.js";
import { BASELINE_LEVERS } from "./contract.js";

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
 * over every promo-eligible SKU, and re-parsing the expressions each time turns
 * a keystroke into thousands of parses.
 *
 * The engine runs two formulas:
 *   f01-ads-per-store sizes the base daily rate the promo uplift multiplies;
 *   f13-incremental-promotion-margin prices the incremental promo margin.
 * f13 reads its own ADS internally (ads × 7 × price), so only f01's lever-aware
 * output is fed forward.
 */
export function createEngine(formulas) {
  const missing = REQUIRED_FORMULAS.filter((id) => !formulas?.[id]);
  if (missing.length) {
    throw new Error(
      `Promotion Effectiveness cannot simulate without ${missing.join(", ")}. ` +
        "Rebuild the fixture: python scripts/build_promotion_effectiveness_fixture.py",
    );
  }

  const ast = Object.fromEntries(
    REQUIRED_FORMULAS.map((id) => [id, parse(formulas[id])]),
  );
  // Names each formula's live text reads, so a parameter added to the catalog
  // (e.g. via the Formula Manager) after this engine was written doesn't
  // crash the board — see `run` below.
  const names = Object.fromEntries(
    REQUIRED_FORMULAS.map((id) => [id, referencedNames(ast[id])]),
  );

  // Defaults any parameter the formula text references but the caller didn't
  // supply to 1 (a neutral multiplicative factor) instead of letting
  // `evaluate` throw. A live formula edit can add a parameter this engine has
  // no way to know about ahead of time; better to keep the board usable and
  // warn than to hard-crash every view that re-runs the formula.
  const run = (id, values) => {
    let safeValues = values;
    for (const name of names[id]) {
      if (!(name in safeValues)) {
        if (safeValues === values) safeValues = { ...values };
        safeValues[name] = 1;
        console.warn(
          `${id} references '${name}', which this engine does not supply. ` +
            "Defaulting to 1 (no-op). The formula catalog likely changed " +
            "without a matching code update.",
        );
      }
    }
    return evaluate(ast[id], safeValues);
  };

  return function applyLevers(item, levers = BASELINE_LEVERS) {
    const lever = { ...BASELINE_LEVERS, ...levers };

    // f01 sizes ADS from the base rate, seasonality, store size and the
    // demand/promo levers. Non-promo SKUs ignore the promo lever by construction.
    // promo_depth is stored as a display percentage; f01 takes it as a fraction.
    const ads = run("f01-ads-per-store", {
      base_ads: item.base_ads,
      seasonality: item.seasonality,
      arch_horizon_factor: item.arch_horizon_factor,
      store_size: item.store_size,
      demand_lever: lever.demand,
      promo_eligible: item.promo_eligible,
      promo_lever: lever.promo,
      promo_depth: (Number(item.promo_depth) || 0) / 100,
    });

    // f13 is the incremental promotion margin. It returns 0 for non-promo SKUs
    // (the IF guards on promo_eligible), so it is safe to run on every item.
    //
    // The fixture carries cannibalisation_pct / promo_funding as DISPLAY
    // percentages (26 meaning 26%), but f13's formula takes them as FRACTIONS
    // (0.26). Convert here so the stored values stay readable and the formula
    // gets what its expression assumes. margin_pct is already a fraction.
    const incrementalMargin = run("f13-incremental-promotion-margin", {
      ads,
      price: item.price,
      margin_pct: item.margin_pct,
      cannibalization: (Number(item.cannibalisation_pct) || 0) / 100,
      promo_eligible: item.promo_eligible,
      promo_funding: (Number(item.promo_funding) || 0) / 100,
    });

    return {
      ...item,
      ads,
      incremental_margin: incrementalMargin,
    };
  };
}

const REQUIRED_FORMULAS = [
  "f01-ads-per-store",
  "f13-incremental-promotion-margin",
];

/**
 * Reconstruct one item at one store, for the Store filter's full item swap.
 *
 * `f01-ads-per-store` is purely multiplicative in `store_size`, and `f13` is
 * linear in `ads` with every other input constant per item regardless of
 * store. So overriding `store_size` with one store's `size_index` — instead
 * of the vertical-wide sum every item already carries — reproduces that
 * store's own `ads` / `incremental_margin` once run back through
 * `createEngine`'s `applyLevers`. Verified against every real ENGINE_STORE
 * row for a promo SKU by the fixture builder's `verify_store_split`, to
 * floating-point precision.
 *
 * This is only needed for the Store filter's item-population swap. The
 * by-store/cluster/channel dimension charts don't call this — they use the
 * cheaper proportional split in `selectors.js`'s `computeByStore` directly.
 */
export function atStore(item, store) {
  return { ...item, store_size: Number(store?.size_index) || 0 };
}
