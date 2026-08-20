-- Rollback for 009_add_formula_vendor_grain.sql.
--
-- Fails rather than silently dropping rows: any formula already stored at
-- grain `vendor` would violate the restored constraint, so those rows must
-- be re-graded or deleted first, deliberately.

SET XACT_ABORT ON;
GO

IF EXISTS (SELECT 1 FROM retail.formula WHERE grain = N'vendor')
    THROW 50109, 'retail.formula still holds rows at grain vendor; re-grade or delete them before rolling back 009.', 1;
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
