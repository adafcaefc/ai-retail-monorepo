"""Excel-free formula expressions: tokenize, parse, evaluate.

Formulas are arithmetic over *named parameters* -- never Excel cell
references. `resources/formula.md` documents the workbook originals in native
Excel, but those are reference material only: sheet names, `!` and `$` anchors
are rejected here on purpose, with a message that says so.

Nothing in this module calls `eval()` or `ast.parse()`. A fixed grammar is
tokenized, parsed into a small tuple AST, and walked against an allow-list of
functions -- the same guarded-parse shape as the SQL allow-listing in
`src/llm/agents/common/tools/freeform_query.py`.

Grammar (loosest to tightest):

    expression  := comparison
    comparison  := additive (("=" | "<>" | "<" | "<=" | ">" | ">=") additive)*
    additive    := multiplicative (("+" | "-") multiplicative)*
    multiplicative := unary (("*" | "/") unary)*
    unary       := ("-" | "+")* primary
    primary     := NUMBER | STRING | NAME | CALL | "(" expression ")"
    CALL        := NAME "(" [expression ("," expression)*] ")"
"""

from __future__ import annotations

import math
import re

from typing import Any

# Generic maths, not Excel-specific. Names are matched case-insensitively but
# are conventionally written upper-case in stored expressions.
FUNCTIONS: dict[str, tuple[int, int]] = {
    # name: (min args, max args); -1 max means variadic
    "MAX": (1, -1),
    "MIN": (1, -1),
    "ROUND": (1, 2),
    "CEILING": (1, 2),
    "IF": (2, 3),
    "AND": (1, -1),
    "OR": (1, -1),
    "NOT": (1, 1),
}

COMPARISONS = frozenset({"=", "<>", "<", "<=", ">", ">="})

_TOKEN_RE = re.compile(
    r"""
      (?P<space>\s+)
    | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
    | (?P<string>"[^"]*")
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<op><>|<=|>=|[<>=+\-*/])
    | (?P<punct>[(),])
    """,
    re.VERBOSE,
)

# Characters that mean the author pasted a native Excel formula.
_EXCEL_HINTS = {
    "!": "sheet-qualified cell references",
    "$": "absolute cell anchors ($)",
    ":": "cell ranges (:)",
    ";": "argument separators (;)",
    "&": "text concatenation (&)",
    "%": "percent signs",
    "^": "exponent operators (^)",
}


class Token:
    __slots__ = ("kind", "value", "position")

    def __init__(self, kind: str, value: str, position: int) -> None:
        self.kind = kind
        self.value = value
        self.position = position

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind}, {self.value!r}, {self.position})"


def tokenize(expression: str) -> list[Token]:
    """Split an expression into tokens, or raise ValueError."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Expression is empty.")

    text = expression.strip()
    if text.startswith("="):
        raise ValueError(
            "Expressions must not start with '=' -- that is Excel syntax. "
            "Write the formula directly, e.g. ROUND(on_hand + open_po)."
        )

    tokens: list[Token] = []
    index = 0
    while index < len(text):
        match = _TOKEN_RE.match(text, index)
        if match is None:
            character = text[index]
            hint = _EXCEL_HINTS.get(character)
            if hint is not None:
                raise ValueError(
                    f"{hint.capitalize()} are not supported at position {index + 1}. "
                    "Formulas use named parameters only, not Excel cell references."
                )
            raise ValueError(
                f"Unexpected character {character!r} at position {index + 1}."
            )

        kind = match.lastgroup
        value = match.group()
        index = match.end()
        if kind == "space":
            continue
        tokens.append(Token(kind, value, match.start()))

    if not tokens:
        raise ValueError("Expression is empty.")
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._index = 0

    # -- token helpers -------------------------------------------------

    def _peek(self) -> Token | None:
        if self._index < len(self._tokens):
            return self._tokens[self._index]
        return None

    def _next(self) -> Token:
        token = self._peek()
        if token is None:
            raise ValueError("Expression ended unexpectedly.")
        self._index += 1
        return token

    def _accept(self, kind: str, *values: str) -> Token | None:
        token = self._peek()
        if token is None or token.kind != kind:
            return None
        if values and token.value not in values:
            return None
        self._index += 1
        return token

    def _expect(self, kind: str, value: str) -> Token:
        token = self._accept(kind, value)
        if token is None:
            found = self._peek()
            where = (
                f"position {found.position + 1}" if found else "the end of the expression"
            )
            raise ValueError(f"Expected {value!r} at {where}.")
        return token

    # -- grammar -------------------------------------------------------

    def parse(self) -> tuple:
        node = self._comparison()
        leftover = self._peek()
        if leftover is not None:
            raise ValueError(
                f"Unexpected {leftover.value!r} at position {leftover.position + 1}."
            )
        return node

    def _comparison(self) -> tuple:
        node = self._additive()
        while True:
            token = self._accept("op")
            if token is None:
                return node
            if token.value not in COMPARISONS:
                self._index -= 1
                return node
            node = ("bin", token.value, node, self._additive())

    def _additive(self) -> tuple:
        node = self._multiplicative()
        while True:
            token = self._accept("op", "+", "-")
            if token is None:
                return node
            node = ("bin", token.value, node, self._multiplicative())

    def _multiplicative(self) -> tuple:
        node = self._unary()
        while True:
            token = self._accept("op", "*", "/")
            if token is None:
                return node
            node = ("bin", token.value, node, self._unary())

    def _unary(self) -> tuple:
        token = self._accept("op", "-", "+")
        if token is None:
            return self._primary()
        operand = self._unary()
        if token.value == "+":
            return operand
        return ("neg", operand)

    def _primary(self) -> tuple:
        token = self._next()

        if token.kind == "number":
            return ("num", float(token.value))

        if token.kind == "string":
            return ("str", token.value[1:-1])

        if token.kind == "punct" and token.value == "(":
            node = self._comparison()
            self._expect("punct", ")")
            return node

        if token.kind == "name":
            if self._accept("punct", "("):
                return self._call(token)
            return ("name", token.value)

        raise ValueError(
            f"Unexpected {token.value!r} at position {token.position + 1}."
        )

    def _call(self, name_token: Token) -> tuple:
        name = name_token.value.upper()
        if name not in FUNCTIONS:
            allowed = ", ".join(sorted(FUNCTIONS))
            raise ValueError(
                f"Unknown function {name_token.value!r} at position "
                f"{name_token.position + 1}. Allowed functions: {allowed}."
            )

        arguments: list[tuple] = []
        if self._accept("punct", ")") is None:
            while True:
                arguments.append(self._comparison())
                if self._accept("punct", ","):
                    continue
                self._expect("punct", ")")
                break

        low, high = FUNCTIONS[name]
        count = len(arguments)
        if count < low or (high != -1 and count > high):
            expected = f"{low}" if low == high else (
                f"at least {low}" if high == -1 else f"{low} to {high}"
            )
            raise ValueError(
                f"{name} takes {expected} argument(s), got {count}."
            )
        return ("call", name, arguments)


def parse(expression: str) -> tuple:
    """Parse an expression into an AST, or raise ValueError."""
    return _Parser(tokenize(expression)).parse()


def referenced_names(node: tuple) -> set[str]:
    """Every parameter name the expression reads."""
    kind = node[0]
    if kind == "name":
        return {node[1]}
    if kind == "neg":
        return referenced_names(node[1])
    if kind == "bin":
        return referenced_names(node[2]) | referenced_names(node[3])
    if kind == "call":
        names: set[str] = set()
        for argument in node[2]:
            names |= referenced_names(argument)
        return names
    return set()


# -- evaluation --------------------------------------------------------


def _number(value: Any, context: str) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"{context} needs a number, got {value!r}.")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    raise ValueError(f"Expected a condition, got the text {value!r}.")


def _compare(operator: str, left: Any, right: Any) -> bool:
    # Excel compares text case-insensitively; mirror that so "y" = "Y".
    if isinstance(left, str) or isinstance(right, str):
        if not (isinstance(left, str) and isinstance(right, str)):
            raise ValueError(
                f"Cannot compare text with a number: {left!r} {operator} {right!r}."
            )
        first: Any = left.casefold()
        second: Any = right.casefold()
        if operator not in {"=", "<>"}:
            raise ValueError(
                f"Text can only be compared with '=' or '<>', not {operator!r}."
            )
    else:
        first = _number(left, "Comparison")
        second = _number(right, "Comparison")

    if operator == "=":
        return first == second
    if operator == "<>":
        return first != second
    if operator == "<":
        return first < second
    if operator == "<=":
        return first <= second
    if operator == ">":
        return first > second
    return first >= second


def _excel_round(value: float, digits: float = 0.0) -> float:
    """ROUND with Excel's half-away-from-zero rule (Python rounds half to even)."""
    factor = 10.0 ** int(digits)
    scaled = value * factor
    rounded = math.floor(abs(scaled) + 0.5)
    return math.copysign(rounded, scaled) / factor


def _excel_ceiling(value: float, significance: float = 1.0) -> float:
    if significance == 0:
        return 0.0
    return math.ceil(value / significance) * significance


def _call(name: str, node_args: list[tuple], values: dict[str, Any]) -> Any:
    # IF short-circuits: the untaken branch must not be evaluated, so a guard
    # like IF(qty > 0, total / qty, 0) is safe.
    if name == "IF":
        condition = _truthy(_evaluate(node_args[0], values))
        if condition:
            return _evaluate(node_args[1], values)
        if len(node_args) == 3:
            return _evaluate(node_args[2], values)
        return False

    if name == "AND":
        for argument in node_args:
            if not _truthy(_evaluate(argument, values)):
                return False
        return True

    if name == "OR":
        for argument in node_args:
            if _truthy(_evaluate(argument, values)):
                return True
        return False

    if name == "NOT":
        return not _truthy(_evaluate(node_args[0], values))

    arguments = [_evaluate(argument, values) for argument in node_args]

    if name == "MAX":
        return max(_number(item, "MAX") for item in arguments)
    if name == "MIN":
        return min(_number(item, "MIN") for item in arguments)
    if name == "ROUND":
        digits = _number(arguments[1], "ROUND") if len(arguments) == 2 else 0.0
        return _excel_round(_number(arguments[0], "ROUND"), digits)
    if name == "CEILING":
        step = _number(arguments[1], "CEILING") if len(arguments) == 2 else 1.0
        return _excel_ceiling(_number(arguments[0], "CEILING"), step)

    raise ValueError(f"Unknown function {name}.")


def _evaluate(node: tuple, values: dict[str, Any]) -> Any:
    kind = node[0]

    if kind == "num":
        return node[1]
    if kind == "str":
        return node[1]

    if kind == "name":
        name = node[1]
        if name not in values:
            raise ValueError(f"No value supplied for parameter {name!r}.")
        return values[name]

    if kind == "neg":
        return -_number(_evaluate(node[1], values), "Negation")

    if kind == "call":
        return _call(node[1], node[2], values)

    operator = node[1]
    left = _evaluate(node[2], values)
    right = _evaluate(node[3], values)

    if operator in COMPARISONS:
        return _compare(operator, left, right)

    first = _number(left, f"Operator {operator!r}")
    second = _number(right, f"Operator {operator!r}")
    if operator == "+":
        return first + second
    if operator == "-":
        return first - second
    if operator == "*":
        return first * second
    if second == 0:
        raise ValueError("Division by zero.")
    return first / second


def evaluate(node: tuple, values: dict[str, Any]) -> Any:
    """Run a parsed expression against parameter values."""
    return _evaluate(node, values)


def evaluate_expression(expression: str, values: dict[str, Any]) -> Any:
    """Parse and run in one step."""
    return evaluate(parse(expression), values)
