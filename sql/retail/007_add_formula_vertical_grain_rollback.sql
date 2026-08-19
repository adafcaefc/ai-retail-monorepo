-- Undo 007. Restores the original three-value grain check.
--
-- Only safe to run once no `vertical`-grain row remains in retail.formula --
-- delete or re-grain fc01-seasonal-index (and any other vertical-grain rows)
-- first, or this rollback's ADD CONSTRAINT fails on the existing data.

SET XACT_ABORT ON;
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
    CHECK (grain IN (N'store_sku', N'chain_sku', N'store_roster'));
GO
