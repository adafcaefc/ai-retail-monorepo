-- Undo 005. Discards whatever the re-seed wrote into competitor_index.
-- Nothing else reads the column, so no other table or view breaks.

SET XACT_ABORT ON;
GO

IF COL_LENGTH('retail.dim_item', 'competitor_index') IS NOT NULL
    ALTER TABLE retail.dim_item DROP COLUMN competitor_index;
GO
