/*
  Approved Demand Store SKU 32W synthetic POC table.

  This is intentionally a single wide, additive table at SKU x Store grain.
  The loader executes this script only after read-only source and candidate
  validation, and only when the target table does not already exist.

  Source-compatible identifiers:
    retail.dim_item.item_id / fact_inventory_daily.item_key: NVARCHAR(30)
    retail.dim_store.store_id / fact_inventory_daily.store_key: NVARCHAR(20)
    retail.dim_item.category_id: NVARCHAR(30)
*/
IF SCHEMA_ID(N'synthetic') IS NULL
    EXEC(N'CREATE SCHEMA synthetic');
GO

IF OBJECT_ID(N'synthetic.demand_store_sku_32w', N'U') IS NULL
BEGIN
    CREATE TABLE synthetic.demand_store_sku_32w
    (
        sku_id       NVARCHAR(30) NOT NULL,
        store_id     NVARCHAR(20) NOT NULL,
        cat          NVARCHAR(30) NOT NULL,

        actual_w16   DECIMAL(20,6) NOT NULL,
        actual_w15   DECIMAL(20,6) NOT NULL,
        actual_w14   DECIMAL(20,6) NOT NULL,
        actual_w13   DECIMAL(20,6) NOT NULL,
        actual_w12   DECIMAL(20,6) NOT NULL,
        actual_w11   DECIMAL(20,6) NOT NULL,
        actual_w10   DECIMAL(20,6) NOT NULL,
        actual_w9    DECIMAL(20,6) NOT NULL,
        actual_w8    DECIMAL(20,6) NOT NULL,
        actual_w7    DECIMAL(20,6) NOT NULL,
        actual_w6    DECIMAL(20,6) NOT NULL,
        actual_w5    DECIMAL(20,6) NOT NULL,
        actual_w4    DECIMAL(20,6) NOT NULL,
        actual_w3    DECIMAL(20,6) NOT NULL,
        actual_w2    DECIMAL(20,6) NOT NULL,
        actual_w1    DECIMAL(20,6) NOT NULL,

        forecast_w1  DECIMAL(20,6) NOT NULL,
        forecast_w2  DECIMAL(20,6) NOT NULL,
        forecast_w3  DECIMAL(20,6) NOT NULL,
        forecast_w4  DECIMAL(20,6) NOT NULL,
        forecast_w5  DECIMAL(20,6) NOT NULL,
        forecast_w6  DECIMAL(20,6) NOT NULL,
        forecast_w7  DECIMAL(20,6) NOT NULL,
        forecast_w8  DECIMAL(20,6) NOT NULL,
        forecast_w9  DECIMAL(20,6) NOT NULL,
        forecast_w10 DECIMAL(20,6) NOT NULL,
        forecast_w11 DECIMAL(20,6) NOT NULL,
        forecast_w12 DECIMAL(20,6) NOT NULL,
        forecast_w13 DECIMAL(20,6) NOT NULL,
        forecast_w14 DECIMAL(20,6) NOT NULL,
        forecast_w15 DECIMAL(20,6) NOT NULL,
        forecast_w16 DECIMAL(20,6) NOT NULL,

        CONSTRAINT PK_synthetic_demand_store_sku_32w
            PRIMARY KEY CLUSTERED (sku_id, store_id),
        CONSTRAINT CK_synthetic_demand_store_sku_32w_nonnegative
            CHECK (
                actual_w16 >= 0 AND actual_w15 >= 0 AND actual_w14 >= 0
                AND actual_w13 >= 0 AND actual_w12 >= 0 AND actual_w11 >= 0
                AND actual_w10 >= 0 AND actual_w9 >= 0 AND actual_w8 >= 0
                AND actual_w7 >= 0 AND actual_w6 >= 0 AND actual_w5 >= 0
                AND actual_w4 >= 0 AND actual_w3 >= 0 AND actual_w2 >= 0
                AND actual_w1 >= 0
                AND forecast_w1 >= 0 AND forecast_w2 >= 0 AND forecast_w3 >= 0
                AND forecast_w4 >= 0 AND forecast_w5 >= 0 AND forecast_w6 >= 0
                AND forecast_w7 >= 0 AND forecast_w8 >= 0 AND forecast_w9 >= 0
                AND forecast_w10 >= 0 AND forecast_w11 >= 0 AND forecast_w12 >= 0
                AND forecast_w13 >= 0 AND forecast_w14 >= 0 AND forecast_w15 >= 0
                AND forecast_w16 >= 0
            )
    );
END;
GO
