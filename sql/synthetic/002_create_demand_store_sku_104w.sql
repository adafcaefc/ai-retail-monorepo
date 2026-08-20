/*
  Approved Demand Store SKU 104W synthetic POC table.

  This is a new additive wide table at SKU x Store grain.  It intentionally
  does not alter synthetic.demand_store_sku_32w or any retail source table.
  The loader executes this script only after candidate, source, and existing
  32W preservation checks pass, and only when the 104W target is absent.

  Source-compatible identifiers:
    retail.dim_item.item_id / fact_inventory_daily.item_key: NVARCHAR(30)
    retail.dim_store.store_id / fact_inventory_daily.store_key: NVARCHAR(20)
    retail.dim_item.category_id: NVARCHAR(30)
*/
IF SCHEMA_ID(N'synthetic') IS NULL
    EXEC(N'CREATE SCHEMA synthetic');
GO

IF OBJECT_ID(N'synthetic.demand_store_sku_104w', N'U') IS NULL
BEGIN
    CREATE TABLE synthetic.demand_store_sku_104w
    (
        sku_id       NVARCHAR(30) NOT NULL,
        store_id     NVARCHAR(20) NOT NULL,
        cat          NVARCHAR(30) NOT NULL,

        actual_w52   DECIMAL(20,6) NOT NULL,
        actual_w51   DECIMAL(20,6) NOT NULL,
        actual_w50   DECIMAL(20,6) NOT NULL,
        actual_w49   DECIMAL(20,6) NOT NULL,
        actual_w48   DECIMAL(20,6) NOT NULL,
        actual_w47   DECIMAL(20,6) NOT NULL,
        actual_w46   DECIMAL(20,6) NOT NULL,
        actual_w45   DECIMAL(20,6) NOT NULL,
        actual_w44   DECIMAL(20,6) NOT NULL,
        actual_w43   DECIMAL(20,6) NOT NULL,
        actual_w42   DECIMAL(20,6) NOT NULL,
        actual_w41   DECIMAL(20,6) NOT NULL,
        actual_w40   DECIMAL(20,6) NOT NULL,
        actual_w39   DECIMAL(20,6) NOT NULL,
        actual_w38   DECIMAL(20,6) NOT NULL,
        actual_w37   DECIMAL(20,6) NOT NULL,
        actual_w36   DECIMAL(20,6) NOT NULL,
        actual_w35   DECIMAL(20,6) NOT NULL,
        actual_w34   DECIMAL(20,6) NOT NULL,
        actual_w33   DECIMAL(20,6) NOT NULL,
        actual_w32   DECIMAL(20,6) NOT NULL,
        actual_w31   DECIMAL(20,6) NOT NULL,
        actual_w30   DECIMAL(20,6) NOT NULL,
        actual_w29   DECIMAL(20,6) NOT NULL,
        actual_w28   DECIMAL(20,6) NOT NULL,
        actual_w27   DECIMAL(20,6) NOT NULL,
        actual_w26   DECIMAL(20,6) NOT NULL,
        actual_w25   DECIMAL(20,6) NOT NULL,
        actual_w24   DECIMAL(20,6) NOT NULL,
        actual_w23   DECIMAL(20,6) NOT NULL,
        actual_w22   DECIMAL(20,6) NOT NULL,
        actual_w21   DECIMAL(20,6) NOT NULL,
        actual_w20   DECIMAL(20,6) NOT NULL,
        actual_w19   DECIMAL(20,6) NOT NULL,
        actual_w18   DECIMAL(20,6) NOT NULL,
        actual_w17   DECIMAL(20,6) NOT NULL,
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
        forecast_w17 DECIMAL(20,6) NOT NULL,
        forecast_w18 DECIMAL(20,6) NOT NULL,
        forecast_w19 DECIMAL(20,6) NOT NULL,
        forecast_w20 DECIMAL(20,6) NOT NULL,
        forecast_w21 DECIMAL(20,6) NOT NULL,
        forecast_w22 DECIMAL(20,6) NOT NULL,
        forecast_w23 DECIMAL(20,6) NOT NULL,
        forecast_w24 DECIMAL(20,6) NOT NULL,
        forecast_w25 DECIMAL(20,6) NOT NULL,
        forecast_w26 DECIMAL(20,6) NOT NULL,
        forecast_w27 DECIMAL(20,6) NOT NULL,
        forecast_w28 DECIMAL(20,6) NOT NULL,
        forecast_w29 DECIMAL(20,6) NOT NULL,
        forecast_w30 DECIMAL(20,6) NOT NULL,
        forecast_w31 DECIMAL(20,6) NOT NULL,
        forecast_w32 DECIMAL(20,6) NOT NULL,
        forecast_w33 DECIMAL(20,6) NOT NULL,
        forecast_w34 DECIMAL(20,6) NOT NULL,
        forecast_w35 DECIMAL(20,6) NOT NULL,
        forecast_w36 DECIMAL(20,6) NOT NULL,
        forecast_w37 DECIMAL(20,6) NOT NULL,
        forecast_w38 DECIMAL(20,6) NOT NULL,
        forecast_w39 DECIMAL(20,6) NOT NULL,
        forecast_w40 DECIMAL(20,6) NOT NULL,
        forecast_w41 DECIMAL(20,6) NOT NULL,
        forecast_w42 DECIMAL(20,6) NOT NULL,
        forecast_w43 DECIMAL(20,6) NOT NULL,
        forecast_w44 DECIMAL(20,6) NOT NULL,
        forecast_w45 DECIMAL(20,6) NOT NULL,
        forecast_w46 DECIMAL(20,6) NOT NULL,
        forecast_w47 DECIMAL(20,6) NOT NULL,
        forecast_w48 DECIMAL(20,6) NOT NULL,
        forecast_w49 DECIMAL(20,6) NOT NULL,
        forecast_w50 DECIMAL(20,6) NOT NULL,
        forecast_w51 DECIMAL(20,6) NOT NULL,
        forecast_w52 DECIMAL(20,6) NOT NULL,

        CONSTRAINT PK_synthetic_demand_store_sku_104w
            PRIMARY KEY CLUSTERED (sku_id, store_id),
        CONSTRAINT CK_synthetic_demand_store_sku_104w_nonnegative
            CHECK (
                actual_w52 >= 0 AND actual_w51 >= 0 AND actual_w50 >= 0
                AND actual_w49 >= 0 AND actual_w48 >= 0 AND actual_w47 >= 0
                AND actual_w46 >= 0 AND actual_w45 >= 0 AND actual_w44 >= 0
                AND actual_w43 >= 0 AND actual_w42 >= 0 AND actual_w41 >= 0
                AND actual_w40 >= 0 AND actual_w39 >= 0 AND actual_w38 >= 0
                AND actual_w37 >= 0 AND actual_w36 >= 0 AND actual_w35 >= 0
                AND actual_w34 >= 0 AND actual_w33 >= 0 AND actual_w32 >= 0
                AND actual_w31 >= 0 AND actual_w30 >= 0 AND actual_w29 >= 0
                AND actual_w28 >= 0 AND actual_w27 >= 0 AND actual_w26 >= 0
                AND actual_w25 >= 0 AND actual_w24 >= 0 AND actual_w23 >= 0
                AND actual_w22 >= 0 AND actual_w21 >= 0 AND actual_w20 >= 0
                AND actual_w19 >= 0 AND actual_w18 >= 0 AND actual_w17 >= 0
                AND actual_w16 >= 0 AND actual_w15 >= 0 AND actual_w14 >= 0
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
                AND forecast_w16 >= 0 AND forecast_w17 >= 0 AND forecast_w18 >= 0
                AND forecast_w19 >= 0 AND forecast_w20 >= 0 AND forecast_w21 >= 0
                AND forecast_w22 >= 0 AND forecast_w23 >= 0 AND forecast_w24 >= 0
                AND forecast_w25 >= 0 AND forecast_w26 >= 0 AND forecast_w27 >= 0
                AND forecast_w28 >= 0 AND forecast_w29 >= 0 AND forecast_w30 >= 0
                AND forecast_w31 >= 0 AND forecast_w32 >= 0 AND forecast_w33 >= 0
                AND forecast_w34 >= 0 AND forecast_w35 >= 0 AND forecast_w36 >= 0
                AND forecast_w37 >= 0 AND forecast_w38 >= 0 AND forecast_w39 >= 0
                AND forecast_w40 >= 0 AND forecast_w41 >= 0 AND forecast_w42 >= 0
                AND forecast_w43 >= 0 AND forecast_w44 >= 0 AND forecast_w45 >= 0
                AND forecast_w46 >= 0 AND forecast_w47 >= 0 AND forecast_w48 >= 0
                AND forecast_w49 >= 0 AND forecast_w50 >= 0 AND forecast_w51 >= 0
                AND forecast_w52 >= 0
            )
    );
END;
GO
