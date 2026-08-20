"""Seed `synthetic.demand_store_sku_32w` from the POC CSV export.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/seed_synthetic_demand_32w.py

Input:  resources/demand_store_sku_32w_poc_v1.csv
        resources/demand_store_sku_32w_poc_v1_manifest.json
Output: synthetic.demand_store_sku_32w, fully replaced

THE CSV IS THE SOURCE OF TRUTH
------------------------------
The table was first loaded out-of-band, which left the repo unable to
reproduce it: a fresh environment could build every `retail` table from the
workbook and still have nothing behind the demand curves. The CSV beside this
script is the same export that made the live table, and the manifest beside it
records the column contract and row count the POC generator produced. Run
`sql/retail/010_create_synthetic_demand_32w.sql` first for the shape; this
script only moves rows.

Re-run it whenever the CSV changes. It deletes and re-inserts the whole table
inside one transaction (the same `replace_all` discipline the retail seeder
uses), so a reader never observes a half-rewritten table and a failed run
leaves the previous data intact.

WHY NO AUDIT BATCH
------------------
The `retail` seeders open an `audit.import_batches` row because their figures
reconcile against workbook sheets and a run is worth finding later. This
dataset's provenance record is the manifest itself — generator name, row
counts, QC thresholds — which is a better answer to "where did this come from"
than an audit row pointing at a CSV. Nothing downstream picks an import batch
off this table.
"""

from __future__ import annotations

import csv
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402

CSV_SOURCE = REPO / "resources" / "demand_store_sku_32w_poc_v1.csv"
MANIFEST = REPO / "resources" / "demand_store_sku_32w_poc_v1_manifest.json"

SCHEMA = "synthetic"
TABLE = "demand_store_sku_32w"

# The manifest states this; it is re-checked against the CSV at runtime so a
# truncated download cannot masquerade as a full export.
EXPECTED_ROWS = 16_000


def load_rows() -> list[dict[str, Any]]:
    """The CSV as typed row dicts, after checking the manifest's contract.

    Values become `Decimal` straight from the text: every figure in the export
    carries exactly six decimals, and `Decimal` keeps them exact where `float`
    would round-trip through binary -- the live table's `DECIMAL(20,6)` then
    receives precisely what the CSV states, not the nearest double.
    """
    contract = json.loads(MANIFEST.read_text(encoding="utf-8"))["column_contract"]
    columns = contract["columns"]

    with CSV_SOURCE.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != columns:
            raise SystemExit(
                f"FAIL  CSV header disagrees with the manifest contract.\n"
                f"      csv:      {reader.fieldnames}\n"
                f"      manifest: {columns}"
            )
        rows = [
            {name: (value if name in ("sku_id", "store_id", "cat") else Decimal(value))
             for name, value in row.items()}
            for row in reader
        ]

    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(
            f"FAIL  expected {EXPECTED_ROWS:,} rows, CSV holds {len(rows):,}"
        )
    return rows


def main() -> int:
    for path in (CSV_SOURCE, MANIFEST):
        if not path.exists():
            print(f"FAIL  source not found: {path}")
            return 1

    rows = load_rows()

    engine = get_engine()
    with engine.connect() as connection:
        if connection.execute(
            text(
                "SELECT OBJECT_ID(N'synthetic.demand_store_sku_32w', N'U')"
            )
        ).scalar() is None:
            print("FAIL  synthetic.demand_store_sku_32w does not exist.")
            print("      run sql/retail/010_create_synthetic_demand_32w.sql first")
            return 1

        # The CSV's keys have to exist in the dimensions before any row lands.
        # The dashboard joins this table to dim_item/dim_store; a sku that is
        # missing there would silently drop out of every scoped curve.
        skus = {row["sku_id"] for row in rows}
        stores = {row["store_id"] for row in rows}
        known_skus = {
            value for (value,) in connection.execute(
                text("SELECT item_id FROM retail.dim_item")
            )
        }
        known_stores = {
            value for (value,) in connection.execute(
                text("SELECT store_id FROM retail.dim_store")
            )
        }
        unknown_skus = sorted(skus - known_skus)[:5]
        unknown_stores = sorted(stores - known_stores)[:5]
        if unknown_skus or unknown_stores:
            print("FAIL  the CSV references ids the dimensions do not hold:")
            for label, unknown in (("sku", unknown_skus), ("store", unknown_stores)):
                if unknown:
                    shown = ", ".join(unknown)
                    print(f"      {label}: {shown}{' ...' if len(unknown) == 5 else ''}")
            print("      run scripts/seed_retail_dims_from_json.py first")
            return 1

    # Delete-then-insert, chunked, one transaction -- see the module docstring.
    columns = list(rows[0].keys())
    quoted = ", ".join(f'"{name}"' for name in columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    statement = text(
        f"INSERT INTO {SCHEMA}.{TABLE} ({quoted}) VALUES ({placeholders})"
    )

    with engine.begin() as connection:
        connection.execute(text(f"DELETE FROM {SCHEMA}.{TABLE}"))
        written = 0
        for start in range(0, len(rows), 2000):
            chunk = rows[start : start + 2000]
            connection.execute(statement, chunk)
            written += len(chunk)

    cats = {row["cat"] for row in rows}
    print(f"  ok  {written:,} rows ({len(skus)} skus x {len(stores)} stores, "
          f"{len(cats)} categories)")
    print(f"  ok  synthetic.{TABLE} fully replaced from {CSV_SOURCE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
