/**
 * The reorder zone, named once for every Retail board that reports it.
 *
 * WHY THIS FILE EXISTS
 * Agents 1 and 2 both display a "Stockout-risk SKUs" tile, and the project's
 * own rule is that they must answer it identically — if they computed it two
 * ways they would disagree the moment a What-If slider moved, and a reader
 * with both tabs open would have no way to tell which was wrong. A2 carried
 * this set in its own `contract.js`; A1 needed the same two names when its
 * baseline stopped retyping `position < rop`. A second copy is the shape of
 * bug this codebase keeps paying for (see `dataSource.js`), so the set moved
 * here instead and `inventory_risk/data/contract.js` re-exports it.
 *
 * WHAT IT MEANS
 * f07 assigns `Stockout` below `0.6 × ROP` and `Low` below ROP — the first two
 * of its branches — so these two states and the comparison `position < rop`
 * select the same rows by construction. Verified over the live warehouse at
 * both grains: 345 of 800 chain-net rows and 7,090 of 16,000 store rows, with
 * no row disagreeing either way.
 *
 * That equivalence is a property of f07's current branch ORDER, not a law. If
 * a Formula Manager edit ever moves `Expiry` above `Low`, perishable stock
 * that is both below ROP and past its shelf life would read `Expiry` and drop
 * out of this set — which is the behaviour the boards want (that row belongs
 * to markdown, not replenishment), but it would no longer be a synonym for
 * "below the reorder point". Anything that specifically means the comparison
 * should say so; anything that means "the reorder zone the state chain
 * assigns" should use this.
 */
export const REPLENISH_STATES = Object.freeze(["Stockout", "Low"]);
