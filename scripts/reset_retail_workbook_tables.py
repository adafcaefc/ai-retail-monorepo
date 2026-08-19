"""One-time reset: DROP every table the v8.2->v8.5 workbook migration touches.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/reset_retail_workbook_tables.py --apply

Dry run by default (prints the drop order, does nothing). `--apply` executes.

WHY A FULL DROP, NOT JUST THE 14 WORKBOOK-OWNED TABLES
`retail.dim_item` and `retail.dim_store` are also FK targets of 5 tables this
migration does not own or reseed: `fact_sales_daily`, `fact_price_daily`,
`fact_promotion`, `fact_purchase_receipt`, and `forecast_daily` (itself
referencing `forecast_run`, and `forecast_accuracy` referencing `forecast_run`
too). SQL Server refuses to drop a table an FK still points at, so dropping
the dims means dropping these 7 as well. Confirmed safe first: all 7 are
empty (`backend/src/llm/agents/retail/common/snapshot.py` documents them as
"empty by design" -- this workbook has no real transaction history), so
nothing is lost. They come back via 002_create_orm_schema.sql same as the 14
owned tables, then stay empty exactly as before.

`retail.formula` and `audit.import_batches` are NOT in this list. Formula
sync goes through the existing idempotent upsert
(scripts/import_formulas_to_db.py), and audit.import_batches is the shared
audit trail across every import (including the unrelated finance `newdata`
work) -- not ours to erase.

After this runs, recreate everything via
    ../.venv/Scripts/python.exe ../scripts/apply_sql_migration.py ../sql/retail/002_create_orm_schema.sql --apply
    ../.venv/Scripts/python.exe ../scripts/apply_sql_migration.py ../sql/retail/004_add_markdown_and_baseline_columns.sql --apply
    ../.venv/Scripts/python.exe ../scripts/apply_sql_migration.py ../sql/retail/005_add_dim_item_competitor_index.sql --apply
then reseed with seed_retail_dims_from_json.py and seed_retail_facts_from_json.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402

SCHEMA = "retail"

# Children before parents -- see the FK graph in sql/retail/002_create_orm_schema.sql.
DROP_ORDER = (
    "forecast_daily",
    "forecast_accuracy",
    "assortment",
    "fact_sales_daily",
    "fact_inventory_daily",
    "fact_price_daily",
    "fact_promotion",
    "fact_purchase_receipt",
    "fact_inventory_chain_daily",
    "trade_agreement",
    "replenishment_proposal",
    "fact_gmv_monthly",
    "agent_kpi_reference",
    "forecast_run",
    "promotion_detail",
    "promotion_vertical_kpi",
    "dim_item",
    "dim_store",
    "dim_vendor",
    "dim_calendar",
    "dim_vertical",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    args = ap.parse_args()

    engine = get_engine()

    with engine.connect() as connection:
        existing = set(
            connection.execute(
                text(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA = :schema"
                ),
                {"schema": SCHEMA},
            ).scalars()
        )

    to_drop = [name for name in DROP_ORDER if name in existing]
    missing = [name for name in DROP_ORDER if name not in existing]

    print(f"{len(to_drop)} table(s) to drop, in order:")
    for name in to_drop:
        print(f"  DROP TABLE {SCHEMA}.{name}")
    if missing:
        print(f"\n{len(missing)} already absent, skipped: {', '.join(missing)}")

    if not args.apply:
        print("\nDry run. Nothing was sent. Re-run with --apply to execute.")
        return 0

    print("\nApplying...")
    with engine.begin() as connection:
        for name in to_drop:
            connection.execute(text(f"DROP TABLE {SCHEMA}.{name}"))
            print(f"  ok  DROP TABLE {SCHEMA}.{name}")

    print("\nDone. Recreate via apply_sql_migration.py against 002/004/005, then reseed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
