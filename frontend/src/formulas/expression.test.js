/*
 * The JavaScript evaluator against the Python one.
 *
 * `expression.js` exists because What-If has to re-run the formulas 800 times
 * per slider movement, which is not a thing to do over HTTP. The price of that
 * is a second implementation of the interpreter, and the only thing that keeps
 * the price honest is this file: both evaluators are run over the same worked
 * examples, and any disagreement fails the build.
 *
 * The corpus is not written here. `workedExamples.json` is generated from
 * `resources/formula.md` by `src/formulas/verification_pack.py`, and
 * `backend/tests/test_worked_example_cells.py` already asserts every one of its
 * inputs against the cell it was read from. So these 95 cases are not "some
 * numbers someone picked" — each is a workbook cell, with its address.
 *
 * The expressions are read from `resources/dbtemp/formula.json` rather than
 * from the fixture, deliberately: the fixture carries only the five formulas
 * Inventory Risk uses, and an evaluator that agrees on five out of nineteen is
 * an evaluator nobody has tested.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import workedExamples from "../pages/main/formula_manager/workedExamples.json";
import {
  FormulaError,
  evaluateExpression,
  parse,
  referencedNames,
  tokenize,
} from "./expression.js";

// Read rather than imported: the file sits outside `frontend/`, and Vite will
// not serve a module from there. Vitest runs with the frontend as its root, so
// the store is one level up. `import.meta.url` is not a file:// URL under
// jsdom, which is why this is not a URL.
const STORE_PATH = resolve(process.cwd(), "../resources/dbtemp/formula.json");
const store = JSON.parse(readFileSync(STORE_PATH, "utf-8"));

const corpus = store.formulas.flatMap((formula) =>
  (workedExamples[formula.id] || []).map((example) => ({
    id: formula.id,
    expression: formula.expression,
    ...example,
  })),
);

describe("the corpus itself", () => {
  it("covers every stored formula", () => {
    const covered = new Set(corpus.map((example) => example.id));
    const stored = store.formulas.map((formula) => formula.id);

    // Nineteen transcribed from the workbook's `Formulas` sheet, plus ENGINE
    // columns I, L and N — real workbook formulas the sheet does not list.
    expect(stored).toHaveLength(22);
    for (const id of stored) {
      expect(covered).toContain(id);
    }
  });

  it("carries enough cases to be worth running", () => {
    expect(corpus.length).toBeGreaterThanOrEqual(110);
  });
});

describe("agreement with the Python evaluator", () => {
  it.each(corpus)("$id · $label", (example) => {
    const actual = evaluateExpression(example.expression, example.values);

    if (typeof example.expected === "string") {
      expect(actual).toBe(example.expected);
      return;
    }

    /*
     * The pack records what Excel displays, which is shorter than what the
     * cache holds — ENGINE_STORE!J4 is 29.1668846784 for a documented
     * 29.166885. A relative tolerance is what the Python side uses for the
     * same reason; matching it exactly is the point.
     */
    const tolerance = Math.max(Math.abs(example.expected) * 1e-6, 1e-9);
    expect(Math.abs(actual - example.expected)).toBeLessThanOrEqual(tolerance);
  });
});

describe("Excel semantics that a naive port gets wrong", () => {
  it("rounds half away from zero, not half to even", () => {
    // JS Math.round(-0.5) is -0, Python round(0.5) is 0. Excel says 1 and -1.
    expect(evaluateExpression("ROUND(x)", { x: 0.5 })).toBe(1);
    expect(evaluateExpression("ROUND(x)", { x: 1.5 })).toBe(2);
    expect(evaluateExpression("ROUND(x)", { x: 2.5 })).toBe(3);
    expect(evaluateExpression("ROUND(x)", { x: -0.5 })).toBe(-1);
    expect(evaluateExpression("ROUND(x)", { x: -2.5 })).toBe(-3);
  });

  it("compares text without regard to case", () => {
    expect(evaluateExpression('IF(p = "Y", 1, 0)', { p: "y" })).toBe(1);
    expect(evaluateExpression('IF(p = "Y", 1, 0)', { p: "N" })).toBe(0);
  });

  it("does not evaluate the branch IF did not take", () => {
    // f14 relies on this: its Expiry branch divides by figures that are zero
    // for a Healthy row.
    expect(evaluateExpression("IF(q > 0, t / q, 0)", { q: 0, t: 5 })).toBe(0);
  });

  it("ceilings to a step, defaulting to whole units", () => {
    expect(evaluateExpression("CEILING(x, s)", { x: 13, s: 12 })).toBe(24);
    expect(evaluateExpression("CEILING(x)", { x: 12.1 })).toBe(13);
  });
});

describe("refusals", () => {
  it("rejects native Excel syntax by name", () => {
    expect(() => tokenize("=A1+B1")).toThrow(/Excel syntax/);
    expect(() => tokenize("ENGINE!F6")).toThrow(/sheet-qualified/i);
    expect(() => tokenize("SUM($A$1:$A$9)")).toThrow(/absolute cell anchors/i);
  });

  it("rejects a function that is not on the allow-list", () => {
    expect(() => parse("VLOOKUP(a, b, c)")).toThrow(FormulaError);
  });

  it("rejects the wrong number of arguments", () => {
    expect(() => parse("ROUND(a, b, c)")).toThrow(/1 to 2 argument/);
  });

  it("names a parameter it was not given", () => {
    expect(() => evaluateExpression("a + b", { a: 1 })).toThrow(
      /No value supplied for parameter 'b'/,
    );
  });

  it("refuses to divide by zero rather than returning Infinity", () => {
    expect(() => evaluateExpression("a / b", { a: 1, b: 0 })).toThrow(
      /Division by zero/,
    );
  });
});

describe("referencedNames", () => {
  it("lists what an expression needs, so a caller can check before running", () => {
    const names = referencedNames(parse(store.formulas[0].expression));
    expect([...names].sort()).toEqual([
      "base_ads",
      "demand_lever",
      "promo_depth",
      "promo_eligible",
      "promo_lever",
      "seasonality",
      "store_size",
    ]);
  });
});
