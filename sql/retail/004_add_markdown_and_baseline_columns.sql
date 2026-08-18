-- 004: the ten columns the revised workbook added to ENGINE_STORE.
--
-- Two markdown figures and the eight-column BASE block, added to BOTH store-
-- grain tables:
--
--   retail.fact_inventory_daily  -- what the agent boards actually query
--   retail.StoreSkuSnapshot      -- what the RAG bootstrap loads and embeds
--
-- Getting only the snapshot table would have looked right and served nothing:
-- every retail dashboard reads `fact_inventory_daily`, and Agent 5 sums
-- markdown exposure across a SKU's stores from exactly that grain.
--
-- `markdown_at_risk_value` is gross exposure (ENGINE_STORE!AF);
-- `markdown_recoverable` is what a markdown actually recovers once depth and
-- sell-through are applied (AA). They are different numbers and the Pricing &
-- Markdown board shows both. Neither is the existing `at_risk_value`, which is
-- inventory at risk -- position x price where state is not Healthy -- so that
-- column is left alone.
--
-- The BASE block is the same engine with every What-If lever forced to zero,
-- which is what makes a delta computable in SQL instead of only in Excel.
--
-- Every column is NULL-able with no default, so this is a metadata-only change
-- even on the partitioned fact table: existing rows keep what they have and the
-- re-seed fills the rest. Nothing here rewrites data.
--
-- Rollback: 004_add_markdown_and_baseline_columns_rollback.sql

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'retail.fact_inventory_daily', N'U') IS NULL
    THROW 50004, 'retail.fact_inventory_daily does not exist; run 002 first.', 1;
GO
IF OBJECT_ID(N'retail.StoreSkuSnapshot', N'U') IS NULL
    THROW 50004, 'retail.StoreSkuSnapshot does not exist; run 001 first.', 1;
GO

-- Guarded one at a time so a partially applied run can be re-run safely.
IF COL_LENGTH('retail.fact_inventory_daily', 'markdown_recoverable') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD markdown_recoverable DECIMAL(28,4) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'markdown_at_risk_value') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD markdown_at_risk_value DECIMAL(28,4) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'base_ads') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD base_ads DECIMAL(28,8) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'base_position') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD base_position DECIMAL(28,6) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'base_rop') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD base_rop DECIMAL(28,6) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'base_max') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD base_max DECIMAL(28,6) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'base_state') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD base_state NVARCHAR(40) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'base_at_risk') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD base_at_risk DECIMAL(28,4) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'base_order_value') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD base_order_value DECIMAL(28,4) NULL;
GO
IF COL_LENGTH('retail.fact_inventory_daily', 'base_forecast_7d') IS NULL
    ALTER TABLE retail.fact_inventory_daily ADD base_forecast_7d DECIMAL(28,8) NULL;
GO

IF COL_LENGTH('retail.StoreSkuSnapshot', 'markdown_recoverable') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD markdown_recoverable DECIMAL(28,4) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'markdown_at_risk_value') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD markdown_at_risk_value DECIMAL(28,4) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_ads') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD base_ads DECIMAL(28,8) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_position') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD base_position DECIMAL(28,6) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_rop') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD base_rop DECIMAL(28,6) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_max') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD base_max DECIMAL(28,6) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_state') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD base_state NVARCHAR(40) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_at_risk') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD base_at_risk DECIMAL(28,4) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_order_value') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD base_order_value DECIMAL(28,4) NULL;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_forecast_7d') IS NULL
    ALTER TABLE retail.StoreSkuSnapshot ADD base_forecast_7d DECIMAL(28,8) NULL;
GO

-- Agent 5 filters to the three markdown candidate states and ranks by
-- exposure, so it reads this pair together on every request. Aligned to the
-- monthly partition scheme from 003, or it could not be built on this table.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_fact_inventory_daily_markdown'
      AND object_id = OBJECT_ID('retail.fact_inventory_daily')
)
    CREATE NONCLUSTERED INDEX ix_fact_inventory_daily_markdown
        ON retail.fact_inventory_daily (cal_date, state)
        INCLUDE (markdown_at_risk_value, markdown_recoverable)
        ON ps_retail_month (cal_date);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_StoreSkuSnapshot_markdown'
      AND object_id = OBJECT_ID('retail.StoreSkuSnapshot')
)
    CREATE NONCLUSTERED INDEX ix_StoreSkuSnapshot_markdown
        ON retail.StoreSkuSnapshot (inventory_state)
        INCLUDE (markdown_at_risk_value, markdown_recoverable);
GO
