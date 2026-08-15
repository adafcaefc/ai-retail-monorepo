-- Monthly range partitioning for the daily retail fact tables (Azure SQL).
--
-- Why now: these tables are empty or nearly so today, and rebuilding a
-- clustered index is proportional to the rows under it. The same change once
-- the ~15 GB company extract has landed would rewrite every one of those rows.
--
-- What this buys: partition elimination. `fact_sales_daily` at store x SKU x
-- day grows by roughly 16k rows a day, so a single "last month" query would
-- otherwise scan every year ever loaded. It also makes per-period maintenance
-- (rebuild, truncate, switch) a per-partition operation instead of a
-- whole-table one.
--
-- What it does NOT buy: space. Azure SQL Database exposes one filegroup, so
-- every partition lands on PRIMARY -- this is about scan boundaries, not
-- storage placement, and it does not move the 32 GB ceiling on this tier.
--
-- Scope: only the five tables whose grain is genuinely daily AND whose primary
-- key already contains the date column, so the clustered key does not change:
--
--     fact_sales_daily             PK(item_key, store_key, cal_date)
--     fact_inventory_daily         PK(item_key, store_key, cal_date)
--     fact_price_daily             PK(item_key, store_key, cal_date)
--     fact_inventory_chain_daily   PK(item_key, cal_date)
--     forecast_daily               PK(run_id, item_key, store_key, target_date)
--
-- Deliberately excluded: fact_gmv_monthly (192 rows, already monthly grain,
-- and keyed on year_index/month_index rather than a date), fact_promotion and
-- fact_purchase_receipt (keyed on promo_id/receipt_id with no date in the key,
-- so partitioning them would mean widening their primary key -- a data-model
-- decision, not a performance one), and the small forecast_run/
-- forecast_accuracy metadata tables.
--
-- Re-runnable: every step is guarded, so applying this twice is a no-op.
--
-- APPLIED to free-sql-db-0067773 on 2026-08-15. All five tables came back with
-- 73 partitions, row counts unchanged (fact_inventory_daily 16,000,
-- fact_inventory_chain_daily 800), and the five excluded tables still on 1.
-- Every existing row is dated 2026-07-01 and landed in partition 32, whose
-- lower boundary is 2026-07-01 -- and a query filtered to that month reads 1
-- partition of the 73, which is the elimination this migration exists for.
-- Backend suite after the change: 661 passed, 7 skipped.
--
-- Verify afterwards with:
--     SELECT t.name, COUNT(p.partition_number)
--     FROM sys.tables t
--     JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id = 1
--     GROUP BY t.name;

SET XACT_ABORT ON;
GO

-------------------------------------------------------------------------------
-- 1. Partition function: one boundary per month.
-------------------------------------------------------------------------------
-- RANGE RIGHT so each boundary is the first day of its own month, which is how
-- the dates are actually written -- RANGE LEFT would need the last day of each
-- month and turn every boundary into a leap-year question.
--
-- Range runs 2024-01-01 (dim_calendar's first day) to 2030-01-01. Rows outside
-- it are not rejected: anything earlier lands in the leading partition and
-- anything later in the trailing one, so a late extract still loads correctly,
-- just without elimination until the range is extended with SPLIT RANGE.
IF NOT EXISTS (SELECT 1 FROM sys.partition_functions WHERE name = 'pf_retail_month')
BEGIN
    DECLARE @boundaries nvarchar(max) = N'';
    DECLARE @d date = '2024-01-01';

    WHILE @d < '2030-01-01'
    BEGIN
        SET @boundaries = @boundaries
            + CASE WHEN @boundaries = N'' THEN N'' ELSE N', ' END
            + N'''' + CONVERT(char(10), @d, 23) + N'''';
        SET @d = DATEADD(month, 1, @d);
    END

    EXEC(N'CREATE PARTITION FUNCTION pf_retail_month (date)
           AS RANGE RIGHT FOR VALUES (' + @boundaries + N')');
END
GO

-------------------------------------------------------------------------------
-- 2. Partition scheme.
-------------------------------------------------------------------------------
-- ALL TO ([PRIMARY]) is not a simplification: Azure SQL Database has no
-- user-defined filegroups, so PRIMARY is the only target available.
IF NOT EXISTS (SELECT 1 FROM sys.partition_schemes WHERE name = 'ps_retail_month')
    CREATE PARTITION SCHEME ps_retail_month
        AS PARTITION pf_retail_month ALL TO ([PRIMARY]);
GO

-------------------------------------------------------------------------------
-- 3. Move each table's clustered primary key onto the scheme.
-------------------------------------------------------------------------------
-- DROP_EXISTING would be tidier, but it cannot move a PRIMARY KEY constraint
-- between data spaces, so each key is dropped and recreated. Safe here because
-- no foreign key references any of these tables -- verified against
-- sys.foreign_keys before writing this; re-check if that ever changes, as the
-- DROP would then fail rather than silently orphan anything.
--
-- Non-clustered indexes are recreated on the same scheme ("aligned"). An
-- unaligned index would keep its own unpartitioned structure, which blocks
-- partition switching later and is the usual reason a partitioning migration
-- has to be redone.

-- fact_sales_daily -----------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes i
           WHERE i.object_id = OBJECT_ID('retail.fact_sales_daily')
             AND i.index_id = 1 AND i.data_space_id != (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    DROP INDEX IF EXISTS ix_sales_date ON retail.fact_sales_daily;
    DROP INDEX IF EXISTS ix_sales_item_date ON retail.fact_sales_daily;

    ALTER TABLE retail.fact_sales_daily
        DROP CONSTRAINT PK_retail_fact_sales_daily;
    ALTER TABLE retail.fact_sales_daily
        ADD CONSTRAINT PK_retail_fact_sales_daily
        PRIMARY KEY CLUSTERED (item_key, store_key, cal_date)
        ON ps_retail_month(cal_date);

    CREATE NONCLUSTERED INDEX ix_sales_date
        ON retail.fact_sales_daily (cal_date) ON ps_retail_month(cal_date);
    CREATE NONCLUSTERED INDEX ix_sales_item_date
        ON retail.fact_sales_daily (item_key, cal_date) ON ps_retail_month(cal_date);
END
GO

-- fact_inventory_daily -------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes i
           WHERE i.object_id = OBJECT_ID('retail.fact_inventory_daily')
             AND i.index_id = 1 AND i.data_space_id != (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    DROP INDEX IF EXISTS ix_inventory_date ON retail.fact_inventory_daily;

    ALTER TABLE retail.fact_inventory_daily
        DROP CONSTRAINT PK_retail_fact_inventory_daily;
    ALTER TABLE retail.fact_inventory_daily
        ADD CONSTRAINT PK_retail_fact_inventory_daily
        PRIMARY KEY CLUSTERED (item_key, store_key, cal_date)
        ON ps_retail_month(cal_date);

    CREATE NONCLUSTERED INDEX ix_inventory_date
        ON retail.fact_inventory_daily (cal_date) ON ps_retail_month(cal_date);
END
GO

-- fact_price_daily -----------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes i
           WHERE i.object_id = OBJECT_ID('retail.fact_price_daily')
             AND i.index_id = 1 AND i.data_space_id != (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    ALTER TABLE retail.fact_price_daily
        DROP CONSTRAINT PK_retail_fact_price_daily;
    ALTER TABLE retail.fact_price_daily
        ADD CONSTRAINT PK_retail_fact_price_daily
        PRIMARY KEY CLUSTERED (item_key, store_key, cal_date)
        ON ps_retail_month(cal_date);
END
GO

-- fact_inventory_chain_daily -------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes i
           WHERE i.object_id = OBJECT_ID('retail.fact_inventory_chain_daily')
             AND i.index_id = 1 AND i.data_space_id != (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    ALTER TABLE retail.fact_inventory_chain_daily
        DROP CONSTRAINT PK_retail_fact_inv_chain;
    ALTER TABLE retail.fact_inventory_chain_daily
        ADD CONSTRAINT PK_retail_fact_inv_chain
        PRIMARY KEY CLUSTERED (item_key, cal_date)
        ON ps_retail_month(cal_date);
END
GO

-- forecast_daily -------------------------------------------------------------
-- Partitioned on target_date (the date being forecast), not the run date: the
-- boards read this by horizon, so that is the column queries filter on.
IF EXISTS (SELECT 1 FROM sys.indexes i
           WHERE i.object_id = OBJECT_ID('retail.forecast_daily')
             AND i.index_id = 1 AND i.data_space_id != (
                 SELECT data_space_id FROM sys.partition_schemes
                 WHERE name = 'ps_retail_month'))
BEGIN
    DROP INDEX IF EXISTS ix_forecast_target ON retail.forecast_daily;
    DROP INDEX IF EXISTS ix_forecast_item_store_target ON retail.forecast_daily;

    ALTER TABLE retail.forecast_daily
        DROP CONSTRAINT PK_retail_forecast_daily;
    ALTER TABLE retail.forecast_daily
        ADD CONSTRAINT PK_retail_forecast_daily
        PRIMARY KEY CLUSTERED (run_id, item_key, store_key, target_date)
        ON ps_retail_month(target_date);

    CREATE NONCLUSTERED INDEX ix_forecast_target
        ON retail.forecast_daily (target_date) ON ps_retail_month(target_date);
    CREATE NONCLUSTERED INDEX ix_forecast_item_store_target
        ON retail.forecast_daily (item_key, store_key, target_date)
        ON ps_retail_month(target_date);
END
GO
