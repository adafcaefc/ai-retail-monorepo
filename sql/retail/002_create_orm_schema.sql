/*
  Azure SQL equivalent of the Postgres `retail.*` (dim/fact/formula) and
  `chat.*` schemas previously created by scripts/create_retail_schema.py,
  scripts/create_chat_schema.py and scripts/migrate_monitoring_runs.py.

  Additive and rerunnable: every statement checks for the object first and
  never drops or truncates anything. Coexists with the pre-existing
  workbook-bootstrap `retail.*` tables (LegalEntity, Store, Sku, ...): no name
  overlap, since those are PascalCase and these are snake_case, matching the
  ORM/raw-SQL code in src/db/db.py, src/actions/repository.py,
  src/formulas/repository.py and the retail agent dashboards/tools.

  Postgres -> T-SQL translations used throughout:
    TEXT              -> NVARCHAR(n) / NVARCHAR(MAX)
    BOOLEAN           -> BIT
    NUMERIC(p,s)      -> DECIMAL(p,s)
    DOUBLE PRECISION  -> FLOAT
    BIGSERIAL         -> BIGINT IDENTITY(1,1)
    TIMESTAMPTZ       -> DATETIME2(3)
    now()/CURRENT_TIMESTAMP -> SYSUTCDATETIME()
    PARTITION BY RANGE(...) -> omitted (not required for correctness)
*/

-- ============================================================== audit ======
IF SCHEMA_ID(N'audit') IS NULL
    EXEC(N'CREATE SCHEMA audit');
GO

IF OBJECT_ID(N'audit.import_batches', N'U') IS NULL
BEGIN
    CREATE TABLE audit.import_batches (
        id               BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_audit_import_batches PRIMARY KEY,
        agent_name       NVARCHAR(100) NOT NULL,
        workbook_name    NVARCHAR(255) NOT NULL,
        workbook_version NVARCHAR(100) NULL,
        workbook_path    NVARCHAR(500) NULL,
        import_status    NVARCHAR(30) NOT NULL CONSTRAINT DF_audit_import_batches_status DEFAULT N'STARTED'
            CONSTRAINT CK_audit_import_batches_status CHECK (import_status IN (N'STARTED', N'COMPLETED', N'FAILED', N'CANCELLED')),
        imported_by      NVARCHAR(255) NULL,
        imported_at      DATETIME2(3) NOT NULL CONSTRAINT DF_audit_import_batches_imported_at DEFAULT SYSUTCDATETIME(),
        completed_at     DATETIME2(3) NULL,
        total_sheets     INT NOT NULL CONSTRAINT DF_audit_import_batches_total_sheets DEFAULT 0,
        total_rows       INT NOT NULL CONSTRAINT DF_audit_import_batches_total_rows DEFAULT 0,
        error_message    NVARCHAR(MAX) NULL,
        [metadata]       NVARCHAR(MAX) NOT NULL CONSTRAINT DF_audit_import_batches_metadata DEFAULT N'{}'
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_import_batches_agent_name' AND object_id = OBJECT_ID(N'audit.import_batches'))
    CREATE INDEX idx_import_batches_agent_name ON audit.import_batches (agent_name);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_import_batches_status' AND object_id = OBJECT_ID(N'audit.import_batches'))
    CREATE INDEX idx_import_batches_status ON audit.import_batches (import_status);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_import_batches_imported_at' AND object_id = OBJECT_ID(N'audit.import_batches'))
    CREATE INDEX idx_import_batches_imported_at ON audit.import_batches (imported_at DESC);
GO

-- ============================================================== retail =====
IF SCHEMA_ID(N'retail') IS NULL
    EXEC(N'CREATE SCHEMA retail');
GO

IF OBJECT_ID(N'retail.dim_vertical', N'U') IS NULL
BEGIN
    CREATE TABLE retail.dim_vertical (
        vertical_id     NVARCHAR(20) NOT NULL CONSTRAINT PK_retail_dim_vertical PRIMARY KEY,
        name            NVARCHAR(200) NOT NULL,
        dashboard_label NVARCHAR(200) NOT NULL,
        sales_per_fte   DECIMAL(18, 4) NULL,
        d365_data_area  NVARCHAR(50) NULL,
        sort_order      INT NULL
    );
END;
GO

IF OBJECT_ID(N'retail.dim_vendor', N'U') IS NULL
BEGIN
    CREATE TABLE retail.dim_vendor (
        vendor_account     NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_dim_vendor PRIMARY KEY,
        vendor_short       NVARCHAR(200) NOT NULL CONSTRAINT UQ_retail_dim_vendor_short UNIQUE,
        vendor_name        NVARCHAR(300) NULL,
        vendor_group       NVARCHAR(100) NULL,
        currency           NVARCHAR(10) NULL,
        payment_terms      NVARCHAR(100) NULL,
        delivery_terms     NVARCHAR(100) NULL,
        lead_time_days     DECIMAL(10, 2) NULL,
        moq_units          DECIMAL(18, 4) NULL,
        otif_pct           DECIMAL(10, 4) NULL,
        fill_pct           DECIMAL(10, 4) NULL,
        defect_pct         DECIMAL(10, 4) NULL,
        lead_adherence_pct DECIMAL(10, 4) NULL
    );
END;
GO

IF OBJECT_ID(N'retail.dim_store', N'U') IS NULL
BEGIN
    CREATE TABLE retail.dim_store (
        store_id            NVARCHAR(20) NOT NULL CONSTRAINT PK_retail_dim_store PRIMARY KEY,
        vertical_id         NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_dim_store_vertical REFERENCES retail.dim_vertical (vertical_id),
        name                NVARCHAR(240) NOT NULL,
        cluster             NVARCHAR(80) NULL,
        channel             NVARCHAR(80) NULL,
        size_index          DECIMAL(10, 4) NULL,
        health_index        DECIMAL(10, 4) NULL,
        footfall_index      DECIMAL(10, 4) NULL,
        invent_location_id  NVARCHAR(50) NULL,
        opened_at           DATE NULL,
        closed_at           DATE NULL
    );
END;
GO

IF OBJECT_ID(N'retail.dim_item', N'U') IS NULL
BEGIN
    CREATE TABLE retail.dim_item (
        item_id             NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_dim_item PRIMARY KEY,
        vertical_id         NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_dim_item_vertical REFERENCES retail.dim_vertical (vertical_id),
        category_id         NVARCHAR(30) NULL,
        category_name       NVARCHAR(200) NULL,
        name                NVARCHAR(300) NOT NULL,
        brand               NVARCHAR(200) NULL,
        vendor_account      NVARCHAR(30) NULL CONSTRAINT FK_retail_dim_item_vendor REFERENCES retail.dim_vendor (vendor_account),
        is_perishable       BIT NOT NULL CONSTRAINT DF_retail_dim_item_is_perishable DEFAULT 0,
        shelf_life_days     INT NULL,
        sales_uom           NVARCHAR(20) NULL,
        buy_uom             NVARCHAR(20) NULL,
        pack_factor         DECIMAL(18, 4) NULL,
        lead_time_days      DECIMAL(10, 2) NULL,
        safety_days         DECIMAL(10, 2) NULL,
        base_ads            FLOAT NULL,
        price               DECIMAL(18, 4) NULL,
        unit_cost           DECIMAL(18, 4) NULL,
        margin_pct          DECIMAL(10, 4) NULL,
        seasonality_index   DECIMAL(10, 4) NULL,
        lifecycle           NVARCHAR(50) NULL,
        growth_index        DECIMAL(10, 4) NULL,
        is_promo_eligible   BIT NOT NULL CONSTRAINT DF_retail_dim_item_is_promo_eligible DEFAULT 0,
        cannibalisation_pct DECIMAL(10, 4) NULL,
        elasticity          DECIMAL(10, 4) NULL,
        is_viral            BIT NOT NULL CONSTRAINT DF_retail_dim_item_is_viral DEFAULT 0,
        funding_pct         DECIMAL(10, 4) NULL,
        onhand_days         FLOAT NULL,
        stock_factor        FLOAT NULL
    );
END;
GO

IF OBJECT_ID(N'retail.dim_calendar', N'U') IS NULL
BEGIN
    CREATE TABLE retail.dim_calendar (
        cal_date         DATE NOT NULL CONSTRAINT PK_retail_dim_calendar PRIMARY KEY,
        dow              SMALLINT NOT NULL,
        iso_week         SMALLINT NOT NULL,
        [month]          SMALLINT NOT NULL,
        [year]           SMALLINT NOT NULL,
        is_weekend       BIT NOT NULL,
        is_payday_window BIT NOT NULL,
        is_ramadan_est   BIT NOT NULL CONSTRAINT DF_retail_dim_calendar_ramadan DEFAULT 0,
        is_idulfitri_est BIT NOT NULL CONSTRAINT DF_retail_dim_calendar_idulfitri DEFAULT 0
    );
END;
GO

IF OBJECT_ID(N'retail.assortment', N'U') IS NULL
BEGIN
    CREATE TABLE retail.assortment (
        item_key   NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_assortment_item REFERENCES retail.dim_item (item_id),
        store_key  NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_assortment_store REFERENCES retail.dim_store (store_id),
        valid_from DATE NOT NULL,
        valid_to   DATE NULL,
        CONSTRAINT PK_retail_assortment PRIMARY KEY (item_key, store_key, valid_from)
    );
END;
GO

IF OBJECT_ID(N'retail.fact_sales_daily', N'U') IS NULL
BEGIN
    CREATE TABLE retail.fact_sales_daily (
        item_key        NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_fact_sales_daily_item REFERENCES retail.dim_item (item_id),
        store_key       NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_fact_sales_daily_store REFERENCES retail.dim_store (store_id),
        cal_date        DATE NOT NULL,
        qty_sold        DECIMAL(18, 4) NOT NULL CONSTRAINT DF_retail_fact_sales_daily_qty DEFAULT 0,
        revenue         DECIMAL(20, 4) NOT NULL CONSTRAINT DF_retail_fact_sales_daily_rev DEFAULT 0,
        is_stockout     BIT NOT NULL CONSTRAINT DF_retail_fact_sales_daily_stockout DEFAULT 0,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_fact_sales_daily_batch REFERENCES audit.import_batches (id),
        CONSTRAINT PK_retail_fact_sales_daily PRIMARY KEY (item_key, store_key, cal_date)
    );
END;
GO

IF OBJECT_ID(N'retail.fact_inventory_daily', N'U') IS NULL
BEGIN
    CREATE TABLE retail.fact_inventory_daily (
        item_key        NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_fact_inventory_daily_item REFERENCES retail.dim_item (item_id),
        store_key       NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_fact_inventory_daily_store REFERENCES retail.dim_store (store_id),
        cal_date        DATE NOT NULL,
        on_hand_qty     FLOAT NOT NULL CONSTRAINT DF_retail_fact_inventory_daily_onhand DEFAULT 0,
        open_po_qty     FLOAT NOT NULL CONSTRAINT DF_retail_fact_inventory_daily_openpo DEFAULT 0,
        position_qty    FLOAT NOT NULL CONSTRAINT DF_retail_fact_inventory_daily_position DEFAULT 0,
        rop_qty         DECIMAL(18, 4) NULL,
        max_qty         DECIMAL(18, 4) NULL,
        days_cover      FLOAT NULL,
        state           NVARCHAR(30) NULL,
        is_stockout     BIT NOT NULL CONSTRAINT DF_retail_fact_inventory_daily_stockout DEFAULT 0,
        ads             FLOAT NULL,
        forecast_7d     FLOAT NULL,
        order_qty_sales FLOAT NULL,
        order_qty_buy   FLOAT NULL,
        order_value     DECIMAL(20, 4) NULL,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_fact_inventory_daily_batch REFERENCES audit.import_batches (id),
        CONSTRAINT PK_retail_fact_inventory_daily PRIMARY KEY (item_key, store_key, cal_date)
    );
END;
GO

IF OBJECT_ID(N'retail.fact_price_daily', N'U') IS NULL
BEGIN
    CREATE TABLE retail.fact_price_daily (
        item_key        NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_fact_price_daily_item REFERENCES retail.dim_item (item_id),
        store_key       NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_fact_price_daily_store REFERENCES retail.dim_store (store_id),
        cal_date        DATE NOT NULL,
        unit_price      DECIMAL(18, 4) NOT NULL,
        unit_cost       DECIMAL(18, 4) NULL,
        is_promo        BIT NOT NULL CONSTRAINT DF_retail_fact_price_daily_promo DEFAULT 0,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_fact_price_daily_batch REFERENCES audit.import_batches (id),
        CONSTRAINT PK_retail_fact_price_daily PRIMARY KEY (item_key, store_key, cal_date)
    );
END;
GO

IF OBJECT_ID(N'retail.fact_promotion', N'U') IS NULL
BEGIN
    CREATE TABLE retail.fact_promotion (
        promo_id        NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_fact_promotion PRIMARY KEY,
        item_key        NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_fact_promotion_item REFERENCES retail.dim_item (item_id),
        store_key       NVARCHAR(20) NULL CONSTRAINT FK_retail_fact_promotion_store REFERENCES retail.dim_store (store_id),
        start_date      DATE NOT NULL,
        end_date        DATE NOT NULL,
        discount_pct    DECIMAL(10, 4) NULL,
        mechanic        NVARCHAR(100) NULL,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_fact_promotion_batch REFERENCES audit.import_batches (id),
        CONSTRAINT CK_retail_fact_promotion_dates CHECK (end_date >= start_date)
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ux_promo_line' AND object_id = OBJECT_ID(N'retail.fact_promotion'))
    CREATE UNIQUE INDEX ux_promo_line ON retail.fact_promotion (item_key, store_key, start_date);
GO

IF OBJECT_ID(N'retail.fact_purchase_receipt', N'U') IS NULL
BEGIN
    CREATE TABLE retail.fact_purchase_receipt (
        receipt_id      NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_fact_purchase_receipt PRIMARY KEY,
        item_key        NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_fact_purchase_receipt_item REFERENCES retail.dim_item (item_id),
        store_key       NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_fact_purchase_receipt_store REFERENCES retail.dim_store (store_id),
        vendor_account  NVARCHAR(30) NULL CONSTRAINT FK_retail_fact_purchase_receipt_vendor REFERENCES retail.dim_vendor (vendor_account),
        ordered_date    DATE NULL,
        received_date   DATE NULL,
        ordered_qty     DECIMAL(18, 4) NULL,
        received_qty    DECIMAL(18, 4) NULL,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_fact_purchase_receipt_batch REFERENCES audit.import_batches (id)
    );
END;
GO

IF OBJECT_ID(N'retail.fact_inventory_chain_daily', N'U') IS NULL
BEGIN
    CREATE TABLE retail.fact_inventory_chain_daily (
        item_key        NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_fact_inv_chain_item REFERENCES retail.dim_item (item_id),
        cal_date        DATE NOT NULL CONSTRAINT FK_retail_fact_inv_chain_cal REFERENCES retail.dim_calendar (cal_date),
        ads             FLOAT NULL,
        on_hand_qty     DECIMAL(18, 4) NOT NULL CONSTRAINT DF_retail_fact_inv_chain_onhand DEFAULT 0,
        open_po_qty     DECIMAL(18, 4) NOT NULL CONSTRAINT DF_retail_fact_inv_chain_openpo DEFAULT 0,
        position_qty    DECIMAL(18, 4) NOT NULL CONSTRAINT DF_retail_fact_inv_chain_position DEFAULT 0,
        rop_qty         DECIMAL(18, 4) NULL,
        max_qty         DECIMAL(18, 4) NULL,
        days_cover      FLOAT NULL,
        state           NVARCHAR(30) NULL,
        unit_price      DECIMAL(18, 4) NULL,
        inventory_value DECIMAL(20, 4) NULL,
        at_risk_value   DECIMAL(20, 4) NULL,
        expiry_units    FLOAT NULL,
        order_units     DECIMAL(18, 4) NULL,
        order_value     DECIMAL(20, 4) NULL,
        weekly_gmv      DECIMAL(20, 4) NULL,
        margin_rp       DECIMAL(20, 4) NULL,
        funding_rp      DECIMAL(20, 4) NULL,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_fact_inv_chain_batch REFERENCES audit.import_batches (id),
        CONSTRAINT PK_retail_fact_inv_chain PRIMARY KEY (item_key, cal_date)
    );
END;
GO

IF OBJECT_ID(N'retail.fact_gmv_monthly', N'U') IS NULL
BEGIN
    CREATE TABLE retail.fact_gmv_monthly (
        vertical_id     NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_fact_gmv_monthly_vertical REFERENCES retail.dim_vertical (vertical_id),
        year_index      SMALLINT NOT NULL,
        month_index     SMALLINT NOT NULL,
        gmv             DECIMAL(22, 4) NOT NULL,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_fact_gmv_monthly_batch REFERENCES audit.import_batches (id),
        CONSTRAINT PK_retail_fact_gmv_monthly PRIMARY KEY (vertical_id, year_index, month_index)
    );
END;
GO

IF OBJECT_ID(N'retail.agent_kpi_reference', N'U') IS NULL
BEGIN
    CREATE TABLE retail.agent_kpi_reference (
        agent_id        NVARCHAR(50) NOT NULL,
        vertical_id     NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_agent_kpi_reference_vertical REFERENCES retail.dim_vertical (vertical_id),
        metric          NVARCHAR(100) NOT NULL,
        [value]         FLOAT NULL,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_agent_kpi_reference_batch REFERENCES audit.import_batches (id),
        CONSTRAINT PK_retail_agent_kpi_reference PRIMARY KEY (agent_id, vertical_id, metric)
    );
END;
GO

IF OBJECT_ID(N'retail.trade_agreement', N'U') IS NULL
BEGIN
    CREATE TABLE retail.trade_agreement (
        item_key        NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_trade_agreement_item REFERENCES retail.dim_item (item_id),
        vendor_account  NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_trade_agreement_vendor REFERENCES retail.dim_vendor (vendor_account),
        unit_price      DECIMAL(18, 4) NOT NULL,
        currency        NVARCHAR(10) NOT NULL CONSTRAINT DF_retail_trade_agreement_ccy DEFAULT N'IDR',
        min_qty_break   DECIMAL(18, 4) NULL,
        lead_time_days  INT NULL,
        discount_pct    DECIMAL(9, 6) NULL,
        valid_from      DATE NOT NULL,
        valid_to        DATE NULL,
        is_designated   BIT NOT NULL CONSTRAINT DF_retail_trade_agreement_designated DEFAULT 0,
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_trade_agreement_batch REFERENCES audit.import_batches (id),
        CONSTRAINT PK_retail_trade_agreement PRIMARY KEY (item_key, vendor_account, valid_from)
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_trade_agreement_vendor' AND object_id = OBJECT_ID(N'retail.trade_agreement'))
    CREATE INDEX ix_trade_agreement_vendor ON retail.trade_agreement (vendor_account);
GO

IF OBJECT_ID(N'retail.replenishment_proposal', N'U') IS NULL
BEGIN
    CREATE TABLE retail.replenishment_proposal (
        item_key             NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_replen_proposal_item REFERENCES retail.dim_item (item_id),
        as_of_date           DATE NOT NULL,
        qty_on_hand          DECIMAL(18, 4) NOT NULL CONSTRAINT DF_retail_replen_proposal_onhand DEFAULT 0,
        open_po_qty          DECIMAL(18, 4) NOT NULL CONSTRAINT DF_retail_replen_proposal_openpo DEFAULT 0,
        demand_per_day       DECIMAL(18, 4) NULL,
        rop_qty              DECIMAL(18, 4) NULL,
        max_qty              DECIMAL(18, 4) NULL,
        is_reorder           BIT NOT NULL CONSTRAINT DF_retail_replen_proposal_reorder DEFAULT 0,
        order_qty_sales      DECIMAL(18, 4) NOT NULL CONSTRAINT DF_retail_replen_proposal_ord_sales DEFAULT 0,
        order_qty_buy        DECIMAL(18, 4) NOT NULL CONSTRAINT DF_retail_replen_proposal_ord_buy DEFAULT 0,
        buy_uom              NVARCHAR(20) NULL,
        designated_vendor    NVARCHAR(30) NULL CONSTRAINT FK_retail_replen_proposal_desig_vendor REFERENCES retail.dim_vendor (vendor_account),
        unit_price_ta        DECIMAL(18, 4) NULL,
        amount               DECIMAL(18, 4) NULL,
        best_price_vendor    NVARCHAR(30) NULL CONSTRAINT FK_retail_replen_proposal_best_vendor REFERENCES retail.dim_vendor (vendor_account),
        best_price           DECIMAL(18, 4) NULL,
        saving_vs_designated DECIMAL(18, 4) NULL,
        import_batch_id      BIGINT NULL CONSTRAINT FK_retail_replen_proposal_batch REFERENCES audit.import_batches (id),
        CONSTRAINT PK_retail_replenishment_proposal PRIMARY KEY (item_key, as_of_date)
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_replenishment_proposal_reorder' AND object_id = OBJECT_ID(N'retail.replenishment_proposal'))
    CREATE INDEX ix_replenishment_proposal_reorder ON retail.replenishment_proposal (as_of_date, is_reorder);
GO

IF OBJECT_ID(N'retail.promotion_detail', N'U') IS NULL
BEGIN
    CREATE TABLE retail.promotion_detail (
        promo_id             NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_promotion_detail PRIMARY KEY,
        promo_name           NVARCHAR(200) NOT NULL,
        discount_type        NVARCHAR(50) NOT NULL,
        scope                NVARCHAR(50) NOT NULL,
        vertical_label       NVARCHAR(200) NOT NULL,
        target_category      NVARCHAR(200) NOT NULL,
        season               NVARCHAR(50) NOT NULL,
        peak_month           NVARCHAR(30) NOT NULL,
        mechanism            NVARCHAR(100) NOT NULL,
        discount_pct         INT NULL,
        value_rule           NVARCHAR(200) NOT NULL,
        min_qty_threshold    NVARCHAR(100) NOT NULL,
        supplier_funding_pct INT NOT NULL,
        expected_uplift_pct  INT NOT NULL,
        pre_buy_uplift_units INT NOT NULL,
        valid_from           DATE NOT NULL,
        valid_to             DATE NOT NULL,
        d365_construct       NVARCHAR(100) NOT NULL,
        source_row           INT NOT NULL,
        CONSTRAINT CK_retail_promotion_detail_dates CHECK (valid_to >= valid_from)
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_promotion_detail_vertical' AND object_id = OBJECT_ID(N'retail.promotion_detail'))
    CREATE INDEX ix_promotion_detail_vertical ON retail.promotion_detail (vertical_label);
GO

IF OBJECT_ID(N'retail.promotion_vertical_kpi', N'U') IS NULL
BEGIN
    CREATE TABLE retail.promotion_vertical_kpi (
        vertical_label     NVARCHAR(200) NOT NULL CONSTRAINT PK_retail_promotion_vertical_kpi PRIMARY KEY,
        active_promo_skus  INT NOT NULL,
        uplift_pct         DECIMAL(10, 4) NOT NULL,
        incremental_margin DECIMAL(20, 4) NOT NULL,
        roi_x              DECIMAL(10, 4) NOT NULL,
        cannib_pct         DECIMAL(10, 4) NOT NULL,
        funding_pct        DECIMAL(10, 4) NOT NULL
    );
END;
GO

IF OBJECT_ID(N'retail.forecast_run', N'U') IS NULL
BEGIN
    CREATE TABLE retail.forecast_run (
        run_id          BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_retail_forecast_run PRIMARY KEY,
        model_version   NVARCHAR(50) NOT NULL,
        as_of_date      DATE NOT NULL,
        horizon_days    SMALLINT NOT NULL,
        created_at      DATETIME2(3) NOT NULL CONSTRAINT DF_retail_forecast_run_created DEFAULT SYSUTCDATETIME(),
        import_batch_id BIGINT NULL CONSTRAINT FK_retail_forecast_run_batch REFERENCES audit.import_batches (id),
        CONSTRAINT UQ_retail_forecast_run UNIQUE (model_version, as_of_date, horizon_days)
    );
END;
GO

IF OBJECT_ID(N'retail.forecast_daily', N'U') IS NULL
BEGIN
    CREATE TABLE retail.forecast_daily (
        run_id      BIGINT NOT NULL CONSTRAINT FK_retail_forecast_daily_run REFERENCES retail.forecast_run (run_id) ON DELETE CASCADE,
        item_key    NVARCHAR(30) NOT NULL CONSTRAINT FK_retail_forecast_daily_item REFERENCES retail.dim_item (item_id),
        store_key   NVARCHAR(20) NOT NULL CONSTRAINT FK_retail_forecast_daily_store REFERENCES retail.dim_store (store_id),
        target_date DATE NOT NULL,
        yhat        DECIMAL(18, 4) NOT NULL,
        yhat_lo     DECIMAL(18, 4) NULL,
        yhat_hi     DECIMAL(18, 4) NULL,
        CONSTRAINT PK_retail_forecast_daily PRIMARY KEY (run_id, item_key, store_key, target_date)
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_forecast_target' AND object_id = OBJECT_ID(N'retail.forecast_daily'))
    CREATE INDEX ix_forecast_target ON retail.forecast_daily (target_date);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_forecast_item_store_target' AND object_id = OBJECT_ID(N'retail.forecast_daily'))
    CREATE INDEX ix_forecast_item_store_target ON retail.forecast_daily (item_key, store_key, target_date);
GO

IF OBJECT_ID(N'retail.forecast_accuracy', N'U') IS NULL
BEGIN
    CREATE TABLE retail.forecast_accuracy (
        run_id        BIGINT NOT NULL CONSTRAINT FK_retail_forecast_accuracy_run REFERENCES retail.forecast_run (run_id) ON DELETE CASCADE,
        horizon       SMALLINT NOT NULL,
        model_version NVARCHAR(50) NOT NULL,
        wape          DECIMAL(10, 4) NULL,
        bias          DECIMAL(10, 4) NULL,
        mape          DECIMAL(10, 4) NULL,
        n_obs         INT NOT NULL CONSTRAINT DF_retail_forecast_accuracy_nobs DEFAULT 0,
        computed_at   DATETIME2(3) NOT NULL CONSTRAINT DF_retail_forecast_accuracy_computed DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_retail_forecast_accuracy PRIMARY KEY (run_id, horizon)
    );
END;
GO

IF OBJECT_ID(N'retail.formula', N'U') IS NULL
BEGIN
    CREATE TABLE retail.formula (
        id          NVARCHAR(50) NOT NULL CONSTRAINT PK_retail_formula PRIMARY KEY,
        number      INT NOT NULL,
        name        NVARCHAR(200) NOT NULL,
        logic       NVARCHAR(MAX) NULL,
        grain       NVARCHAR(20) NOT NULL
            CONSTRAINT CK_retail_formula_grain CHECK (grain IN (N'store_sku', N'chain_sku', N'store_roster')),
        sheet       NVARCHAR(100) NULL,
        result_type NVARCHAR(30) NOT NULL CONSTRAINT DF_retail_formula_result_type DEFAULT N'number',
        expression  NVARCHAR(MAX) NOT NULL,
        parameters  NVARCHAR(MAX) NOT NULL CONSTRAINT DF_retail_formula_parameters DEFAULT N'[]',
        updated_at  DATETIME2(3) NOT NULL CONSTRAINT DF_retail_formula_updated_at DEFAULT SYSUTCDATETIME()
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_retail_formula_number' AND object_id = OBJECT_ID(N'retail.formula'))
    CREATE UNIQUE INDEX idx_retail_formula_number ON retail.formula (number);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_sales_date' AND object_id = OBJECT_ID(N'retail.fact_sales_daily'))
    CREATE INDEX ix_sales_date ON retail.fact_sales_daily (cal_date);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_sales_item_date' AND object_id = OBJECT_ID(N'retail.fact_sales_daily'))
    CREATE INDEX ix_sales_item_date ON retail.fact_sales_daily (item_key, cal_date);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_inventory_date' AND object_id = OBJECT_ID(N'retail.fact_inventory_daily'))
    CREATE INDEX ix_inventory_date ON retail.fact_inventory_daily (cal_date);
GO

-- ================================================================ chat =====
IF SCHEMA_ID(N'chat') IS NULL
    EXEC(N'CREATE SCHEMA chat');
GO

IF OBJECT_ID(N'chat.conversations', N'U') IS NULL
BEGIN
    CREATE TABLE chat.conversations (
        id         UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_chat_conversations PRIMARY KEY,
        title      NVARCHAR(400) NOT NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_chat_conversations_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_chat_conversations_updated DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID(N'chat.messages', N'U') IS NULL
BEGIN
    CREATE TABLE chat.messages (
        id              UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_chat_messages PRIMARY KEY,
        conversation_id UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT FK_chat_messages_conversation REFERENCES chat.conversations (id) ON DELETE CASCADE,
        sender          NVARCHAR(20) NOT NULL,
        channel         NVARCHAR(100) NOT NULL,
        message         NVARCHAR(MAX) NOT NULL,
        created_at      DATETIME2(3) NOT NULL CONSTRAINT DF_chat_messages_created DEFAULT SYSUTCDATETIME()
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_chat_messages_conversation' AND object_id = OBJECT_ID(N'chat.messages'))
    CREATE INDEX idx_chat_messages_conversation ON chat.messages (conversation_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_chat_messages_created_at' AND object_id = OBJECT_ID(N'chat.messages'))
    CREATE INDEX idx_chat_messages_created_at ON chat.messages (created_at);
GO

IF OBJECT_ID(N'chat.monitoring_runs', N'U') IS NULL
BEGIN
    CREATE TABLE chat.monitoring_runs (
        id                BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_chat_monitoring_runs PRIMARY KEY,
        agent             NVARCHAR(60) NOT NULL,
        run_status        NVARCHAR(30) NOT NULL CONSTRAINT DF_chat_monitoring_runs_status DEFAULT N'STARTED',
        started_at        DATETIME2(3) NOT NULL CONSTRAINT DF_chat_monitoring_runs_started DEFAULT SYSUTCDATETIME(),
        completed_at      DATETIME2(3) NULL,
        monitoring_passes INT NOT NULL CONSTRAINT DF_chat_monitoring_runs_passes DEFAULT 0,
        alerts_created    INT NOT NULL CONSTRAINT DF_chat_monitoring_runs_alerts_created DEFAULT 0,
        actions_created   INT NOT NULL CONSTRAINT DF_chat_monitoring_runs_actions_created DEFAULT 0,
        error_message     NVARCHAR(MAX) NULL
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_chat_monitoring_runs_agent' AND object_id = OBJECT_ID(N'chat.monitoring_runs'))
    CREATE INDEX idx_chat_monitoring_runs_agent ON chat.monitoring_runs (agent, started_at DESC);
GO

IF OBJECT_ID(N'chat.alerts', N'U') IS NULL
BEGIN
    CREATE TABLE chat.alerts (
        id           UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_chat_alerts PRIMARY KEY,
        name         NVARCHAR(300) NULL,
        subagent     NVARCHAR(100) NULL,
        agent        NVARCHAR(100) NULL,
        issue        NVARCHAR(MAX) NULL,
        date_created DATETIME2(3) NULL,
        run_id       BIGINT NULL CONSTRAINT FK_chat_alerts_run REFERENCES chat.monitoring_runs (id) ON DELETE SET NULL
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_chat_alerts_agent' AND object_id = OBJECT_ID(N'chat.alerts'))
    CREATE INDEX idx_chat_alerts_agent ON chat.alerts (agent);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_chat_alerts_agent_date_created' AND object_id = OBJECT_ID(N'chat.alerts'))
    CREATE INDEX idx_chat_alerts_agent_date_created ON chat.alerts (agent, date_created DESC);
GO

IF OBJECT_ID(N'chat.actions', N'U') IS NULL
BEGIN
    CREATE TABLE chat.actions (
        id                 UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_chat_actions PRIMARY KEY,
        action             NVARCHAR(400) NOT NULL,
        agent              NVARCHAR(100) NOT NULL,
        -- Postgres text[] has no T-SQL analog; routes is an NVARCHAR(MAX)
        -- JSON array string, encoded/decoded in src/actions/repository.py.
        routes             NVARCHAR(MAX) NOT NULL,
        alert_id           UNIQUEIDENTIFIER NULL CONSTRAINT FK_chat_actions_alert REFERENCES chat.alerts (id) ON DELETE CASCADE,
        status             NVARCHAR(30) NULL CONSTRAINT DF_chat_actions_status DEFAULT N'planned',
        created_at         DATETIME2(3) NULL,
        spec               NVARCHAR(MAX) NULL,
        impact             NVARCHAR(MAX) NULL,
        simulation_summary NVARCHAR(MAX) NULL,
        reason             NVARCHAR(MAX) NULL,
        run_id             BIGINT NULL CONSTRAINT FK_chat_actions_run REFERENCES chat.monitoring_runs (id) ON DELETE SET NULL
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_chat_actions_alert_id' AND object_id = OBJECT_ID(N'chat.actions'))
    CREATE INDEX idx_chat_actions_alert_id ON chat.actions (alert_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_chat_actions_status' AND object_id = OBJECT_ID(N'chat.actions'))
    CREATE INDEX idx_chat_actions_status ON chat.actions (status);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_chat_actions_agent_created_at' AND object_id = OBJECT_ID(N'chat.actions'))
    CREATE INDEX idx_chat_actions_agent_created_at ON chat.actions (agent, created_at DESC);
GO
