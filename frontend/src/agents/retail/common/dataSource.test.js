/*
 * Which source a build reads from.
 *
 * This is one line of logic guarding a whole artefact: `npm run build`
 * produces a bundle that talks to the API, `npm run build:standalone`
 * produces one that carries its own data and needs no server. Getting it
 * backwards ships a file that looks identical and shows an error on every
 * board, or one that quietly reads a frozen snapshot while a reader believes
 * they are looking at the database.
 *
 * The bundler's half of this — dropping the branch that is not taken — shows
 * up as a size difference between the two builds rather than as an assertion
 * here. What is asserted is the rule the bundler folds.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function resolve() {
  vi.resetModules();
  return import("./dataSource.js");
}

describe("the Retail data source", () => {
  it("reads the fixture under Vitest, whatever else is set", async () => {
    // jsdom has no server to answer, so tests are fixture-bound regardless.
    vi.stubEnv("VITE_DATA_SOURCE", "api");
    const { DATA_SOURCE } = await resolve();
    expect(DATA_SOURCE).toBe("fixture");
  });

  it("defaults to the API when nothing asks otherwise", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_DATA_SOURCE", "");
    const { DATA_SOURCE, IS_STANDALONE } = await resolve();
    expect(DATA_SOURCE).toBe("api");
    expect(IS_STANDALONE).toBe(false);
  });

  it("pins to the fixture when the standalone build asks for it", async () => {
    vi.stubEnv("MODE", "standalone");
    vi.stubEnv("VITE_DATA_SOURCE", "fixture");
    const { DATA_SOURCE, IS_STANDALONE } = await resolve();
    expect(DATA_SOURCE).toBe("fixture");
    expect(IS_STANDALONE).toBe(true);
  });

  it("refuses a value it does not recognise instead of guessing", async () => {
    /*
     * A typo must not fall through to the default. "fixtures" quietly
     * building an API bundle is the failure that survives review: the file is
     * the right size, opens fine, and is wrong only once it is in front of
     * someone.
     */
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_DATA_SOURCE", "fixtures");
    await expect(resolve()).rejects.toThrow(/must be "api" or "fixture"/);
  });

  it("is the single definition the three boards share", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_DATA_SOURCE", "fixture");

    const [shared, a1, a2, a3] = await Promise.all([
      import("./dataSource.js"),
      import("../demand_forecasting/data/dashboardData.js"),
      import("../inventory_risk/data/dashboardData.js"),
      import("../replenishment/data/dashboardData.js"),
    ]);

    // Three copies of this expression is what let SCHEMA_VERSION drift and
    // left serializeScope on two boards of three.
    expect(a1.DATA_SOURCE).toBe(shared.DATA_SOURCE);
    expect(a2.DATA_SOURCE).toBe(shared.DATA_SOURCE);
    expect(a3.DATA_SOURCE).toBe(shared.DATA_SOURCE);
  });
});
