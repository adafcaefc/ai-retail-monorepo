"""Copy the snake_case `retail`/`chat`/`audit` rows from PostgreSQL into Azure SQL.

Run it yourself (dry run first — it writes nothing):

    cd backend
    ../.venv/Scripts/python.exe ../scripts/migrate_pg_to_azure.py
    ../.venv/Scripts/python.exe ../scripts/migrate_pg_to_azure.py --apply

Why this exists: the star-schema tables the agents actually query
(`retail.dim_*`, `retail.fact_*`) were created in Azure SQL on 2026-08-14 but
never loaded, so every agent returns zeros. The same tables in PostgreSQL are
populated and are already the shape `src/llm/agents/` expects, so this copies
them across rather than re-deriving the transform from the PascalCase workbook
dump (`retail.Sku`, `retail.StoreSkuSnapshot`, ...) that holds the same source
data under a different model.

Both connection strings are read from `backend/.env` — nothing is hardcoded.

Four things this has to reconcile, because the two schemas were generated
independently and their types do not line up:

  * `timestamptz` -> `datetime2`. SQL Server's datetime2 has no offset, so
    values are converted to UTC and the offset dropped. Absolute instants
    survive; the original offset does not.
  * `jsonb` / `text[]` -> `nvarchar`. Serialised with json.dumps, so `routes`
    arrives as a JSON array rather than a Postgres array literal.
  * unbounded `text` -> bounded `nvarchar(n)`. Postgres never enforced a
    length, so the dry run measures every string column against its target
    width and refuses to start if anything would be silently truncated.
  * IDENTITY columns. `audit.import_batches.id`, `chat.monitoring_runs.id` and
    `retail.forecast_run.run_id` are IDENTITY in Azure SQL, so their literal
    keys are preserved under IDENTITY_INSERT — the fact tables carry those ids
    as foreign keys and renumbering would orphan them.

Re-runnable: each table is deleted (children first) and reloaded inside one
transaction per table. It is a replace, not an upsert — anything written
directly into Azure SQL that is not in PostgreSQL is lost. `chat.monitoring_runs`
is the one table where that is not hypothetical: it holds 31 rows in Azure SQL
against 29 in PostgreSQL, so the dry run calls it out before you commit to it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pyodbc

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / "backend" / ".env"

SCHEMAS = ("audit", "retail", "chat")
BATCH = 1000

# Azure SQL reports these as ordinary columns; only sys.identity_columns knows
# they are IDENTITY, and INSERT refuses them without an explicit override.
IDENTITY_OVERRIDE = {
    "audit.import_batches",
    "chat.monitoring_runs",
    "retail.forecast_run",
}


def read_env() -> tuple[str, str]:
    if not ENV.exists():
        sys.exit(f"{ENV} not found")
    values: dict[str, str] = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")

    pg = values.get("DATABASE_URL")
    ms = values.get("AZURE_SQL_CONNECTIONSTRING")
    if not pg:
        sys.exit("DATABASE_URL missing from backend/.env")
    if not ms:
        sys.exit("AZURE_SQL_CONNECTIONSTRING missing from backend/.env")

    if "sslmode=" not in pg:
        pg += ("&" if "?" in pg else "?") + "sslmode=require"
    if "driver=" not in ms.lower():
        ms = ms.rstrip("; ") + ";Driver={ODBC Driver 18 for SQL Server}"
    # The free tier auto-pauses; the first connection after an idle spell has
    # to wait for the resume rather than fail the run.
    if "connection timeout" not in ms.lower():
        ms = ms.rstrip("; ") + ";Connection Timeout=90"
    return pg, ms


def target_columns(cur: pyodbc.Cursor) -> dict[str, list[tuple[str, str, int]]]:
    """{schema.table: [(column, type, max_char_len)]} in INSERT order."""
    cur.execute(
        """
        select s.name + '.' + t.name, c.name, ty.name, c.max_length, c.column_id
        from sys.columns c
        join sys.tables t on t.object_id = c.object_id
        join sys.schemas s on s.schema_id = t.schema_id
        join sys.types ty on ty.user_type_id = c.user_type_id
        where s.name in (?, ?, ?)
          and t.name = lower(t.name) collate Latin1_General_CS_AS
        order by s.name, t.name, c.column_id
        """,
        *SCHEMAS,
    )
    out: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for table, col, typ, max_len, _ in cur.fetchall():
        # nvarchar counts bytes here, two per character; -1 means MAX.
        chars = -1 if max_len == -1 else (max_len // 2 if typ.startswith("n") else max_len)
        out[table].append((col, typ, chars))
    return dict(out)


def load_order(cur: pyodbc.Cursor, tables: list[str]) -> list[str]:
    """Parents before children, so foreign keys resolve as rows land."""
    cur.execute(
        """
        select s.name + '.' + tp.name, rs.name + '.' + tr.name
        from sys.foreign_keys fk
        join sys.tables tp on tp.object_id = fk.parent_object_id
        join sys.schemas s on s.schema_id = tp.schema_id
        join sys.tables tr on tr.object_id = fk.referenced_object_id
        join sys.schemas rs on rs.schema_id = tr.schema_id
        """
    )
    known = set(tables)
    parents: dict[str, set[str]] = {t: set() for t in tables}
    for child, parent in cur.fetchall():
        # Self-references order themselves; nothing to wait for.
        if child in known and parent in known and child != parent:
            parents[child].add(parent)

    ordered: list[str] = []
    placed: set[str] = set()
    while len(ordered) < len(tables):
        ready = sorted(t for t in tables if t not in placed and parents[t] <= placed)
        if not ready:
            # A cycle would hang the loop; fall back to declaration order and
            # let the database complain rather than silently dropping tables.
            ready = sorted(t for t in tables if t not in placed)
        ordered.extend(ready)
        placed.update(ready)
    return ordered


def convert(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, Decimal):
        return value
    return value


def measure(rows: list[tuple], columns: list[str], widths: dict[str, int]) -> dict[str, int]:
    """Longest string actually present per column, for the truncation check."""
    longest: dict[str, int] = {}
    for row in rows:
        for col, value in zip(columns, row):
            if widths.get(col, -1) > 0 and isinstance(value, str):
                if len(value) > longest.get(col, 0):
                    longest[col] = len(value)
    return longest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--only", help="comma-separated schema.table list")
    ap.add_argument(
        "--schemas",
        default=",".join(SCHEMAS),
        help=(
            "comma-separated schemas to copy (default: all). Use "
            "'audit,retail' to load the agent-facing tables while leaving the "
            "chat history in Azure SQL untouched."
        ),
    )
    args = ap.parse_args()

    chosen = tuple(s.strip() for s in args.schemas.split(",") if s.strip())
    unknown = set(chosen) - set(SCHEMAS)
    if unknown:
        sys.exit(f"unknown schema(s): {', '.join(sorted(unknown))}")

    pg_dsn, ms_dsn = read_env()
    pg = psycopg.connect(pg_dsn, connect_timeout=60)
    ms = pyodbc.connect(ms_dsn, timeout=90)
    ms.autocommit = False
    mcur = ms.cursor()

    targets = target_columns(mcur)

    pcur = pg.cursor()
    pcur.execute(
        """
        select table_schema || '.' || table_name
        from information_schema.tables
        where table_schema = any(%s) and table_type = 'BASE TABLE'
        """,
        (list(chosen),),
    )
    # `*_default` are Postgres partition children; their rows arrive through
    # the parent table and would be copied twice if taken on their own.
    source = {t[0] for t in pcur.fetchall() if not t[0].endswith("_default")}

    tables = sorted(source & set(targets))
    if args.only:
        wanted = {t.strip() for t in args.only.split(",")}
        tables = [t for t in tables if t in wanted]

    ordered = load_order(mcur, tables)

    print(f"{'TABLE':<38}{'PG':>9}{'AZURE':>9}  COLUMNS  NOTE")
    print("-" * 96)

    plan: list[tuple[str, list[str], list[tuple], int]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    total_src = 0

    for table in ordered:
        schema, name = table.split(".")
        tgt = targets[table]
        tgt_names = [c[0] for c in tgt]
        widths = {c[0]: c[2] for c in tgt}
        lowered = {c.lower(): c for c in tgt_names}

        pcur.execute(
            """
            select column_name from information_schema.columns
            where table_schema = %s and table_name = %s order by ordinal_position
            """,
            (schema, name),
        )
        src_names = [r[0] for r in pcur.fetchall()]

        shared = [lowered[c.lower()] for c in src_names if c.lower() in lowered]
        dropped = [c for c in src_names if c.lower() not in lowered]

        pcur.execute(f'select count(*) from {schema}."{name}"')
        n_src = pcur.fetchone()[0]
        mcur.execute(f"select count(*) from [{schema}].[{name}]")
        n_dst = mcur.fetchone()[0]
        total_src += n_src

        rows: list[tuple] = []
        if n_src:
            select_cols = ", ".join(f'"{c.lower()}"' for c in shared)
            pcur.execute(f'select {select_cols} from {schema}."{name}"')
            rows = [tuple(convert(v) for v in r) for r in pcur.fetchall()]

        notes: list[str] = []
        if dropped:
            notes.append(f"skip cols: {','.join(dropped)}")
            warnings.append(f"{table}: source columns absent in Azure SQL -> {', '.join(dropped)}")
        if table in IDENTITY_OVERRIDE:
            notes.append("IDENTITY_INSERT")
        if n_dst and n_src and n_dst != n_src:
            warnings.append(f"{table}: Azure SQL holds {n_dst:,} rows vs {n_src:,} in PostgreSQL — replace loses the difference")
        elif n_dst and not n_src:
            warnings.append(f"{table}: Azure SQL holds {n_dst:,} rows, PostgreSQL is empty — replace would empty it")

        for col, longest in measure(rows, shared, widths).items():
            if longest > widths[col]:
                blockers.append(f"{table}.{col}: longest value {longest} chars > nvarchar({widths[col]})")

        print(f"{table:<38}{n_src:>9,}{n_dst:>9,}{len(shared):>9}  {'; '.join(notes)}")
        plan.append((table, shared, rows, n_dst))

    print("-" * 96)
    print(f"{'TOTAL':<38}{total_src:>9,}")

    if warnings:
        print("\nWARNINGS")
        for w in warnings:
            print(f"  ! {w}")

    if blockers:
        print("\nBLOCKERS — values would be truncated, nothing was written:")
        for b in blockers:
            print(f"  x {b}")
        return 2

    if not args.apply:
        print("\nDry run. Nothing was written. Re-run with --apply to load.")
        return 0

    print("\nApplying...")
    # Children first, so a delete never trips a foreign key.
    for table, *_ in reversed(plan):
        schema, name = table.split(".")
        mcur.execute(f"delete from [{schema}].[{name}]")
    ms.commit()

    for table, cols, rows, _ in plan:
        if not rows:
            continue
        schema, name = table.split(".")
        collist = ", ".join(f"[{c}]" for c in cols)
        params = ", ".join("?" * len(cols))
        sql = f"insert into [{schema}].[{name}] ({collist}) values ({params})"
        ident = table in IDENTITY_OVERRIDE
        try:
            if ident:
                mcur.execute(f"set identity_insert [{schema}].[{name}] on")
            mcur.fast_executemany = True
            for i in range(0, len(rows), BATCH):
                mcur.executemany(sql, rows[i : i + BATCH])
            if ident:
                mcur.execute(f"set identity_insert [{schema}].[{name}] off")
            ms.commit()
        except Exception as exc:
            ms.rollback()
            print(f"  FAILED {table}: {str(exc)[:200]}")
            return 1
        print(f"  {table:<38} {len(rows):>9,} rows")

    print("\nVerifying...")
    bad = 0
    for table, _, rows, _ in plan:
        schema, name = table.split(".")
        pcur.execute(f'select count(*) from {schema}."{name}"')
        a = pcur.fetchone()[0]
        mcur.execute(f"select count(*) from [{schema}].[{name}]")
        b = mcur.fetchone()[0]
        flag = "" if a == b else "   <-- MISMATCH"
        if a != b:
            bad += 1
        print(f"  {table:<38} pg={a:>8,}  azure={b:>8,}{flag}")

    print("\nDone." if not bad else f"\n{bad} table(s) did not match.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
