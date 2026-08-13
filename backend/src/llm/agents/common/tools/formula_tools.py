"""The business rules, as tools an agent can call.

The retail boards do not hardcode how a reorder point is computed; they read
`retail.formula` and evaluate it. Before these tools existed the agents had no
way to reach the same catalogue, so an agent asked "how did you get that ROP?"
could only restate the rule from memory and do the arithmetic in prose. Both
are ways to disagree with the screen the reader is looking at.

Every function here wraps `src.formulas.service`, which is the same code path
the Formula Manager API uses. Nothing is reimplemented: `evaluate_formula` runs
`src.formulas.expression`, an Excel-compatible evaluator with Excel's
half-away-from-zero ROUND and its CEILING significance semantics, so a figure
computed here matches the workbook it was transcribed from.

GRAIN
-----
Every formula carries a `grain`: what one row of its inputs counts. It is the
field most likely to be ignored and most expensive to ignore, because the two
inventory grains share parameter names:

    f04-position       store_sku   ROUND(on_hand + open_po)
    f20-days-of-supply chain_sku   IF(ads > 0, position / ads, 0)

Both take `position`. Feeding f20 one store's position returns a number that is
arithmetically correct, carries no error, and answers a question nobody asked.
So `grain` travels with every result rather than being something the caller has
to look up.

ERRORS
------
A missing id comes back as `{"error": ..., "valid_ids": [...]}` rather than
raising. A raising tool costs the agent a whole retry round trip, and the
recovery it needs is almost always just the right id -- so hand it over.
"""

from __future__ import annotations

from typing import Any

# What a grain means, and which table a rule at that grain may be fed from.
# Imported from the API models so the agents, the Formula Manager and the
# OpenAPI schema describe a grain in the same words.
from src.formulas.models import GRAIN_LABELS, GRAIN_TABLES


def _grain_note(grain: str) -> dict[str, Any]:
    """The grain, spelled out, so a caller need not know the vocabulary."""
    return {
        "grain": grain,
        "grain_means": GRAIN_LABELS.get(grain, "unknown grain"),
        "feed_from_table": GRAIN_TABLES.get(grain) or None,
    }


def _summary(formula: dict[str, Any]) -> dict[str, Any]:
    """One catalogue entry: enough to choose a formula, without its body."""
    return {
        "id": formula["id"],
        "number": formula.get("number"),
        "name": formula.get("name"),
        "logic": formula.get("logic"),
        "result_type": formula.get("result_type", "number"),
        **_grain_note(str(formula.get("grain") or "")),
        "parameters": [
            {
                "key": parameter.get("key"),
                "label": parameter.get("label"),
                "type": parameter.get("type", "number"),
                "default": parameter.get("default"),
            }
            for parameter in formula.get("parameters") or []
        ],
    }


def _not_found(formula_id: str, error: Exception) -> dict[str, Any]:
    from src.formulas import service

    try:
        valid = [item["id"] for item in service.list_formulas()]
    except Exception:  # noqa: BLE001 - the id error is the one worth reporting
        valid = []
    return {
        "error": str(error),
        "requested_id": formula_id,
        "valid_ids": valid,
    }


def list_formulas() -> dict[str, Any]:
    """List every stored business rule, with its grain and parameters.

    Call this first when you need to apply, quote or check a business rule and
    do not already know its id. It returns the whole catalogue without the
    expression bodies; call get_formula for one rule in full.

    The rules that do most of the work on the retail boards are:
      f04-position                       on-hand plus open PO
      f05-rop                            reorder point, ads x (lead + safety)
      f06-maximum-inventory              order-up-to level
      f07-inventory-state                Stockout / Low / Expiry / Overstock /
                                         Slow-mover / Healthy
      f08-forecast-7-days                ads x 7.45, the day-of-week weighted week
      f09-order-quantity-sales-units     up-to-max order in sales units
      f10-order-quantity-purchase-units  the same order in buy units, via pack factor
      f12-at-risk-value                  position x price where state is not Healthy
      f20-days-of-supply                 position / ads, chain-wide
      f21-inventory-value                position x price, chain-wide
      f22-expiry-units                   perishable units beyond shelf life

    Each entry carries `grain` ("what one row of the inputs counts") plus
    `grain_means` and `feed_from_table` spelling it out. Respect it: a
    chain_sku rule fed one store's figures returns a plausible wrong number
    rather than an error.
    """
    from src.formulas import service

    try:
        formulas = service.list_formulas()
    except Exception as error:  # noqa: BLE001
        return {"error": str(error), "items": [], "count": 0}

    return {
        "count": len(formulas),
        "items": [_summary(formula) for formula in formulas],
        "note": (
            "Expressions are omitted here. Call get_formula(formula_id) for "
            "one rule in full, or evaluate_formula(formula_id, values) to "
            "compute it."
        ),
    }


def get_formula(formula_id: str) -> dict[str, Any]:
    """Return one business rule in full, including its expression.

    Use this to quote the exact rule behind a figure, or to see which
    parameters a formula needs before calling evaluate_formula. Pass an id
    exactly as list_formulas reports it, for example 'f05-rop'.

    Args:
        formula_id: Id of the formula, e.g. 'f07-inventory-state'.
    """
    from src.formulas import service

    try:
        formula = service.get_formula(formula_id)
    except LookupError as error:
        return _not_found(formula_id, error)
    except Exception as error:  # noqa: BLE001
        return {"error": str(error), "requested_id": formula_id}

    return {
        **_summary(formula),
        "expression": formula.get("expression"),
        "source_sheet": formula.get("sheet") or None,
    }


def evaluate_formula(
    formula_id: str,
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute a stored business rule and return the number it produces.

    Always prefer this over doing the arithmetic yourself: the retail boards
    evaluate the same catalogue, so a figure computed here reconciles with what
    the reader is looking at and one computed in prose may not.

    Any parameter you omit falls back to its stored default, and the response
    echoes every value actually used -- so a what-if is just an override.
    To answer "what if lead time were 9 days?", pass
    {'lead_time_days': 9} and leave the rest alone; the returned `values` shows
    exactly what was assumed.

    Args:
        formula_id: Id of the formula, e.g. 'f05-rop'.
        values: Parameter values by key. Omitted keys use their stored default.
    """
    from src.formulas import service

    try:
        result = service.evaluate_formula(formula_id, values or {})
    except LookupError as error:
        return _not_found(formula_id, error)
    except ValueError as error:
        # A missing parameter with no default, or an expression that could not
        # be evaluated. Return the parameter list so the retry can be correct.
        detail: dict[str, Any] = {"error": str(error), "requested_id": formula_id}
        try:
            detail["parameters"] = _summary(service.get_formula(formula_id))[
                "parameters"
            ]
        except Exception:  # noqa: BLE001
            pass
        return detail
    except Exception as error:  # noqa: BLE001
        return {"error": str(error), "requested_id": formula_id}

    grain = str(result.get("grain") or "")
    return {
        "id": result["id"],
        "result": result["result"],
        "result_type": result.get("result_type", "number"),
        **_grain_note(grain),
        "values": result.get("values", {}),
    }


LOCAL_FORMULA_TOOLS = {
    "list_formulas": list_formulas,
    "get_formula": get_formula,
    "evaluate_formula": evaluate_formula,
}


__all__ = [
    "LOCAL_FORMULA_TOOLS",
    "evaluate_formula",
    "get_formula",
    "list_formulas",
]
