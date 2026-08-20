-- Rollback of 010: drop the 32-week synthetic demand table.
--
-- Data-only demo table: nothing in `retail` references it, so dropping it
-- loses no workbook fact. The boards that read it fall back to their
-- snapshot-only presentation (a missing table is a soft failure by design).
-- The `synthetic` schema is dropped only when it is empty, so a future second
-- table is not taken out with this one.

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'synthetic.demand_store_sku_32w', N'U') IS NOT NULL
    DROP TABLE synthetic.demand_store_sku_32w;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE schema_id = SCHEMA_ID(N'synthetic'))
    DROP SCHEMA synthetic;
GO
