-- Rollback of 012: drop the 16-week synthetic markdown ladder projection.
--
-- Data-only demo table: nothing in `retail` references it, so dropping it
-- loses no workbook fact. A5's ladder-vs-no-action chart falls back to not
-- rendering (the fixture/dashboard.py guard the same way A3's requirement
-- chart guards `synthetic.inbound_store_sku_16w` -- a missing table is a
-- soft failure by design). The `synthetic` schema is dropped only when it is
-- empty, so `demand_store_sku_32w`/`inbound_store_sku_16w` are not taken out
-- with this one.

SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'synthetic.markdown_ladder_store_sku_16w', N'U') IS NOT NULL
    DROP TABLE synthetic.markdown_ladder_store_sku_16w;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE schema_id = SCHEMA_ID(N'synthetic'))
    DROP SCHEMA synthetic;
GO
