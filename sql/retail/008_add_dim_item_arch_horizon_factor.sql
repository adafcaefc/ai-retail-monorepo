-- 008: archetype/horizon factor, from ENGINE_STORE!archhz (v8.5).
--
-- `f01-ads-per-store` multiplies by an archetype/horizon factor. dim_item
-- carries the archetype LABEL (006, `archetype_pattern`) but never the
-- multiplier the formula actually reads, so every live query had to fall back
-- to 1.0 -- which silently returns a different ADS than the workbook, and with
-- it a different DoS, state and expiry figure on Agent 2's KPI cards.
--
-- It is not a SKU_Master column: the workbook precomputes it onto ENGINE_STORE
-- as `archhz`, constant across all 20 stores for a given SKU (verified over all
-- 800 SKUs). So it is a per-SKU attribute stored at store grain, and dim_item
-- is its right home -- the same argument 006 made for the label beside it.
--
-- Nullable with no default, so this is a metadata-only change: existing rows
-- keep NULL until scripts/seed_retail_dims_from_json.py re-runs and fills it.
-- Readers coalesce to 1.0, which is the identity for f01's multiplier and
-- reproduces the pre-008 behaviour exactly on an unseeded column.
--
-- Rollback: 008_add_dim_item_arch_horizon_factor_rollback.sql

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'retail.dim_item', N'U') IS NULL
    THROW 50008, 'retail.dim_item does not exist; run 002 first.', 1;
GO

IF COL_LENGTH('retail.dim_item', 'arch_horizon_factor') IS NULL
    ALTER TABLE retail.dim_item ADD arch_horizon_factor DECIMAL(10, 4) NULL;
GO
