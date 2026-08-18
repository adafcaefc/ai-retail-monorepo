-- Undo 004. Drops the index first: a column cannot be dropped while an
-- index still includes it.
--
-- This discards whatever the re-seed wrote into these nine columns. Nothing
-- else reads them, so no other table or view breaks -- but the data is gone
-- until the seeder runs again.

SET XACT_ABORT ON;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'ix_StoreSkuSnapshot_markdown'
      AND object_id = OBJECT_ID('retail.StoreSkuSnapshot')
)
    DROP INDEX ix_StoreSkuSnapshot_markdown ON retail.StoreSkuSnapshot;
GO

IF COL_LENGTH('retail.StoreSkuSnapshot', 'markdown_recoverable') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN markdown_recoverable;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'markdown_at_risk_value') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN markdown_at_risk_value;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_ads') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN base_ads;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_position') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN base_position;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_rop') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN base_rop;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_max') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN base_max;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_state') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN base_state;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_at_risk') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN base_at_risk;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_order_value') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN base_order_value;
GO
IF COL_LENGTH('retail.StoreSkuSnapshot', 'base_forecast_7d') IS NOT NULL
    ALTER TABLE retail.StoreSkuSnapshot DROP COLUMN base_forecast_7d;
GO
