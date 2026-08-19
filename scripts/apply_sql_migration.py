"""Run a .sql migration against Azure SQL, splitting it on GO.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/apply_sql_migration.py ../sql/retail/003_partition_fact_tables.sql
    ../.venv/Scripts/python.exe ../scripts/apply_sql_migration.py ../sql/retail/003_partition_fact_tables.sql --apply

`GO` is a client batch separator, not T-SQL -- pyodbc sends whatever it is
given straight to the server, which rejects it. Anything with `GO` in it
therefore cannot be executed as one string, and the DDL in sql/retail/ needs
the separator because `CREATE PARTITION FUNCTION` and friends must each begin
a batch. This splits on it the way sqlcmd and the VS Code mssql extension do.

Dry run by default: it prints the batches and the partition layout without
sending anything. `--apply` executes, with autocommit on because several DDL
statements here cannot run inside an explicit transaction.

Connection string comes from backend/.env; nothing is hardcoded.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pyodbc

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / "backend" / ".env"

WATCHED = (
    "fact_sales_daily",
    "fact_inventory_daily",
    "fact_price_daily",
    "fact_inventory_chain_daily",
    "forecast_daily",
)


def connection_string() -> str:
    if not ENV.exists():
        sys.exit(f"{ENV} not found")
    value = None
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("AZURE_SQL_CONNECTIONSTRING="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not value:
        sys.exit("AZURE_SQL_CONNECTIONSTRING missing from backend/.env")
    if "driver=" not in value.lower():
        value = value.rstrip("; ") + ";Driver={ODBC Driver 18 for SQL Server}"
    if "connection timeout" not in value.lower():
        value = value.rstrip("; ") + ";Connection Timeout=90"
    return value


def layout(cur: pyodbc.Cursor, label: str) -> None:
    print(f"--- {label} ---")
    cur.execute("select count(*) from sys.partition_functions where name = 'pf_retail_month'")
    print(f"  pf_retail_month: {'present' if cur.fetchone()[0] else 'absent'}")
    for table in WATCHED:
        cur.execute(f"select object_id('retail.{table}', 'U')")
        if cur.fetchone()[0] is None:
            print(f"  retail.{table:<28} absent")
            continue
        cur.execute(
            f"""
            select (select count(*) from sys.partitions
                    where object_id = object_id('retail.{table}') and index_id = 1),
                   (select count(*) from retail.{table})
            """
        )
        partitions, rows = cur.fetchone()
        print(f"  retail.{table:<28} partitions={partitions:<5} rows={rows:,}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="path to the .sql file")
    ap.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    args = ap.parse_args()

    sql_path = Path(args.path)
    if not sql_path.is_absolute():
        sql_path = (Path.cwd() / sql_path).resolve()
    if not sql_path.exists():
        sys.exit(f"{sql_path} not found")

    batches = [
        batch.strip()
        for batch in re.split(r"(?im)^\s*GO\s*$", sql_path.read_text(encoding="utf-8"))
        if batch.strip()
    ]

    conn = pyodbc.connect(connection_string(), timeout=90)
    conn.autocommit = True
    cur = conn.cursor()

    print(f"{sql_path.name}: {len(batches)} batch(es)\n")
    layout(cur, "BEFORE")

    if not args.apply:
        for i, batch in enumerate(batches, 1):
            first = next(
                (
                    line.strip()
                    for line in batch.splitlines()
                    if line.strip() and not line.strip().startswith("--")
                ),
                "(comments only)",
            )
            print(f"  batch {i}/{len(batches)}: {first[:88]}")
        print("\nDry run. Nothing was sent. Re-run with --apply to execute.")
        return 0

    print("Applying...")
    for i, batch in enumerate(batches, 1):
        try:
            cur.execute(batch)
            while cur.nextset():
                pass
            print(f"  batch {i}/{len(batches)}: ok")
        except Exception as exc:
            print(f"  batch {i}/{len(batches)}: FAILED -- {str(exc)[:240]}")
            print("\n--- failing batch ---")
            print(batch[:600])
            return 1

    print()
    layout(cur, "AFTER")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
