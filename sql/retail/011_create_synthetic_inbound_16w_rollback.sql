-- Rollback of 011: drop the 16-week synthetic inbound schedule.
--
-- Data-only demo table: nothing in `retail` references it, so dropping it
-- loses no workbook fact. A3's requirement chart falls back to placing each
-- SKU's whole open PO on its lead day -- the flat cover line this table was
-- added to replace (a missing table is a soft failure by design). The
-- `synthetic` schema is dropped only when it is empty, so
-- `demand_store_sku_32w` is not taken out with this one.

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'synthetic.inbound_store_sku_16w', N'U') IS NOT NULL
    DROP TABLE synthetic.inbound_store_sku_16w;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE schema_id = SCHEMA_ID(N'synthetic'))
    DROP SCHEMA synthetic;
GO
