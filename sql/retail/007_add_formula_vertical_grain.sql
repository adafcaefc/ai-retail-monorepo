-- 007: add the `vertical` grain to retail.formula.
--
-- `fc01-seasonal-index` (resources/custom_formulas.json) is the first
-- catalogue rule with no per-store or per-SKU row at all -- its one input is
-- a vertical's own monthly GMV figure. None of the three existing grains
-- (store_sku, chain_sku, store_roster) describe that, and CK_retail_formula_grain
-- rejects anything else outright. The v8.5 per-vertical formulas this session
-- also plans (Accuracy %, Fill rate, Service level) need the same grain --
-- see docs/v8.5-new-agent-formulas.md's open design question -- so it is
-- added once here rather than per formula.
--
-- Rollback: 007_add_formula_vertical_grain_rollback.sql

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'retail.formula', N'U') IS NULL
    THROW 50007, 'retail.formula does not exist; run 002 first.', 1;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_retail_formula_grain'
      AND parent_object_id = OBJECT_ID(N'retail.formula')
)
    ALTER TABLE retail.formula DROP CONSTRAINT CK_retail_formula_grain;
GO

ALTER TABLE retail.formula
    ADD CONSTRAINT CK_retail_formula_grain
    CHECK (grain IN (N'store_sku', N'chain_sku', N'store_roster', N'vertical'));
GO
