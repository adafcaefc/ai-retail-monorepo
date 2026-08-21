"""Seed `synthetic.markdown_ladder_store_sku_16w` from the generated CSV.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/seed_synthetic_markdown_ladder_16w.py

Input:  resources/markdown_ladder_store_sku_16w_v1.csv
        resources/markdown_ladder_store_sku_16w_v1_manifest.json
Output: synthetic.markdown_ladder_store_sku_16w, fully replaced

THE CSV IS THE SOURCE OF TRUTH, AND IT IS REGENERABLE
-------------------------------------------------------
Produced in-repo by scripts/generate_synthetic_markdown_ladder_16w.py from
today's fixture inputs alone. The generator is deterministic, so the CSV can
be rebuilt byte for byte at any time and the manifest beside it records the
column contract, the row count, and the four generation gates it passed. Run
sql/retail/012_create_synthetic_markdown_ladder_16w.sql first for the shape;
this script only moves rows.

Re-run it whenever the CSV changes. It deletes and re-inserts the whole
table inside one transaction (same `replace_all` discipline the other two
synthetic seeders use), so a reader never observes a half-rewritten table
and a failed run leaves the previous data intact.

WHY NO AUDIT BATCH
--------------------
Same reasoning as `seed_synthetic_inbound_16w.py`: the `retail` seeders open
an `audit.import_batches` row because their figures reconcile against
workbook sheets. This dataset's provenance record is the manifest --
generator name and version, fingerprints, the gates it passed -- which is a
better answer to "where did this come from" than an audit row pointing at a
CSV. Nothing downstream picks an import batch off this table.

PURELY ADDITIVE
-----------------
This script only ever touches synthetic.markdown_ladder_store_sku_16w. It
does not read from or write to any other table -- `synthetic.demand_
store_sku_32w`, `synthetic.inbound_store_sku_16w`, `retail.dim_item`,
`retail.fact_inventory_daily`, etc. are all untouched by running it.
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

CSV_SOURCE = REPO / "resources" / "markdown_ladder_store_sku_16w_v1.csv"
MANIFEST = REPO / "resources" / "markdown_ladder_store_sku_16w_v1_manifest.json"

SCHEMA = "synthetic"
TABLE = "markdown_ladder_store_sku_16w"

# The manifest states this; it is re-checked against the CSV at runtime so a
# truncated download cannot masquerade as a full export.
EXPECTED_ROWS = 16_000

TEXT_COLUMNS = ("sku_id", "store_id")


def load_rows() -> list[dict[str, Any]]:
    """The CSV as typed row dicts, after checking the manifest's contract.

    Values become `Decimal` straight from the text, same reasoning as the
    inbound loader: the generator writes exactly six decimals, and `Decimal`
    keeps them exact where `float` would round-trip through binary.
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
            {
                name: (value if name in TEXT_COLUMNS else Decimal(value))
                for name, value in row.items()
            }
            for row in reader
        ]

    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"FAIL  expected {EXPECTED_ROWS:,} rows, CSV holds {len(rows):,}")
    return rows


def main() -> int:
    for path in (CSV_SOURCE, MANIFEST):
        if not path.exists():
            print(f"FAIL  source not found: {path}")
            print("      run scripts/generate_synthetic_markdown_ladder_16w.py first")
            return 1

    rows = load_rows()

    engine = get_engine()
    with engine.connect() as connection:
        if connection.execute(
            text(f"SELECT OBJECT_ID(N'{SCHEMA}.{TABLE}', N'U')")
        ).scalar() is None:
            print(f"FAIL  {SCHEMA}.{TABLE} does not exist.")
            print("      run sql/retail/012_create_synthetic_markdown_ladder_16w.sql first")
            return 1

        # The CSV's keys have to exist in the dimensions before any row
        # lands. The dashboard joins this table to dim_item; a sku that is
        # missing there would silently drop out of every scoped projection.
        skus = {row["sku_id"] for row in rows}
        stores = {row["store_id"] for row in rows}
        known_skus = {
            value for (value,) in connection.execute(text("SELECT item_id FROM retail.dim_item"))
        }
        known_stores = {
            value for (value,) in connection.execute(text("SELECT store_id FROM retail.dim_store"))
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
    statement = text(f"INSERT INTO {SCHEMA}.{TABLE} ({quoted}) VALUES ({placeholders})")

    with engine.begin() as connection:
        connection.execute(text(f"DELETE FROM {SCHEMA}.{TABLE}"))
        written = 0
        for start in range(0, len(rows), 2000):
            chunk = rows[start : start + 2000]
            connection.execute(statement, chunk)
            written += len(chunk)

    print(f"  ok  {written:,} rows ({len(skus)} skus x {len(stores)} stores)")
    print(f"  ok  synthetic.{TABLE} fully replaced from {CSV_SOURCE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
