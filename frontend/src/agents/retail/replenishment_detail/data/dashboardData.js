/**
 * Where Replenishment Detail gets its rows: the API, or an error.
 *
 * There is deliberately NO fixture on this board, and no `DATA_SOURCE` branch.
 * Its five siblings each carry a checked-in `fixture.json` so the standalone
 * build works with no server; this one does not, which has two consequences
 * worth stating rather than discovering:
 *
 *   1. A failed request propagates to the caller's error state. It is never
 *      swapped for demo data — silently substituting a fixture for a real
 *      backend failure reads as the board working when it is not. That is the
 *      policy the Pricing & Markdown board was corrected to in `13b2cc7`.
 *   2. `npm run build:standalone` produces an artefact in which this board
 *      shows its error state. It is the one board that needs a backend.
 *
 * Because `common/dataSource.js` forces `DATA_SOURCE` to "fixture" under
 * Vitest, component tests here mock `fetchDashboard` rather than relying on a
 * bundled payload.
 */

import { fetchDashboard } from "../../../../api/dashboard.js";
import {
  AGENT_ID,
  normalizeReplenishmentDetailDashboard,
  serializeScope,
} from "./contract.js";
import { buildDashboardFromRows } from "./selectors.js";

export async function loadReplenishmentDetailDashboard(scope = {}) {
  const rows = await fetchDashboard(AGENT_ID, serializeScope(scope));
  // The scope narrows the REQUEST (two filters, server-side). It deliberately
  // does not narrow the response here — the board owns client-side filtering,
  // and doing it in both places is what once made "All lines" return nothing.
  return normalizeReplenishmentDetailDashboard(buildDashboardFromRows(rows));
}
