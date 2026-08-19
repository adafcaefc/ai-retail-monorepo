-- 006: demand archetype, from SKU_Master!Pattern (archetype) (v8.5).
--
-- v8.5 adds a demand-archetype label per SKU that the ADS-per-store formula
-- now factors into its multiplier (archHzFactor), alongside the new
-- Constants rows Horizon (B23) and hzCov (B24) -- see resources/formula.md's
-- "ADS (per store)" and "Max" entries. No dim_item column has ever carried
-- it. Same shape as 004/005: the source data already exists in
-- resources/dbtemp/schema_with_data.json (sku_master.pattern_archetype),
-- it was just never given a column.
--
-- Nullable with no default, so this is a metadata-only change: existing rows
-- keep NULL until scripts/seed_retail_dims_from_json.py re-runs and fills it.
--
-- Rollback: 006_add_dim_item_archetype_pattern_rollback.sql

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'retail.dim_item', N'U') IS NULL
    THROW 50006, 'retail.dim_item does not exist; run 002 first.', 1;
GO

IF COL_LENGTH('retail.dim_item', 'archetype_pattern') IS NULL
    ALTER TABLE retail.dim_item ADD archetype_pattern NVARCHAR(50) NULL;
GO
