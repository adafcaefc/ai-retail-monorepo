"""Formula Manager business logic.

Raises plain exceptions -- `LookupError` for a missing formula, `ValueError`
for bad input -- and the router maps them onto 404/422, matching
`src/actions/router.py`.
"""

from __future__ import annotations

import re

from typing import Any

from src.formulas import expression as expr
from src.formulas import repository
from src.formulas.models import FormulaCreate, FormulaUpdate, Parameter

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _slugify(text: str) -> str:
    slug = _SLUG_STRIP.sub("-", text.strip().lower()).strip("-")
    return slug or "formula"


def _unique_id(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


def _check_parameters(parameters: list[Parameter]) -> None:
    seen: set[str] = set()
    for parameter in parameters:
        key = parameter.key
        if not _KEY_RE.match(key):
            raise ValueError(
                f"Parameter name {key!r} must start with a letter or underscore "
                "and contain only letters, digits and underscores."
            )
        if key.upper() in expr.FUNCTIONS:
            raise ValueError(
                f"Parameter name {key!r} clashes with the built-in function {key.upper()}."
            )
        if key in seen:
            raise ValueError(f"Duplicate parameter name {key!r}.")
        seen.add(key)


def _inspect(expression: str, parameters: list[Parameter]) -> dict[str, Any]:
    """Parse + cross-check an expression against its declared parameters."""
    errors: list[str] = []
    referenced: set[str] = set()
    declared = [parameter.key for parameter in parameters]

    try:
        _check_parameters(parameters)
    except ValueError as error:
        errors.append(str(error))

    try:
        referenced = expr.referenced_names(expr.parse(expression))
    except ValueError as error:
        errors.append(str(error))

    undeclared = sorted(referenced - set(declared))
    # Declared-but-unused is reported, not rejected: it is a normal
    # intermediate state while editing and the formula still evaluates.
    unused = sorted(set(declared) - referenced)

    if undeclared:
        errors.append(
            "Expression uses undeclared parameter(s): " + ", ".join(undeclared) + "."
        )

    return {
        "valid": not errors,
        "errors": errors,
        "referenced": sorted(referenced),
        "undeclared": undeclared,
        "unused": unused,
    }


def validate(expression: str, parameters: list[Parameter]) -> dict[str, Any]:
    """Check a draft expression without storing it."""
    return _inspect(expression, parameters)


def _require_valid(expression: str, parameters: list[Parameter]) -> None:
    report = _inspect(expression, parameters)
    if not report["valid"]:
        raise ValueError(" ".join(report["errors"]))


def _as_dict(payload: FormulaCreate | FormulaUpdate) -> dict[str, Any]:
    return {
        "name": payload.name.strip(),
        "logic": payload.logic.strip(),
        # Not stripped or normalized: `Grain` is a Literal, so pydantic has
        # already rejected anything that is not one of the three.
        "grain": payload.grain,
        "sheet": payload.sheet.strip(),
        "result_type": payload.result_type,
        "expression": payload.expression.strip(),
        "parameters": [
            parameter.model_dump() for parameter in payload.parameters
        ],
    }


def _check_unique(
    formulas: list[dict[str, Any]],
    name: str,
    number: int,
    exclude_id: str | None = None,
) -> None:
    for formula in formulas:
        if formula["id"] == exclude_id:
            continue
        if formula["name"].casefold() == name.casefold():
            raise ValueError(f"A formula named {name!r} already exists.")
        if formula["number"] == number:
            raise ValueError(f"Formula number {number} is already used.")


def list_formulas() -> list[dict[str, Any]]:
    return repository.load()


def get_formula(formula_id: str) -> dict[str, Any]:
    for formula in repository.load():
        if formula["id"] == formula_id:
            return formula
    raise LookupError(f"No formula with id {formula_id!r}.")


def create_formula(payload: FormulaCreate) -> dict[str, Any]:
    fields = _as_dict(payload)
    _require_valid(fields["expression"], payload.parameters)

    formulas = repository.load()
    taken = {formula["id"] for formula in formulas}
    formula_id = (payload.id or _slugify(fields["name"])).strip()
    if not formula_id:
        raise ValueError("Formula id cannot be empty.")
    formula_id = _unique_id(_slugify(formula_id), taken)

    number = payload.number
    if number is None:
        number = max((formula["number"] for formula in formulas), default=0) + 1
    _check_unique(formulas, fields["name"], number)

    created = {"id": formula_id, "number": number, **fields}
    formulas.append(created)
    repository.save(sorted(formulas, key=lambda item: item["number"]))
    return created


def update_formula(formula_id: str, payload: FormulaUpdate) -> dict[str, Any]:
    fields = _as_dict(payload)
    _require_valid(fields["expression"], payload.parameters)

    formulas = repository.load()
    for index, formula in enumerate(formulas):
        if formula["id"] != formula_id:
            continue
        number = payload.number if payload.number is not None else formula["number"]
        _check_unique(formulas, fields["name"], number, exclude_id=formula_id)
        updated = {"id": formula_id, "number": number, **fields}
        formulas[index] = updated
        repository.save(sorted(formulas, key=lambda item: item["number"]))
        return updated

    raise LookupError(f"No formula with id {formula_id!r}.")


def delete_formula(formula_id: str) -> dict[str, Any]:
    formulas = repository.load()
    remaining = [formula for formula in formulas if formula["id"] != formula_id]
    if len(remaining) == len(formulas):
        raise LookupError(f"No formula with id {formula_id!r}.")
    repository.save(remaining)
    return {"id": formula_id, "deleted": True}


def _coerce(parameter: dict[str, Any], raw: Any) -> Any:
    kind = parameter.get("type", "number")
    key = parameter["key"]

    if kind == "text":
        return "" if raw is None else str(raw)

    if kind == "boolean":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().casefold() in {"y", "yes", "true", "1"}
        return bool(raw)

    if isinstance(raw, bool):
        return 1.0 if raw else 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        raise ValueError(
            f"Parameter {key!r} needs a number, got {raw!r}."
        ) from None


def evaluate_formula(formula_id: str, values: dict[str, Any]) -> dict[str, Any]:
    """Run a stored formula. Missing values fall back to the parameter default."""
    formula = get_formula(formula_id)
    parameters = formula.get("parameters", [])

    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for parameter in parameters:
        key = parameter["key"]
        if key in values and values[key] not in (None, ""):
            resolved[key] = _coerce(parameter, values[key])
        elif parameter.get("default") is not None:
            resolved[key] = _coerce(parameter, parameter["default"])
        else:
            missing.append(key)

    if missing:
        raise ValueError("Missing value(s) for: " + ", ".join(missing) + ".")

    try:
        result = expr.evaluate_expression(formula["expression"], resolved)
    except ValueError as error:
        raise ValueError(f"Could not evaluate {formula['name']}: {error}") from error

    # 68.0 reads as 68 in the UI; keep whole numbers whole.
    if isinstance(result, float) and result.is_integer():
        result = int(result)

    return {
        "id": formula_id,
        "result": result,
        "result_type": formula.get("result_type", "number"),
        # Returned with the number, not left for the caller to look up. A
        # result is only interpretable against the grain of its inputs.
        "grain": formula.get("grain", "store_sku"),
        "values": resolved,
    }
