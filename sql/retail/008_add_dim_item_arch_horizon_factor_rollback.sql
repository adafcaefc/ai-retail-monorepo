-- Undo 008. Discards whatever the re-seed wrote into arch_horizon_factor.
--
-- Readers coalesce a missing factor to 1.0, so dropping the column does not
-- break a query -- it returns Agent 2 and Agent 6 to the pre-008 ADS, which is
-- the workbook's figure divided by the archetype factor. No other table or
-- view references it.

SET XACT_ABORT ON;
GO

IF COL_LENGTH('retail.dim_item', 'arch_horizon_factor') IS NOT NULL
    ALTER TABLE retail.dim_item DROP COLUMN arch_horizon_factor;
GO
