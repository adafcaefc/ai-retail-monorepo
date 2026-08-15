-- Undo 003_partition_fact_tables.sql: put the five fact tables back on a
-- single unpartitioned clustered index and remove the scheme and function.
--
-- Run this if the partitioning migration is applied and then needs reverting.
-- It restores exactly the shape the tables had beforehand: the same primary
-- key columns, the same non-clustered indexes, all on [PRIMARY].
--
-- This moves data, it does not delete it. Dropping a clustered primary key
-- leaves the rows behind as a heap and recreating one reorders them; at no
-- point is there a DELETE, TRUNCATE or DROP TABLE. The same is true of the
-- forward migration.
--
-- The partition scheme and function are dropped last, because SQL Server
-- refuses to drop either while any index still sits on it -- which doubles as
-- a check that every table really did come back off the scheme.
--
-- Re-runnable: each step is guarded, so running it twice is a no-op, and
-- running it when the migration was never applied does nothing at all.

SET XACT_ABORT ON;
GO

-- fact_sales_daily -----------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes
           WHERE object_id = OBJECT_ID('retail.fact_sales_daily')
             AND index_id = 1 AND data_space_id = (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    DROP INDEX IF EXISTS ix_sales_date ON retail.fact_sales_daily;
    DROP INDEX IF EXISTS ix_sales_item_date ON retail.fact_sales_daily;

    ALTER TABLE retail.fact_sales_daily DROP CONSTRAINT PK_retail_fact_sales_daily;
    ALTER TABLE retail.fact_sales_daily
        ADD CONSTRAINT PK_retail_fact_sales_daily
        PRIMARY KEY CLUSTERED (item_key, store_key, cal_date) ON [PRIMARY];

    CREATE NONCLUSTERED INDEX ix_sales_date
        ON retail.fact_sales_daily (cal_date) ON [PRIMARY];
    CREATE NONCLUSTERED INDEX ix_sales_item_date
        ON retail.fact_sales_daily (item_key, cal_date) ON [PRIMARY];
END
GO

-- fact_inventory_daily -------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes
           WHERE object_id = OBJECT_ID('retail.fact_inventory_daily')
             AND index_id = 1 AND data_space_id = (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    DROP INDEX IF EXISTS ix_inventory_date ON retail.fact_inventory_daily;

    ALTER TABLE retail.fact_inventory_daily DROP CONSTRAINT PK_retail_fact_inventory_daily;
    ALTER TABLE retail.fact_inventory_daily
        ADD CONSTRAINT PK_retail_fact_inventory_daily
        PRIMARY KEY CLUSTERED (item_key, store_key, cal_date) ON [PRIMARY];

    CREATE NONCLUSTERED INDEX ix_inventory_date
        ON retail.fact_inventory_daily (cal_date) ON [PRIMARY];
END
GO

-- fact_price_daily -----------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes
           WHERE object_id = OBJECT_ID('retail.fact_price_daily')
             AND index_id = 1 AND data_space_id = (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    ALTER TABLE retail.fact_price_daily DROP CONSTRAINT PK_retail_fact_price_daily;
    ALTER TABLE retail.fact_price_daily
        ADD CONSTRAINT PK_retail_fact_price_daily
        PRIMARY KEY CLUSTERED (item_key, store_key, cal_date) ON [PRIMARY];
END
GO

-- fact_inventory_chain_daily -------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes
           WHERE object_id = OBJECT_ID('retail.fact_inventory_chain_daily')
             AND index_id = 1 AND data_space_id = (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    ALTER TABLE retail.fact_inventory_chain_daily DROP CONSTRAINT PK_retail_fact_inv_chain;
    ALTER TABLE retail.fact_inventory_chain_daily
        ADD CONSTRAINT PK_retail_fact_inv_chain
        PRIMARY KEY CLUSTERED (item_key, cal_date) ON [PRIMARY];
END
GO

-- forecast_daily -------------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes
           WHERE object_id = OBJECT_ID('retail.forecast_daily')
             AND index_id = 1 AND data_space_id = (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    DROP INDEX IF EXISTS ix_forecast_target ON retail.forecast_daily;
    DROP INDEX IF EXISTS ix_forecast_item_store_target ON retail.forecast_daily;

    ALTER TABLE retail.forecast_daily DROP CONSTRAINT PK_retail_forecast_daily;
    ALTER TABLE retail.forecast_daily
        ADD CONSTRAINT PK_retail_forecast_daily
        PRIMARY KEY CLUSTERED (run_id, item_key, store_key, target_date) ON [PRIMARY];

    CREATE NONCLUSTERED INDEX ix_forecast_target
        ON retail.forecast_daily (target_date) ON [PRIMARY];
    CREATE NONCLUSTERED INDEX ix_forecast_item_store_target
        ON retail.forecast_daily (item_key, store_key, target_date) ON [PRIMARY];
END
GO

-- Scheme and function last -----------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.partition_schemes WHERE name = 'ps_retail_month')
    DROP PARTITION SCHEME ps_retail_month;
GO

IF EXISTS (SELECT 1 FROM sys.partition_functions WHERE name = 'pf_retail_month')
    DROP PARTITION FUNCTION pf_retail_month;
GO
