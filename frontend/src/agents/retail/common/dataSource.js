/**
 * Where the Retail boards get their rows — decided once, for all three.
 *
 * This was three identical expressions in three `dashboardData.js` files. That
 * is the shape of bug this codebase keeps paying for: one rule with several
 * homes, correct until somebody edits two of them. It has already cost a
 * SCHEMA_VERSION that drifted apart and a `serializeScope` that existed on two
 * boards of three.
 *
 * WHAT THE TWO VALUES MEAN
 *   "api"      ask the backend, which reads Postgres.
 *   "fixture"  read the JSON checked in beside each board.
 *
 * Both then run the SAME selectors over the SAME shape, which is what makes
 * the switch safe: the builders return rows rather than a finished dashboard,
 * and `backend/tests/test_retail_dashboard_builders.py` asserts field for field
 * that the payload equals the fixture. Nothing on screen moves.
 *
 * WHY A BUILD FLAG AND NOT A RUNTIME TOGGLE
 * `npm run build:standalone` sets `VITE_DATA_SOURCE=fixture` and produces one
 * self-contained HTML file — every board working with no server behind it,
 * which is what a laptop in a meeting room can actually open. A runtime toggle
 * would put a control on screen that changes where numbers come from, and a
 * reader who does not notice it is reading a different dataset than they think.
 * A build decides once and the artefact says which it was.
 *
 * Tests stay on the fixture because jsdom has no server to answer them, not
 * because the two disagree. `import.meta.env.MODE` is Vite's own flag and is
 * "test" under Vitest.
 */

/*
 * `||` rather than `??`, and it matters. An empty assignment in a .env file
 * (`VITE_DATA_SOURCE=`) arrives as "", which is not nullish — `??` would let
 * it through and DATA_SOURCE would be neither "api" nor "fixture", so every
 * board would take the fixture branch of a bundle built to call the API.
 */
const REQUESTED = import.meta.env.VITE_DATA_SOURCE || "";

if (REQUESTED && REQUESTED !== "api" && REQUESTED !== "fixture") {
  // Failing here beats defaulting: a typo would otherwise ship an artefact
  // that silently reads the wrong source and looks completely normal.
  throw new Error(
    `VITE_DATA_SOURCE must be "api" or "fixture", received "${REQUESTED}".`,
  );
}

export const DATA_SOURCE =
  import.meta.env.MODE === "test" ? "fixture" : REQUESTED || "api";

/** True when the bundle carries its own data and needs no backend. */
export const IS_STANDALONE = DATA_SOURCE === "fixture";
