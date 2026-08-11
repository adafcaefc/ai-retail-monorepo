"""Create the `retail` schema: dimensions, facts, and forecast tables.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/create_retail_schema.py

Unlike `import_new_dataset.py`, which drops and recreates every table on each
run, this script is idempotent by `CREATE TABLE IF NOT EXISTS`. The difference
is deliberate and load-bearing: `newdata.*` is one snapshot per workbook import
and is disposable, whereas `retail.fact_*` and `retail.forecast_*` are daily
time series that get appended to. Dropping them would destroy history that
cannot be recovered, so this script never drops anything. To start over, run
`DROP SCHEMA retail CASCADE` by hand and mean it.

Where the shape came from: the table list and partitioning were fixed in the
approved plan; the dimension columns mirror what
`resources/dbtemp/schema_with_data.json` actually carries (so the seed can fill
them without inventing values); the inventory columns mirror the fields the
D365 `getDemandForecast` endpoint returns (ADSDay, Position, ROP, DaysCover,
Signal) so that swapping the interim workbook data for real D365 data later is
a data change, not a schema change.

Every fact and forecast table carries `import_batch_id` referencing
`audit.import_batches`. This is the opposite of the `newdata.*` convention,
where that column is absent — here lineage matters because rows accumulate from
more than one load.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402

SCHEMA = "retail"

# (label, statement). Order matters: a table may only reference one already
# created above it.
STATEMENTS: list[tuple[str, str]] = [
    (
        "schema",
        f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}",
    ),
    # ---------------------------------------------------------------- dimensions
    (
        "dim_vertical",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.dim_vertical (
            vertical_id       TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            -- The A-sheets label two verticals differently from Verticals.Short
            -- ("General Merch" vs "Department Store"). Dashboards join on this.
            dashboard_label   TEXT NOT NULL,
            sales_per_fte     NUMERIC(18, 4),
            d365_data_area    TEXT
        )
        """,
    ),
    (
        "dim_vendor",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.dim_vendor (
            vendor_account    TEXT PRIMARY KEY,
            vendor_short      TEXT NOT NULL,
            vendor_name       TEXT,
            vendor_group      TEXT,
            currency          TEXT,
            payment_terms     TEXT,
            delivery_terms    TEXT,
            lead_time_days    NUMERIC(10, 2),
            moq_units         NUMERIC(18, 4),
            otif_pct          NUMERIC(10, 4),
            fill_pct          NUMERIC(10, 4),
            defect_pct        NUMERIC(10, 4),
            lead_adherence_pct NUMERIC(10, 4),
            CONSTRAINT uq_dim_vendor_short UNIQUE (vendor_short)
        )
        """,
    ),
    (
        "dim_store",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.dim_store (
            store_id          TEXT PRIMARY KEY,
            vertical_id       TEXT NOT NULL
                REFERENCES {SCHEMA}.dim_vertical (vertical_id),
            name              TEXT NOT NULL,
            cluster           TEXT,
            channel           TEXT,
            size_index        NUMERIC(10, 4),
            health_index      NUMERIC(10, 4),
            footfall_index    NUMERIC(10, 4),
            -- No source in the workbook; filled when D365 store master lands.
            invent_location_id TEXT,
            opened_at         DATE,
            closed_at         DATE
        )
        """,
    ),
    (
        "dim_item",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.dim_item (
            item_id           TEXT PRIMARY KEY,
            vertical_id       TEXT NOT NULL
                REFERENCES {SCHEMA}.dim_vertical (vertical_id),
            category_id       TEXT,
            category_name     TEXT,
            name              TEXT NOT NULL,
            brand             TEXT,
            vendor_account    TEXT
                REFERENCES {SCHEMA}.dim_vendor (vendor_account),
            is_perishable     BOOLEAN NOT NULL DEFAULT FALSE,
            shelf_life_days   INTEGER,
            sales_uom         TEXT,
            buy_uom           TEXT,
            pack_factor       NUMERIC(18, 4),
            lead_time_days    NUMERIC(10, 2),
            safety_days       NUMERIC(10, 2),
            base_ads          NUMERIC(18, 6),
            price             NUMERIC(18, 4),
            unit_cost         NUMERIC(18, 4),
            margin_pct        NUMERIC(10, 4),
            seasonality_index NUMERIC(10, 4),
            lifecycle         TEXT
        )
        """,
    ),
    (
        "dim_calendar",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.dim_calendar (
            cal_date          DATE PRIMARY KEY,
            dow               SMALLINT NOT NULL,
            iso_week          SMALLINT NOT NULL,
            month             SMALLINT NOT NULL,
            year              SMALLINT NOT NULL,
            is_weekend        BOOLEAN NOT NULL,
            is_payday_window  BOOLEAN NOT NULL,
            -- Estimated, not authoritative. See the seed script's docstring.
            is_ramadan_est    BOOLEAN NOT NULL DEFAULT FALSE,
            is_idulfitri_est  BOOLEAN NOT NULL DEFAULT FALSE
        )
        """,
    ),
    # --------------------------------------------------------------- assortment
    (
        "assortment",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.assortment (
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            store_key         TEXT NOT NULL REFERENCES {SCHEMA}.dim_store (store_id),
            valid_from        DATE NOT NULL,
            valid_to          DATE,
            PRIMARY KEY (item_key, store_key, valid_from)
        )
        """,
    ),
    # -------------------------------------------------------------------- facts
    (
        "fact_sales_daily",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_sales_daily (
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            store_key         TEXT NOT NULL REFERENCES {SCHEMA}.dim_store (store_id),
            cal_date          DATE NOT NULL,
            qty_sold          NUMERIC(18, 4) NOT NULL DEFAULT 0,
            revenue           NUMERIC(20, 4) NOT NULL DEFAULT 0,
            -- Demand on a stockout day is censored, not zero. Models must be
            -- able to exclude these rows rather than learn a false zero.
            is_stockout       BOOLEAN NOT NULL DEFAULT FALSE,
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            PRIMARY KEY (item_key, store_key, cal_date)
        ) PARTITION BY RANGE (cal_date)
        """,
    ),
    (
        "fact_sales_daily_default",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_sales_daily_default
            PARTITION OF {SCHEMA}.fact_sales_daily DEFAULT
        """,
    ),
    (
        "fact_inventory_daily",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_inventory_daily (
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            store_key         TEXT NOT NULL REFERENCES {SCHEMA}.dim_store (store_id),
            cal_date          DATE NOT NULL,
            on_hand_qty       NUMERIC(18, 4) NOT NULL DEFAULT 0,
            open_po_qty       NUMERIC(18, 4) NOT NULL DEFAULT 0,
            -- position = on hand + open PO; what D365 calls Position.
            position_qty      NUMERIC(18, 4) NOT NULL DEFAULT 0,
            rop_qty           NUMERIC(18, 4),
            days_cover        NUMERIC(12, 4),
            state             TEXT,
            is_stockout       BOOLEAN NOT NULL DEFAULT FALSE,
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            PRIMARY KEY (item_key, store_key, cal_date)
        ) PARTITION BY RANGE (cal_date)
        """,
    ),
    (
        "fact_inventory_daily_default",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_inventory_daily_default
            PARTITION OF {SCHEMA}.fact_inventory_daily DEFAULT
        """,
    ),
    (
        "fact_price_daily",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_price_daily (
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            store_key         TEXT NOT NULL REFERENCES {SCHEMA}.dim_store (store_id),
            cal_date          DATE NOT NULL,
            unit_price        NUMERIC(18, 4) NOT NULL,
            unit_cost         NUMERIC(18, 4),
            is_promo          BOOLEAN NOT NULL DEFAULT FALSE,
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            PRIMARY KEY (item_key, store_key, cal_date)
        )
        """,
    ),
    (
        "fact_promotion",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_promotion (
            promo_id          TEXT PRIMARY KEY,
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            store_key         TEXT REFERENCES {SCHEMA}.dim_store (store_id),
            start_date        DATE NOT NULL,
            end_date          DATE NOT NULL,
            discount_pct      NUMERIC(10, 4),
            mechanic          TEXT,
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            CONSTRAINT ck_promotion_dates CHECK (end_date >= start_date)
        )
        """,
    ),
    (
        "ux_promo_line",
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_promo_line
            ON {SCHEMA}.fact_promotion (item_key, store_key, start_date)
        """,
    ),
    (
        "fact_purchase_receipt",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_purchase_receipt (
            receipt_id        TEXT PRIMARY KEY,
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            store_key         TEXT NOT NULL REFERENCES {SCHEMA}.dim_store (store_id),
            vendor_account    TEXT REFERENCES {SCHEMA}.dim_vendor (vendor_account),
            ordered_date      DATE,
            received_date     DATE,
            ordered_qty       NUMERIC(18, 4),
            received_qty      NUMERIC(18, 4),
            import_batch_id   BIGINT REFERENCES audit.import_batches (id)
        )
        """,
    ),
    # ----------------------------------------------------------------- forecast
    (
        "forecast_run",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.forecast_run (
            run_id            BIGSERIAL PRIMARY KEY,
            model_version     TEXT NOT NULL,
            as_of_date        DATE NOT NULL,
            horizon_days      SMALLINT NOT NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            CONSTRAINT uq_forecast_run UNIQUE (model_version, as_of_date, horizon_days)
        )
        """,
    ),
    (
        "forecast_daily",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.forecast_daily (
            run_id            BIGINT NOT NULL REFERENCES {SCHEMA}.forecast_run (run_id)
                ON DELETE CASCADE,
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            store_key         TEXT NOT NULL REFERENCES {SCHEMA}.dim_store (store_id),
            target_date       DATE NOT NULL,
            yhat              NUMERIC(18, 4) NOT NULL,
            yhat_lo           NUMERIC(18, 4),
            yhat_hi           NUMERIC(18, 4),
            PRIMARY KEY (run_id, item_key, store_key, target_date)
        ) PARTITION BY RANGE (target_date)
        """,
    ),
    (
        "forecast_daily_default",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.forecast_daily_default
            PARTITION OF {SCHEMA}.forecast_daily DEFAULT
        """,
    ),
    (
        "forecast_accuracy",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.forecast_accuracy (
            run_id            BIGINT NOT NULL REFERENCES {SCHEMA}.forecast_run (run_id)
                ON DELETE CASCADE,
            horizon           SMALLINT NOT NULL,
            model_version     TEXT NOT NULL,
            wape              NUMERIC(10, 4),
            bias              NUMERIC(10, 4),
            mape              NUMERIC(10, 4),
            n_obs             INTEGER NOT NULL DEFAULT 0,
            computed_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (run_id, horizon)
        )
        """,
    ),
    # ------------------------------------------------------------------ indexes
    (
        "ix_sales_date",
        f"CREATE INDEX IF NOT EXISTS ix_sales_date"
        f" ON {SCHEMA}.fact_sales_daily (cal_date)",
    ),
    (
        "ix_sales_item_date",
        f"CREATE INDEX IF NOT EXISTS ix_sales_item_date"
        f" ON {SCHEMA}.fact_sales_daily (item_key, cal_date)",
    ),
    (
        "ix_inventory_date",
        f"CREATE INDEX IF NOT EXISTS ix_inventory_date"
        f" ON {SCHEMA}.fact_inventory_daily (cal_date)",
    ),
    (
        "ix_forecast_target",
        f"CREATE INDEX IF NOT EXISTS ix_forecast_target"
        f" ON {SCHEMA}.forecast_daily (target_date)",
    ),
    (
        "ix_forecast_item_store_target",
        f"CREATE INDEX IF NOT EXISTS ix_forecast_item_store_target"
        f" ON {SCHEMA}.forecast_daily (item_key, store_key, target_date)",
    ),
]


def main() -> int:
    engine = get_engine()

    with engine.begin() as connection:
        for label, statement in STATEMENTS:
            connection.execute(text(statement))
            print(f"  ok  {label}")

    with engine.connect() as connection:
        tables = connection.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = :schema
                ORDER BY table_name
                """
            ),
            {"schema": SCHEMA},
        ).scalars().all()

    print(f"\nSchema {SCHEMA}: {len(tables)} tables")
    for name in tables:
        print(f"  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
