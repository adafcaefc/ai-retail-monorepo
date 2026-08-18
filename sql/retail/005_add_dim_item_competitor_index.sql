-- 005: competitor index, from SKU_Master!comp_idx.
--
-- The workbook's SKU_Master sheet carries a competitive-price index per SKU
-- (comp_idx), read by the Pricing & Markdown fixture builder directly from
-- the extracted workbook JSON -- but no dim_item column has ever carried it,
-- so no live Postgres query could source Agent 5's "Competitive index" KPI.
-- Same shape as 004: the source data already exists in
-- resources/dbtemp/schema_with_data.json, it was just never given a column.
--
-- Nullable with no default, so this is a metadata-only change: existing rows
-- keep NULL until scripts/seed_retail_dims_from_json.py re-runs and fills it.
--
-- Rollback: 005_add_dim_item_competitor_index_rollback.sql

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'retail.dim_item', N'U') IS NULL
    THROW 50005, 'retail.dim_item does not exist; run 002 first.', 1;
GO

IF COL_LENGTH('retail.dim_item', 'competitor_index') IS NULL
    ALTER TABLE retail.dim_item ADD competitor_index DECIMAL(10, 4) NULL;
GO
