"""SUPERSEDED: the backend now runs on Azure SQL exclusively (get_engine() in
src/db/db.py builds an mssql+pyodbc connection from AZURE_SQL_CONNECTIONSTRING),
and this script's DDL is Postgres syntax (`CREATE TABLE IF NOT EXISTS`, TEXT,
BOOLEAN, PARTITION BY RANGE, ...), which will fail against Azure SQL. The
current schema definition is sql/retail/002_create_orm_schema.sql — apply it
the same way sql/ai/001_create_ai_vector_schema.sql is applied (see
src/retail_data_bootstrap/database.py:apply_migration). Kept here only as the
historical record of the Postgres-era shape this schema was translated from.

Create the `retail` schema: dimensions, facts, and forecast tables.

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

`fact_inventory_chain_daily` is a second grain of the same measurement, and it
is not redundant with `fact_inventory_daily`. The workbook's chain-level ENGINE
sheet is NOT the per-store grid rolled up: each store row rounds independently,
so summing twenty rounded quantities lands a few percent away from rounding the
chain total once (`rop` drifts up to 4.5%), and the chain-level `state` is
evaluated on chain-level inputs rather than voted on across stores — which
moves `at_risk_value` by orders of magnitude. Every A-sheet reconciles against
the chain figures, so they are stored rather than derived.

`trade_agreement` and `replenishment_proposal` were added after the first cut,
which had modelled the D365 time series faithfully but left Agent 3 with
nowhere to read from: the workbook's 2,400 vendor quotes and 800 proposed
orders had no table, and `fact_purchase_receipt` is not a substitute — it
records what arrived, and replenishment is about what has not been ordered yet.
Both names are D365's own, so the eventual swap stays a data change.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
            d365_data_area    TEXT,
            -- The workbook's own row order. Not cosmetic: the dropdowns follow
            -- it, and alphabetical would put Digital first on a board whose
            -- readers have looked at Grocery first for as long as it existed.
            sort_order        INTEGER
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
            lifecycle         TEXT,
            -- Read by the What-If engine, not by any report. `f01` prices a
            -- promo lift from `is_promo_eligible` and `cannibalisation_pct`,
            -- and `f07` classifies a slow mover by `growth_index`. Without
            -- them a lever moves and nothing happens.
            growth_index      NUMERIC(10, 4),
            is_promo_eligible BOOLEAN NOT NULL DEFAULT FALSE,
            cannibalisation_pct NUMERIC(10, 4),
            elasticity        NUMERIC(10, 4),
            is_viral          BOOLEAN NOT NULL DEFAULT FALSE
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
            on_hand_qty       DOUBLE PRECISION NOT NULL DEFAULT 0,
            open_po_qty       DOUBLE PRECISION NOT NULL DEFAULT 0,
            -- position = on hand + open PO; what D365 calls Position.
            position_qty      DOUBLE PRECISION NOT NULL DEFAULT 0,
            rop_qty           NUMERIC(18, 4),
            -- The up-to level the policy orders back to. ROP says *when* to
            -- order; Max says *how much*, because the order is
            -- `max(0, Max - Position)`. Storing one without the other leaves
            -- every purchase-order figure underivable from this table.
            max_qty           NUMERIC(18, 4),
            days_cover        DOUBLE PRECISION,
            state             TEXT,
            is_stockout       BOOLEAN NOT NULL DEFAULT FALSE,
            -- What ENGINE_STORE itself computed for this line. Re-deriving
            -- them in SQL lands about 3% off, for the same reason chain-net is
            -- not the per-store roll-up: the workbook rounds each row before
            -- pricing it, so recomputing from rounded quantities compounds.
            ads               DOUBLE PRECISION,
            forecast_7d       DOUBLE PRECISION,
            order_qty_sales   DOUBLE PRECISION,
            order_qty_buy     DOUBLE PRECISION,
            order_value       NUMERIC(20, 4),
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
    (
        "fact_inventory_chain_daily",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_inventory_chain_daily (
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            cal_date          DATE NOT NULL REFERENCES {SCHEMA}.dim_calendar (cal_date),
            ads               DOUBLE PRECISION,
            on_hand_qty       NUMERIC(18, 4) NOT NULL DEFAULT 0,
            open_po_qty       NUMERIC(18, 4) NOT NULL DEFAULT 0,
            position_qty      NUMERIC(18, 4) NOT NULL DEFAULT 0,
            rop_qty           NUMERIC(18, 4),
            max_qty           NUMERIC(18, 4),
            days_cover        DOUBLE PRECISION,
            state             TEXT,
            unit_price        NUMERIC(18, 4),
            inventory_value   NUMERIC(20, 4),
            at_risk_value     NUMERIC(20, 4),
            expiry_units      DOUBLE PRECISION,
            order_units       NUMERIC(18, 4),
            order_value       NUMERIC(20, 4),
            weekly_gmv        NUMERIC(20, 4),
            margin_rp         NUMERIC(20, 4),
            funding_rp        NUMERIC(20, 4),
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            PRIMARY KEY (item_key, cal_date)
        )
        """,
    ),
    (
        "fact_gmv_monthly",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.fact_gmv_monthly (
            vertical_id       TEXT NOT NULL
                REFERENCES {SCHEMA}.dim_vertical (vertical_id),
            year_index        SMALLINT NOT NULL,
            month_index       SMALLINT NOT NULL,
            gmv               NUMERIC(22, 4) NOT NULL,
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            PRIMARY KEY (vertical_id, year_index, month_index)
        )
        """,
    ),
    (
        "agent_kpi_reference",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.agent_kpi_reference (
            agent_id          TEXT NOT NULL,
            vertical_id       TEXT NOT NULL
                REFERENCES {SCHEMA}.dim_vertical (vertical_id),
            metric            TEXT NOT NULL,
            value             DOUBLE PRECISION,
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            PRIMARY KEY (agent_id, vertical_id, metric)
        )
        """,
    ),
    # ------------------------------------------------------------- sourcing
    # Two tables the first cut of this schema had no room for, which left
    # Agent 3 with nothing to read. `fact_purchase_receipt` is not a stand-in
    # for either: it records what *arrived*, and replenishment is about what
    # has not been ordered yet.
    #
    # Both names are D365's own. A trade agreement is how D365 states a
    # negotiated price for an item from a vendor; a planned order is what its
    # master planning proposes before anybody approves it. Borrowing the
    # vocabulary keeps the eventual D365 swap a data change rather than a
    # remodelling.
    (
        "trade_agreement",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.trade_agreement (
            item_key          TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            vendor_account    TEXT NOT NULL REFERENCES {SCHEMA}.dim_vendor (vendor_account),
            -- Several vendors quote the same item, and the cheapest is not
            -- always the designated one. That gap is the only figure on the
            -- Replenishment board that proposes an action.
            unit_price        NUMERIC(18, 4) NOT NULL,
            currency          TEXT NOT NULL DEFAULT 'IDR',
            min_qty_break     NUMERIC(18, 4),
            lead_time_days    INTEGER,
            discount_pct      NUMERIC(9, 6),
            valid_from        DATE,
            valid_to          DATE,
            is_designated     BOOLEAN NOT NULL DEFAULT FALSE,
            import_batch_id   BIGINT REFERENCES audit.import_batches (id),
            -- One agreement per item, vendor and validity window: a vendor may
            -- requote the same item next quarter without replacing history.
            PRIMARY KEY (item_key, vendor_account, valid_from)
        )
        """,
    ),
    (
        "replenishment_proposal",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.replenishment_proposal (
            item_key            TEXT NOT NULL REFERENCES {SCHEMA}.dim_item (item_id),
            as_of_date          DATE NOT NULL,
            qty_on_hand         NUMERIC(18, 4) NOT NULL DEFAULT 0,
            open_po_qty         NUMERIC(18, 4) NOT NULL DEFAULT 0,
            demand_per_day      NUMERIC(18, 4),
            rop_qty             NUMERIC(18, 4),
            max_qty             NUMERIC(18, 4),
            is_reorder          BOOLEAN NOT NULL DEFAULT FALSE,
            -- Sales units are what the shortfall is measured in; buy units are
            -- whole packs. `buy x pack >= sales` always, and the overshoot is
            -- real stock, so both are stored rather than one being derived.
            order_qty_sales     NUMERIC(18, 4) NOT NULL DEFAULT 0,
            order_qty_buy       NUMERIC(18, 4) NOT NULL DEFAULT 0,
            buy_uom             TEXT,
            designated_vendor   TEXT REFERENCES {SCHEMA}.dim_vendor (vendor_account),
            unit_price_ta       NUMERIC(18, 4),
            -- At the trade-agreement price, which is what the order costs.
            -- The selling-price total lives on the board, not here: a purchase
            -- order priced at retail is not a number anyone should approve.
            amount              NUMERIC(18, 4),
            best_price_vendor   TEXT REFERENCES {SCHEMA}.dim_vendor (vendor_account),
            best_price          NUMERIC(18, 4),
            saving_vs_designated NUMERIC(18, 4),
            import_batch_id     BIGINT REFERENCES audit.import_batches (id),
            PRIMARY KEY (item_key, as_of_date)
        )
        """,
    ),
    # ----------------------------------------------------------- promotion (A4)
    # Agent 4 reads two workbook sheets the curated schema had no home for. Both
    # are demonstration data straight from the A4 Promotion and Promotion &
    # Discount Detail sheets; `vertical_label` is the sheet's own wording and is
    # resolved to `dim_vertical.vertical_id` via `dashboard_label` at read time,
    # exactly as `agent_kpi_reference` is. `fact_promotion` exists too, but it is
    # deliberately empty and models a per-item promotion fact, not the campaign
    # plan these sheets hold -- do not repurpose it.
    (
        "promotion_detail",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.promotion_detail (
            promo_id              TEXT PRIMARY KEY,
            promo_name            TEXT NOT NULL,
            discount_type         TEXT NOT NULL,
            scope                 TEXT NOT NULL,
            vertical_label        TEXT NOT NULL,
            target_category       TEXT NOT NULL,
            season                TEXT NOT NULL,
            peak_month            TEXT NOT NULL,
            mechanism             TEXT NOT NULL,
            discount_pct          INTEGER,
            value_rule            TEXT NOT NULL,
            min_qty_threshold     TEXT NOT NULL,
            supplier_funding_pct  INTEGER NOT NULL,
            expected_uplift_pct   INTEGER NOT NULL,
            pre_buy_uplift_units  INTEGER NOT NULL,
            valid_from            DATE NOT NULL,
            valid_to              DATE NOT NULL,
            d365_construct        TEXT NOT NULL,
            source_row            INTEGER NOT NULL,
            CONSTRAINT ck_promo_detail_dates CHECK (valid_to >= valid_from)
        )
        """,
    ),
    (
        "promotion_vertical_kpi",
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.promotion_vertical_kpi (
            vertical_label        TEXT PRIMARY KEY,
            active_promo_skus     INTEGER NOT NULL,
            uplift_pct            NUMERIC(10, 4) NOT NULL,
            incremental_margin    NUMERIC(20, 4) NOT NULL,
            roi_x                 NUMERIC(10, 4) NOT NULL,
            cannib_pct            NUMERIC(10, 4) NOT NULL,
            funding_pct           NUMERIC(10, 4) NOT NULL
        )
        """,
    ),
    (
        "ix_promotion_detail_vertical",
        f"CREATE INDEX IF NOT EXISTS ix_promotion_detail_vertical"
        f" ON {SCHEMA}.promotion_detail (vertical_label)",
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
    # ----------------------------------------------------------- migrations
    # `CREATE TABLE IF NOT EXISTS` is a no-op on a table that already exists,
    # so a column added to a definition above never reaches a database created
    # before it. These statements carry those additions forward. Each must be
    # idempotent in its own right, because this script's whole contract is that
    # running it twice is safe.
    (
        "fact_inventory_daily.max_qty",
        f"ALTER TABLE {SCHEMA}.fact_inventory_daily"
        f" ADD COLUMN IF NOT EXISTS max_qty NUMERIC(18, 4)",
    ),
    # NUMERIC is right for money and wrong for these. `ads`, `days_cover`,
    # `expiry_units` and `base_ads` are computed measures carrying the full
    # precision of an IEEE double — `NUMERIC(18, 6)` silently truncated
    # `496.869179208` to `496.869179`, and the boards then failed to reproduce
    # the workbook they reconcile against. Money columns stay NUMERIC, where
    # exactness in base ten is the whole point.
    (
        "fact_inventory_chain_daily.ads -> float",
        f"ALTER TABLE {SCHEMA}.fact_inventory_chain_daily"
        f" ALTER COLUMN ads TYPE DOUBLE PRECISION,"
        f" ALTER COLUMN days_cover TYPE DOUBLE PRECISION,"
        f" ALTER COLUMN expiry_units TYPE DOUBLE PRECISION",
    ),
    (
        "fact_inventory_daily.days_cover -> float",
        f"ALTER TABLE {SCHEMA}.fact_inventory_daily"
        f" ALTER COLUMN days_cover TYPE DOUBLE PRECISION",
    ),
    (
        "dim_item.base_ads -> float",
        f"ALTER TABLE {SCHEMA}.dim_item"
        f" ALTER COLUMN base_ads TYPE DOUBLE PRECISION",
    ),
    (
        "fact_inventory_daily quantities -> float",
        f"ALTER TABLE {SCHEMA}.fact_inventory_daily"
        f" ALTER COLUMN on_hand_qty TYPE DOUBLE PRECISION,"
        f" ALTER COLUMN open_po_qty TYPE DOUBLE PRECISION,"
        f" ALTER COLUMN position_qty TYPE DOUBLE PRECISION",
    ),
    (
        "fact_inventory_daily order columns",
        f"ALTER TABLE {SCHEMA}.fact_inventory_daily"
        f" ADD COLUMN IF NOT EXISTS order_qty_sales DOUBLE PRECISION,"
        f" ADD COLUMN IF NOT EXISTS order_qty_buy DOUBLE PRECISION,"
        f" ADD COLUMN IF NOT EXISTS order_value NUMERIC(20, 4),"
        f" ADD COLUMN IF NOT EXISTS ads DOUBLE PRECISION,"
        f" ADD COLUMN IF NOT EXISTS forecast_7d DOUBLE PRECISION",
    ),
    (
        "dim_item.is_viral",
        f"ALTER TABLE {SCHEMA}.dim_item"
        f" ADD COLUMN IF NOT EXISTS is_viral BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    (
        "dim_vertical.sort_order",
        f"ALTER TABLE {SCHEMA}.dim_vertical"
        f" ADD COLUMN IF NOT EXISTS sort_order INTEGER",
    ),
    (
        "dim_item what-if attributes",
        f"ALTER TABLE {SCHEMA}.dim_item"
        f" ADD COLUMN IF NOT EXISTS growth_index NUMERIC(10, 4),"
        f" ADD COLUMN IF NOT EXISTS is_promo_eligible BOOLEAN NOT NULL DEFAULT FALSE,"
        f" ADD COLUMN IF NOT EXISTS cannibalisation_pct NUMERIC(10, 4),"
        f" ADD COLUMN IF NOT EXISTS elasticity NUMERIC(10, 4),"
        # SKU_Master col S (fund_pct). Needed by Agent 4's f13 promo margin,
        # which takes per-SKU supplier funding as a fraction. Stored as a
        # fraction (0.4862), matching sku_master and cannibalisation_pct.
        f" ADD COLUMN IF NOT EXISTS funding_pct NUMERIC(10, 4)",
    ),
    # The two SKU attributes that let a board scope to ONE store without
    # shipping the 16,000-row grid.
    #
    #     on_hand(sku, store) = base_ads * onhand_days * stock_factor
    #                           * store.health_index * store.size_index
    #
    # Verified against all 16,000 `ENGINE_STORE` rows at zero difference, so
    # the per-store position a store-scoped board shows is the workbook's own
    # rather than an approximation of it. `dim_store` already carries
    # `size_index` and `health_index`; these were the missing half.
    #
    # DOUBLE PRECISION, not NUMERIC, and `stock_factor` is why: it carries five
    # decimals (1.03793), which `NUMERIC(10, 4)` would silently round to
    # 1.0379 -- the same truncation that already cost this schema a round of
    # debugging on `ads` and `base_ads` above.
    (
        "dim_item per-store derivation inputs",
        f"ALTER TABLE {SCHEMA}.dim_item"
        f" ADD COLUMN IF NOT EXISTS onhand_days DOUBLE PRECISION,"
        f" ADD COLUMN IF NOT EXISTS stock_factor DOUBLE PRECISION",
    ),
    # Sourcing lookups: every board query starts from one vendor's book or one
    # item's quotes, and both tables are read far more often than written.
    (
        "ix_trade_agreement_vendor",
        f"CREATE INDEX IF NOT EXISTS ix_trade_agreement_vendor"
        f" ON {SCHEMA}.trade_agreement (vendor_account)",
    ),
    (
        "ix_replenishment_proposal_reorder",
        f"CREATE INDEX IF NOT EXISTS ix_replenishment_proposal_reorder"
        f" ON {SCHEMA}.replenishment_proposal (as_of_date, is_reorder)",
    ),
]


def ensure_audit_batches(engine: Any) -> None:
    """Create `audit.import_batches`, which every fact table references.

    Eight tables below carry `import_batch_id REFERENCES audit.import_batches`,
    and nothing else in this repository creates that table — it exists on the
    servers this schema was first built against because an earlier import put
    it there. On a database created from scratch, the first fact statement
    fails on a missing relation, which reads like a bug in this script rather
    than a missing prerequisite.

    Built from `ImportBatch` rather than from hand-written DDL: the model is
    the definition, and a second copy here would drift from it silently.
    """
    from src.db.models import ImportBatch  # noqa: PLC0415 - needs sys.path above

    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS audit"))
    ImportBatch.__table__.create(engine, checkfirst=True)


def main() -> int:
    engine = get_engine()

    ensure_audit_batches(engine)
    print("  ok  audit.import_batches")

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
