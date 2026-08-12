/**
 * The formula evaluator, ported from `backend/src/formulas/expression.py`.
 *
 * WHY A SECOND COPY EXISTS
 * The What-If panel re-classifies 800 SKUs on every slider movement. Sending
 * that to `POST /api/formulas/{id}/evaluate` would be one request per SKU per
 * formula, so the evaluation happens here instead.
 *
 * What is duplicated is the *interpreter*, not what it interprets. There is no
 * threshold in this file, no state name, no lever name — nothing that could
 * disagree with the workbook about inventory, because it knows nothing about
 * inventory. The rules stay where they were: `resources/dbtemp/formula.json`,
 * one copy, read by both languages.
 *
 * That distinction is the whole argument for this file, and it is only worth
 * anything while the two evaluators agree. `expression.test.js` runs both over
 * the same worked examples and fails if they diverge.
 *
 * TEMPORARY
 * When the Inventory Risk backend builder lands and What-If moves server-side,
 * delete this module rather than leaving it beside the Python one. Two
 * evaluators are defensible while one of them is the only way to answer the
 * question; two evaluators out of habit are not.
 *
 * Grammar, loosest to tightest — identical to the Python original:
 *
 *   expression     := comparison
 *   comparison     := additive (("=" | "<>" | "<" | "<=" | ">" | ">=") additive)*
 *   additive       := multiplicative (("+" | "-") multiplicative)*
 *   multiplicative := unary (("*" | "/") unary)*
 *   unary          := ("-" | "+")* primary
 *   primary        := NUMBER | STRING | NAME | CALL | "(" expression ")"
 *   CALL           := NAME "(" [expression ("," expression)*] ")"
 */

/** name: [min args, max args]; -1 max means variadic. */
const FUNCTIONS = {
  MAX: [1, -1],
  MIN: [1, -1],
  ROUND: [1, 2],
  CEILING: [1, 2],
  IF: [2, 3],
  AND: [1, -1],
  OR: [1, -1],
  NOT: [1, 1],
};

const COMPARISONS = new Set(["=", "<>", "<", "<=", ">", ">="]);

// Sticky so it can be advanced by hand, matching Python's `re.match(text, i)`.
// Alternation order is load-bearing: `<>` must be tried before `<`.
const TOKEN_RE =
  /(?<space>\s+)|(?<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)|(?<string>"[^"]*")|(?<name>[A-Za-z_][A-Za-z0-9_]*)|(?<op><>|<=|>=|[<>=+\-*/])|(?<punct>[(),])/y;

/** Characters that mean someone pasted a native Excel formula. */
const EXCEL_HINTS = {
  "!": "sheet-qualified cell references",
  $: "absolute cell anchors ($)",
  ":": "cell ranges (:)",
  ";": "argument separators (;)",
  "&": "text concatenation (&)",
  "%": "percent signs",
  "^": "exponent operators (^)",
};

export class FormulaError extends Error {}

export function tokenize(expression) {
  if (typeof expression !== "string" || !expression.trim()) {
    throw new FormulaError("Expression is empty.");
  }

  const text = expression.trim();
  if (text.startsWith("=")) {
    throw new FormulaError(
      "Expressions must not start with '=' — that is Excel syntax. " +
        "Write the formula directly, e.g. ROUND(on_hand + open_po).",
    );
  }

  const tokens = [];
  let index = 0;

  while (index < text.length) {
    TOKEN_RE.lastIndex = index;
    const match = TOKEN_RE.exec(text);

    if (match === null || match.index !== index) {
      const character = text[index];
      const hint = EXCEL_HINTS[character];
      if (hint !== undefined) {
        throw new FormulaError(
          `${hint[0].toUpperCase()}${hint.slice(1)} are not supported at ` +
            `position ${index + 1}. Formulas use named parameters only, not ` +
            "Excel cell references.",
        );
      }
      throw new FormulaError(
        `Unexpected '${character}' at position ${index + 1}.`,
      );
    }

    const kind = Object.keys(match.groups).find(
      (group) => match.groups[group] !== undefined,
    );
    const value = match[0];
    const start = index;
    index += value.length;

    if (kind !== "space") {
      tokens.push({ kind, value, position: start });
    }
  }

  if (tokens.length === 0) {
    throw new FormulaError("Expression is empty.");
  }
  return tokens;
}

class Parser {
  constructor(tokens) {
    this.tokens = tokens;
    this.index = 0;
  }

  peek() {
    return this.index < this.tokens.length ? this.tokens[this.index] : null;
  }

  next() {
    const token = this.peek();
    if (token === null) {
      throw new FormulaError("Expression ended unexpectedly.");
    }
    this.index += 1;
    return token;
  }

  accept(kind, ...values) {
    const token = this.peek();
    if (token === null || token.kind !== kind) return null;
    if (values.length && !values.includes(token.value)) return null;
    this.index += 1;
    return token;
  }

  expect(kind, value) {
    const token = this.accept(kind, value);
    if (token === null) {
      const found = this.peek();
      const where = found
        ? `position ${found.position + 1}`
        : "the end of the expression";
      throw new FormulaError(`Expected '${value}' at ${where}.`);
    }
    return token;
  }

  parse() {
    const node = this.comparison();
    const leftover = this.peek();
    if (leftover !== null) {
      throw new FormulaError(
        `Unexpected '${leftover.value}' at position ${leftover.position + 1}.`,
      );
    }
    return node;
  }

  comparison() {
    let node = this.additive();
    for (;;) {
      const token = this.accept("op");
      if (token === null) return node;
      if (!COMPARISONS.has(token.value)) {
        this.index -= 1;
        return node;
      }
      node = ["bin", token.value, node, this.additive()];
    }
  }

  additive() {
    let node = this.multiplicative();
    for (;;) {
      const token = this.accept("op", "+", "-");
      if (token === null) return node;
      node = ["bin", token.value, node, this.multiplicative()];
    }
  }

  multiplicative() {
    let node = this.unary();
    for (;;) {
      const token = this.accept("op", "*", "/");
      if (token === null) return node;
      node = ["bin", token.value, node, this.unary()];
    }
  }

  unary() {
    const token = this.accept("op", "-", "+");
    if (token === null) return this.primary();
    const operand = this.unary();
    return token.value === "+" ? operand : ["neg", operand];
  }

  primary() {
    const token = this.next();

    if (token.kind === "number") return ["num", Number(token.value)];
    if (token.kind === "string") return ["str", token.value.slice(1, -1)];

    if (token.kind === "punct" && token.value === "(") {
      const node = this.comparison();
      this.expect("punct", ")");
      return node;
    }

    if (token.kind === "name") {
      if (this.accept("punct", "(")) return this.call(token);
      return ["name", token.value];
    }

    throw new FormulaError(
      `Unexpected '${token.value}' at position ${token.position + 1}.`,
    );
  }

  call(nameToken) {
    const name = nameToken.value.toUpperCase();
    if (!(name in FUNCTIONS)) {
      const allowed = Object.keys(FUNCTIONS).sort().join(", ");
      throw new FormulaError(
        `Unknown function '${nameToken.value}' at position ` +
          `${nameToken.position + 1}. Allowed functions: ${allowed}.`,
      );
    }

    const args = [];
    if (this.accept("punct", ")") === null) {
      for (;;) {
        args.push(this.comparison());
        if (this.accept("punct", ",")) continue;
        this.expect("punct", ")");
        break;
      }
    }

    const [low, high] = FUNCTIONS[name];
    if (args.length < low || (high !== -1 && args.length > high)) {
      const expected =
        low === high
          ? `${low}`
          : high === -1
            ? `at least ${low}`
            : `${low} to ${high}`;
      throw new FormulaError(
        `${name} takes ${expected} argument(s), got ${args.length}.`,
      );
    }
    return ["call", name, args];
  }
}

/** Parse an expression into an AST, or throw FormulaError. */
export function parse(expression) {
  return new Parser(tokenize(expression)).parse();
}

/** Every parameter name the expression reads. */
export function referencedNames(node) {
  const [kind] = node;
  if (kind === "name") return new Set([node[1]]);
  if (kind === "neg") return referencedNames(node[1]);
  if (kind === "bin") {
    return new Set([...referencedNames(node[2]), ...referencedNames(node[3])]);
  }
  if (kind === "call") {
    const names = new Set();
    for (const argument of node[2]) {
      for (const name of referencedNames(argument)) names.add(name);
    }
    return names;
  }
  return new Set();
}

// -- evaluation --------------------------------------------------------

function asNumber(value, context) {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new FormulaError(`${context} needs a number, got ${display(value)}.`);
}

function truthy(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  throw new FormulaError(`Expected a condition, got the text ${display(value)}.`);
}

function display(value) {
  return typeof value === "string" ? `'${value}'` : String(value);
}

function compare(operator, left, right) {
  let first;
  let second;

  if (typeof left === "string" || typeof right === "string") {
    if (typeof left !== "string" || typeof right !== "string") {
      throw new FormulaError(
        `Cannot compare text with a number: ${display(left)} ${operator} ` +
          `${display(right)}.`,
      );
    }
    // Excel compares text case-insensitively; mirror that so "y" = "Y".
    first = left.toLowerCase();
    second = right.toLowerCase();
    if (operator !== "=" && operator !== "<>") {
      throw new FormulaError(
        `Text can only be compared with '=' or '<>', not '${operator}'.`,
      );
    }
  } else {
    first = asNumber(left, "Comparison");
    second = asNumber(right, "Comparison");
  }

  switch (operator) {
    case "=":
      return first === second;
    case "<>":
      return first !== second;
    case "<":
      return first < second;
    case "<=":
      return first <= second;
    case ">":
      return first > second;
    default:
      return first >= second;
  }
}

/** ROUND with Excel's half-away-from-zero rule (JS rounds half up). */
function excelRound(value, digits = 0) {
  const factor = 10 ** Math.trunc(digits);
  const scaled = value * factor;
  const rounded = Math.floor(Math.abs(scaled) + 0.5);
  return (scaled < 0 ? -rounded : rounded) / factor;
}

function excelCeiling(value, significance = 1) {
  if (significance === 0) return 0;
  return Math.ceil(value / significance) * significance;
}

function callFunction(name, nodeArgs, values) {
  // IF short-circuits: the untaken branch must not be evaluated, so a guard
  // like IF(qty > 0, total / qty, 0) is safe.
  if (name === "IF") {
    if (truthy(evaluateNode(nodeArgs[0], values))) {
      return evaluateNode(nodeArgs[1], values);
    }
    return nodeArgs.length === 3 ? evaluateNode(nodeArgs[2], values) : false;
  }

  if (name === "AND") {
    for (const argument of nodeArgs) {
      if (!truthy(evaluateNode(argument, values))) return false;
    }
    return true;
  }

  if (name === "OR") {
    for (const argument of nodeArgs) {
      if (truthy(evaluateNode(argument, values))) return true;
    }
    return false;
  }

  if (name === "NOT") return !truthy(evaluateNode(nodeArgs[0], values));

  const args = nodeArgs.map((argument) => evaluateNode(argument, values));

  if (name === "MAX") {
    return Math.max(...args.map((item) => asNumber(item, "MAX")));
  }
  if (name === "MIN") {
    return Math.min(...args.map((item) => asNumber(item, "MIN")));
  }
  if (name === "ROUND") {
    const digits = args.length === 2 ? asNumber(args[1], "ROUND") : 0;
    return excelRound(asNumber(args[0], "ROUND"), digits);
  }
  if (name === "CEILING") {
    const step = args.length === 2 ? asNumber(args[1], "CEILING") : 1;
    return excelCeiling(asNumber(args[0], "CEILING"), step);
  }

  throw new FormulaError(`Unknown function ${name}.`);
}

function evaluateNode(node, values) {
  const [kind] = node;

  if (kind === "num" || kind === "str") return node[1];

  if (kind === "name") {
    const name = node[1];
    if (!(name in values)) {
      throw new FormulaError(`No value supplied for parameter '${name}'.`);
    }
    return values[name];
  }

  if (kind === "neg") {
    return -asNumber(evaluateNode(node[1], values), "Negation");
  }

  if (kind === "call") return callFunction(node[1], node[2], values);

  const operator = node[1];
  const left = evaluateNode(node[2], values);
  const right = evaluateNode(node[3], values);

  if (COMPARISONS.has(operator)) return compare(operator, left, right);

  const first = asNumber(left, `Operator '${operator}'`);
  const second = asNumber(right, `Operator '${operator}'`);

  switch (operator) {
    case "+":
      return first + second;
    case "-":
      return first - second;
    case "*":
      return first * second;
    default:
      if (second === 0) throw new FormulaError("Division by zero.");
      return first / second;
  }
}

/** Run a parsed expression against parameter values. */
export function evaluate(node, values) {
  return evaluateNode(node, values);
}

/** Parse and run in one step. */
export function evaluateExpression(expression, values) {
  return evaluate(parse(expression), values);
}
