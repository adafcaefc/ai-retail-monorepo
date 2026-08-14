"""Azure SQL persistence for formulas, in `retail.formula`.

This used to be a JSON file (`resources/dbtemp/formula.json`) on the reasoning
that formulas are a small hand-curated reference set, easy to read and diff.
That held while nothing but the Formula Manager read them. It stopped holding
once the retail agents began quoting and evaluating the same rules: a file the
API writes is not visible to another process, and `warehouse.py` was reading
the same path independently, so an edit in the UI could change what the agent
computed without changing what the board drew -- two sources of truth wearing
one filename.

The file is still in the tree, and still matters, but its job changed. It is
now the seed (`scripts/import_formulas_to_db.py`) and the reference transcript
that `tests/test_formula_conformance.py` checks against the workbook. This
table is the runtime source.

`load()` and `save()` keep their original signatures and shapes, because
`service.py` only ever talks to these two functions -- which is what made this
a repository swap rather than a rewrite. `save()` replaces the whole set, as it
always did: every caller in `service.py` passes the full validated list, so
whole-set replacement is the existing contract, not a new one.

The module lock is gone. A transaction is a better lock than a threading
primitive, and it holds across processes, which the old one never did.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from src.db.db import get_engine

VERSION = 1

TABLE = "retail.formula"

# Column order used by both directions, so a field added here cannot be
# selected and not written (or the reverse).
COLUMNS: tuple[str, ...] = (
    "id",
    "number",
    "name",
    "logic",
    "grain",
    "sheet",
    "result_type",
    "expression",
    "parameters",
)

_SELECT = f"SELECT {', '.join(COLUMNS)} FROM {TABLE} ORDER BY number"

_INSERT = f"""
INSERT INTO {TABLE}
    (id, number, name, logic, grain, sheet, result_type, expression,
     parameters, updated_at)
VALUES
    (:id, :number, :name, :logic, :grain, :sheet, :result_type, :expression,
     :parameters, SYSUTCDATETIME())
"""


def _row_to_formula(row: Any) -> dict[str, Any]:
    """One DB row as the dict shape `service.py` and the API already expect.

    `parameters` is stored as an NVARCHAR(MAX) JSON string and always arrives
    as a string from the driver; a hand-inserted row still parses correctly.
    """
    formula = dict(row)
    parameters = formula.get("parameters")
    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except json.JSONDecodeError:
            parameters = []
    formula["parameters"] = parameters if isinstance(parameters, list) else []
    # The API model treats these as optional strings, not nulls.
    for key in ("logic", "sheet"):
        if formula.get(key) is None:
            formula[key] = ""
    return formula


def load() -> list[dict[str, Any]]:
    """Every stored formula, ordered by `number`. An empty table reads as []."""
    with get_engine().connect() as connection:
        rows = connection.execute(text(_SELECT)).mappings().all()
    return [_row_to_formula(row) for row in rows]


def save(formulas: list[dict[str, Any]]) -> None:
    """Replace the whole set. Callers pass the full, already-validated list.

    Delete-then-insert inside one transaction: the table is 22 rows, so the
    cost is irrelevant next to the property it buys -- a reader never observes
    a partially rewritten catalogue, and a failed write leaves the previous one
    intact.
    """
    rows = [
        {
            "id": formula["id"],
            "number": formula.get("number") or 0,
            "name": formula.get("name") or "",
            "logic": formula.get("logic") or None,
            "grain": formula["grain"],
            "sheet": formula.get("sheet") or None,
            "result_type": formula.get("result_type") or "number",
            "expression": formula.get("expression") or "",
            "parameters": json.dumps(formula.get("parameters") or []),
        }
        for formula in formulas
    ]

    with get_engine().begin() as connection:
        connection.execute(text(f"DELETE FROM {TABLE}"))
        if rows:
            connection.execute(text(_INSERT), rows)
