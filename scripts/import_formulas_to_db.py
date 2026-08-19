"""Seed `retail.formula` from `resources/dbtemp/formula.json` and
`resources/custom_formulas.json`.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/import_formulas_to_db.py

Idempotent: upserts by `id`, so a rerun reports every row as updated and
changes nothing. This is how a fresh database gets its catalogue.

TWO SOURCES, NOT ONE
---------------------
`resources/dbtemp/formula.json` is regenerated output -- `dbtemp` holds
whatever `extract_workbook_schema.py` last produced from the workbook, and it
carries only formulas transcribed from a real row on the workbook's own
`Formulas` sheet (or a named `ENGINE` column standing in for one).

`resources/custom_formulas.json` is hand-maintained and never touched by
extraction. It holds this project's own rules -- ones with no workbook
transcription to point at, like `fc01-seasonal-index`, which combines
`fact_gmv_monthly` with a "month over mean" method the workbook never wrote
down as a numbered formula. Its ids are prefixed `fc` (formula,
custom/app-derived) precisely so they read as a different kind of thing than
`f01`..`fNN`, and its `number` values are drawn from their own disjoint range
(starting at 501) so `idx_retail_formula_number` never collides with the
workbook sequence as either grows.

WHERE GRAIN COMES FROM
----------------------
`formula.json` records has no `grain` field -- it records `sheet`, the
workbook sheet each rule was transcribed from. The two are not the same idea,
and only one of them is safe to keep asking people for.

`sheet` is provenance. `grain` is what one row of the rule's inputs counts, and
it decides which table the rule may be fed from:

    ENGINE_STORE -> store_sku     one store x one SKU  -> retail.fact_inventory_daily
    ENGINE       -> chain_sku     one SKU, chain-net   -> retail.fact_inventory_chain_daily
    Workforce    -> store_roster  one store's roster   -> (not in this database)

This mapping runs exactly once, here. After the import, nothing derives grain
from sheet again: `grain` is a stored NOT NULL column with a CHECK, the API
model requires it, and the Formula Manager offers it as a labelled dropdown. The
reason is that whoever adds the twenty-third rule through the UI does not have
the workbook, and cannot be expected to know that `ENGINE_STORE` means
per-store. Under the old scheme a rule typed with a blank or invented sheet
reached an agent ungrained and nothing caught it.

An unmapped sheet fails the run and names the formula. It is the one moment the
inference is applied, so a guess here would be permanent and silent -- which is
exactly the failure the column exists to prevent.

Custom formulas have no sheet to infer from in the first place, so they carry
their `grain` directly in `custom_formulas.json` instead of leaving it to be
guessed -- explicit for the same reason the sheet mapping above is explicit,
not because the rule is being relaxed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402

SOURCE = REPO / "resources" / "dbtemp" / "formula.json"
CUSTOM_SOURCE = REPO / "resources" / "custom_formulas.json"

GRAIN_FROM_SHEET: dict[str, str] = {
    "ENGINE_STORE": "store_sku",
    "ENGINE": "chain_sku",
    "Workforce": "store_roster",
}

# What the workbook transcript plus the custom file hold today. Asserted
# rather than assumed: if the split moves, the mapping above (or a custom
# formula's stated grain) deserves a second look before these rows are
# written under it.
EXPECTED_SPLIT: dict[str, int] = {
    "store_sku": 17,
    "chain_sku": 3,
    "store_roster": 3,
    "vertical": 1,
}

UPSERT = """
MERGE retail.formula WITH (HOLDLOCK) AS target
USING (SELECT :id AS id) AS source
ON target.id = source.id
WHEN MATCHED THEN UPDATE SET
    number      = :number,
    name        = :name,
    logic       = :logic,
    grain       = :grain,
    sheet       = :sheet,
    result_type = :result_type,
    expression  = :expression,
    parameters  = :parameters,
    updated_at  = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT
    (id, number, name, logic, grain, sheet, result_type, expression,
     parameters, updated_at)
    VALUES (:id, :number, :name, :logic, :grain, :sheet, :result_type,
            :expression, :parameters, SYSUTCDATETIME());
"""


def load_formulas(source: Path) -> list[dict[str, Any]]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    formulas = payload["formulas"] if isinstance(payload, dict) else payload
    if not isinstance(formulas, list) or not formulas:
        raise SystemExit(f"FAIL  {source} holds no formulas.")
    return formulas


def to_row(formula: dict[str, Any]) -> dict[str, Any]:
    """One JSON record as an insertable row, or raise naming the formula."""
    formula_id = str(formula.get("id") or "").strip()
    if not formula_id:
        raise SystemExit(f"FAIL  a formula has no id: {formula!r}")

    sheet = str(formula.get("sheet") or "").strip()

    # A formula that states its own grain (only custom_formulas.json records
    # do) is trusted rather than routed through the sheet inference below --
    # it has no workbook sheet to infer from in the first place.
    stated_grain = formula.get("grain")
    if stated_grain is not None:
        grain = str(stated_grain).strip()
    else:
        grain = GRAIN_FROM_SHEET.get(sheet)
        if grain is None:
            raise SystemExit(
                f"FAIL  {formula_id} has sheet {sheet!r}, which maps to no grain.\n"
                f"      Known sheets: {', '.join(sorted(GRAIN_FROM_SHEET))}.\n"
                f"      Add the mapping deliberately -- a guessed grain is silent "
                f"and permanent."
            )

    return {
        "id": formula_id,
        "number": int(formula["number"]),
        "name": str(formula.get("name") or ""),
        "logic": formula.get("logic"),
        "grain": grain,
        "sheet": sheet or None,
        "result_type": str(formula.get("result_type") or "number"),
        "expression": str(formula["expression"]),
        "parameters": json.dumps(formula.get("parameters") or []),
    }


def main() -> int:
    engine = get_engine()
    print(f"database: {engine.url.database}")
    print(f"sources:  {SOURCE.relative_to(REPO)}")
    print(f"          {CUSTOM_SOURCE.relative_to(REPO)}\n")

    formulas = load_formulas(SOURCE) + load_formulas(CUSTOM_SOURCE)
    rows = [to_row(formula) for formula in formulas]

    split: dict[str, int] = {}
    for row in rows:
        split[row["grain"]] = split.get(row["grain"], 0) + 1
    if split != EXPECTED_SPLIT:
        print(f"  note  grain split {split} differs from the expected "
              f"{EXPECTED_SPLIT}; check the mapping is still right.")

    with engine.connect() as connection:
        existing = set(
            connection.execute(text("SELECT id FROM retail.formula")).scalars().all()
        )

    inserted = sum(1 for row in rows if row["id"] not in existing)
    updated = len(rows) - inserted

    with engine.begin() as connection:
        connection.execute(text(UPSERT), rows)

    print(f"  ok  {inserted} inserted, {updated} updated\n")

    with engine.connect() as connection:
        total = connection.execute(
            text("SELECT count(*) FROM retail.formula")
        ).scalar_one()
        by_grain = connection.execute(
            text(
                """
                SELECT grain, count(*)
                FROM retail.formula
                GROUP BY grain
                ORDER BY grain
                """
            )
        ).all()
        ungrained = connection.execute(
            text("SELECT count(*) FROM retail.formula WHERE grain IS NULL")
        ).scalar_one()

    print(f"retail.formula: {total} rows")
    for grain, count in by_grain:
        print(f"  {grain:14} {count}")
    print(f"  ungrained      {ungrained}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
