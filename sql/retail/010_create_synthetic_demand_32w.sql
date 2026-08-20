-- 010: the 32-week synthetic demand backbone, store x SKU.
--
-- `synthetic.demand_store_sku_32w` is what lets a board draw demand as a curve
-- instead of a flat rate. The workbook holds one ADS per SKU -- a snapshot with
-- no time axis -- so Replenishment's requirement chart could only accumulate a
-- straight line. This table carries 16 weeks of actual demand and 16 weeks of
-- forecast per store x SKU (160 x 800 = 16,000 rows), pivoted wide: one column
-- per week, no dates. "Today" is the boundary the naming encodes -- actual_w1
-- is the most recent actual week, forecast_w1 the next one ahead.
--
-- It is calibrated against the workbook, not independent of it: the chain's
-- SUM(forecast_w1) reproduces SUM(ads) x 7.45 (Constants!B7, the day-of-week
-- sum) to five significant figures, which is what the fixture builder checks
-- on every rebuild and what keeps the curve and the board's own ADS telling
-- one story.
--
-- Grain and keys match the source exactly: sku_id and store_id have full
-- referential integrity against retail.dim_item and retail.dim_store (800/800
-- and 160/160), so scope filters join straight through. `cat` is carried as
-- the table's own category id (e.g. DGT-C01) and is denormalised on purpose --
-- the queries here read it nowhere, but the POC export ships it and a rebuild
-- that dropped it would stop being byte-comparable against that export.
--
-- Seeded from resources/demand_store_sku_32w_poc_v1.csv by
-- scripts/seed_synthetic_demand_32w.py. The CSV is the source of truth; this
-- migration only creates the shape.
--
-- Rollback: 010_create_synthetic_demand_32w_rollback.sql

SET XACT_ABORT ON;
GO

IF SCHEMA_ID(N'synthetic') IS NULL
    EXEC('CREATE SCHEMA synthetic;');
GO

IF OBJECT_ID(N'synthetic.demand_store_sku_32w', N'U') IS NOT NULL
    THROW 50010, 'synthetic.demand_store_sku_32w already exists; this migration only creates it.', 1;
GO

CREATE TABLE synthetic.demand_store_sku_32w (
    sku_id       NVARCHAR(30)  NOT NULL,
    store_id     NVARCHAR(20)  NOT NULL,
    cat          NVARCHAR(30)  NOT NULL,
    actual_w16   DECIMAL(20,6) NOT NULL,
    actual_w15   DECIMAL(20,6) NOT NULL,
    actual_w14   DECIMAL(20,6) NOT NULL,
    actual_w13   DECIMAL(20,6) NOT NULL,
    actual_w12   DECIMAL(20,6) NOT NULL,
    actual_w11   DECIMAL(20,6) NOT NULL,
    actual_w10   DECIMAL(20,6) NOT NULL,
    actual_w9    DECIMAL(20,6) NOT NULL,
    actual_w8    DECIMAL(20,6) NOT NULL,
    actual_w7    DECIMAL(20,6) NOT NULL,
    actual_w6    DECIMAL(20,6) NOT NULL,
    actual_w5    DECIMAL(20,6) NOT NULL,
    actual_w4    DECIMAL(20,6) NOT NULL,
    actual_w3    DECIMAL(20,6) NOT NULL,
    actual_w2    DECIMAL(20,6) NOT NULL,
    actual_w1    DECIMAL(20,6) NOT NULL,
    forecast_w1  DECIMAL(20,6) NOT NULL,
    forecast_w2  DECIMAL(20,6) NOT NULL,
    forecast_w3  DECIMAL(20,6) NOT NULL,
    forecast_w4  DECIMAL(20,6) NOT NULL,
    forecast_w5  DECIMAL(20,6) NOT NULL,
    forecast_w6  DECIMAL(20,6) NOT NULL,
    forecast_w7  DECIMAL(20,6) NOT NULL,
    forecast_w8  DECIMAL(20,6) NOT NULL,
    forecast_w9  DECIMAL(20,6) NOT NULL,
    forecast_w10 DECIMAL(20,6) NOT NULL,
    forecast_w11 DECIMAL(20,6) NOT NULL,
    forecast_w12 DECIMAL(20,6) NOT NULL,
    forecast_w13 DECIMAL(20,6) NOT NULL,
    forecast_w14 DECIMAL(20,6) NOT NULL,
    forecast_w15 DECIMAL(20,6) NOT NULL,
    forecast_w16 DECIMAL(20,6) NOT NULL,
    CONSTRAINT PK_synthetic_demand_store_sku_32w PRIMARY KEY (sku_id, store_id)
);
GO
