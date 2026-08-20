-- 009: add the `vendor` grain to retail.formula.
--
-- The v8.5 Vendor score rule (`A8 Vendors live`, 8 vendors) is the first
-- catalogue rule whose row is a vendor -- its inputs are OTIF, Fill,
-- LeadAdh and Defect, all held per vendor account on retail.dim_vendor.
-- None of the four existing grains describe that: store_sku and chain_sku
-- count SKUs, store_roster counts one store's workforce, and vertical
-- counts a legal entity. Grading it as chain_sku would have recorded a
-- vendor-level rule as per-SKU, which is the silent, permanent mis-grain
-- that import_formulas_to_db.py's docstring exists to prevent.
--
-- Same shape as 007, which added `vertical` for the same reason.
--
-- Rollback: 009_add_formula_vendor_grain_rollback.sql

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'retail.formula', N'U') IS NULL
    THROW 50009, 'retail.formula does not exist; run 002 first.', 1;
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
    CHECK (grain IN (N'store_sku', N'chain_sku', N'store_roster',
                     N'vertical', N'vendor'));
GO
