-- 004: the nine columns the revised workbook added to ENGINE_STORE.
--
-- Two markdown figures and the eight-column BASE block. `StoreSkuSnapshot`
-- predates all of them, so the loader had nowhere to put them and the
-- Pricing & Markdown board (Agent 5) could not be served from the database
-- at all -- its frontend falls back to a local workbook fixture whenever the
-- dashboard route answers empty, which is what it does today.
--
-- Why both markdown columns and not one: `markdown_at_risk_value` is the
-- gross exposure (ENGINE_STORE!AF) and `markdown_recoverable` is what a
-- markdown actually gets back after depth and sell-through (AA). They are
-- different numbers and the board shows both. The existing `at_risk_value`
-- column is neither -- it is inventory at risk (position x price where the
-- state is not Healthy), which is why it stays untouched here.
--
-- The BASE block is the same engine with every What-If lever forced to zero.
-- It is what makes a delta computable server-side instead of only in Excel.
--
-- Every column is NULL-able with no default: existing rows keep whatever
-- they have and the re-seed fills them. Nothing here rewrites data.
--
-- Rollback: 004_add_markdown_and_baseline_columns_rollback.sql

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'retail.StoreSkuSnapshot', N'U') IS NULL
    THROW 50004, 'retail.StoreSkuSnapshot does not exist; run 001 first.', 1;
GO

-- Guarded one at a time so a partially applied run can be re-run safely.
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

-- Agent 5 ranks by markdown exposure and filters to the three candidate
-- states, so it reads this pair together on every request.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_StoreSkuSnapshot_markdown'
      AND object_id = OBJECT_ID('retail.StoreSkuSnapshot')
)
    CREATE NONCLUSTERED INDEX ix_StoreSkuSnapshot_markdown
        ON retail.StoreSkuSnapshot (inventory_state)
        INCLUDE (markdown_at_risk_value, markdown_recoverable);
GO
