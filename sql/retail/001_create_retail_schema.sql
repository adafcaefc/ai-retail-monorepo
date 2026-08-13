/*
  AI Retail 360 pre-embedding relational foundation for Azure SQL.

  This migration is additive and rerunnable: it creates only missing objects,
  never drops or truncates objects, and never creates an ai/vector table.
  The Python migration runner performs a catalog conflict check first.
*/
IF SCHEMA_ID(N'retail') IS NULL
    EXEC(N'CREATE SCHEMA retail');
GO

IF OBJECT_ID(N'retail.SourceLoad', N'U') IS NULL
BEGIN
    CREATE TABLE retail.SourceLoad (
        source_load_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_retail_SourceLoad PRIMARY KEY,
        workbook_name NVARCHAR(260) NOT NULL,
        workbook_sha256 CHAR(64) NOT NULL,
        source_type NVARCHAR(30) NOT NULL CONSTRAINT DF_retail_SourceLoad_source_type DEFAULT N'EXCEL',
        load_status NVARCHAR(20) NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_SourceLoad_loaded_at DEFAULT SYSUTCDATETIME(),
        completed_at DATETIME2(3) NULL,
        row_count INT NULL,
        CONSTRAINT UQ_retail_SourceLoad_hash UNIQUE (workbook_sha256),
        CONSTRAINT CK_retail_SourceLoad_status CHECK (load_status IN (N'STARTED', N'COMPLETED', N'FAILED'))
    );
END;
GO

IF OBJECT_ID(N'retail.LegalEntity', N'U') IS NULL
BEGIN
    CREATE TABLE retail.LegalEntity (
        legal_entity_id NVARCHAR(10) NOT NULL CONSTRAINT PK_retail_LegalEntity PRIMARY KEY,
        legal_entity_name NVARCHAR(200) NOT NULL,
        short_name NVARCHAR(100) NOT NULL,
        workforce_base_per_size DECIMAL(18,6) NULL,
        sales_per_fte DECIMAL(28,4) NULL,
        peak_season_factor DECIMAL(18,6) NULL,
        total_store_size DECIMAL(18,6) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_LegalEntity_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_LegalEntity_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id),
        CONSTRAINT UQ_retail_LegalEntity_name UNIQUE (legal_entity_name)
    );
END;
GO

IF OBJECT_ID(N'retail.Store', N'U') IS NULL
BEGIN
    CREATE TABLE retail.Store (
        store_id NVARCHAR(20) NOT NULL CONSTRAINT PK_retail_Store PRIMARY KEY,
        legal_entity_id NVARCHAR(10) NOT NULL,
        store_name NVARCHAR(240) NOT NULL,
        cluster NVARCHAR(80) NULL,
        size_factor DECIMAL(18,6) NULL,
        health_factor DECIMAL(18,6) NULL,
        footfall_index DECIMAL(18,6) NULL,
        channel NVARCHAR(80) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_Store_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_Store_entity FOREIGN KEY (legal_entity_id) REFERENCES retail.LegalEntity(legal_entity_id),
        CONSTRAINT FK_retail_Store_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
    CREATE INDEX IX_retail_Store_entity ON retail.Store(legal_entity_id);
    CREATE INDEX IX_retail_Store_channel ON retail.Store(channel);
END;
GO

IF OBJECT_ID(N'retail.Category', N'U') IS NULL
BEGIN
    CREATE TABLE retail.Category (
        category_id NVARCHAR(20) NOT NULL CONSTRAINT PK_retail_Category PRIMARY KEY,
        legal_entity_id NVARCHAR(10) NOT NULL,
        category_name NVARCHAR(200) NOT NULL,
        is_perishable BIT NOT NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_Category_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_Category_entity FOREIGN KEY (legal_entity_id) REFERENCES retail.LegalEntity(legal_entity_id),
        CONSTRAINT FK_retail_Category_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id),
        CONSTRAINT UQ_retail_Category_entity_name UNIQUE (legal_entity_id, category_name)
    );
    CREATE INDEX IX_retail_Category_entity ON retail.Category(legal_entity_id);
END;
GO

IF OBJECT_ID(N'retail.Vendor', N'U') IS NULL
BEGIN
    CREATE TABLE retail.Vendor (
        vendor_account NVARCHAR(20) NOT NULL CONSTRAINT PK_retail_Vendor PRIMARY KEY,
        vendor_code NVARCHAR(80) NOT NULL,
        vendor_name NVARCHAR(240) NOT NULL,
        vendor_group NVARCHAR(80) NULL,
        currency NVARCHAR(10) NULL,
        payment_terms NVARCHAR(60) NULL,
        delivery_terms NVARCHAR(60) NULL,
        lead_time_days INT NULL,
        moq_units DECIMAL(28,6) NULL,
        otif_pct DECIMAL(9,4) NULL,
        fill_pct DECIMAL(9,4) NULL,
        defect_pct DECIMAL(9,4) NULL,
        lead_adherence_pct DECIMAL(9,4) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_Vendor_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_Vendor_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id),
        CONSTRAINT UQ_retail_Vendor_code UNIQUE (vendor_code)
    );
END;
GO

IF OBJECT_ID(N'retail.Brand', N'U') IS NULL
BEGIN
    CREATE TABLE retail.Brand (
        brand_name NVARCHAR(160) NOT NULL CONSTRAINT PK_retail_Brand PRIMARY KEY,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_Brand_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_Brand_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
END;
GO

IF OBJECT_ID(N'retail.Sku', N'U') IS NULL
BEGIN
    CREATE TABLE retail.Sku (
        sku_id NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_Sku PRIMARY KEY,
        legal_entity_id NVARCHAR(10) NOT NULL,
        category_id NVARCHAR(20) NOT NULL,
        item_name NVARCHAR(240) NOT NULL,
        is_perishable BIT NOT NULL,
        base_ads DECIMAL(28,8) NULL,
        price DECIMAL(28,4) NULL,
        margin_pct DECIMAL(18,8) NULL,
        cost DECIMAL(28,4) NULL,
        lead_time_days INT NULL,
        on_hand_days DECIMAL(18,6) NULL,
        open_po_units DECIMAL(28,6) NULL,
        safety_days DECIMAL(18,6) NULL,
        expiry_days DECIMAL(18,6) NULL,
        growth_factor DECIMAL(18,8) NULL,
        elasticity DECIMAL(18,8) NULL,
        competitor_index DECIMAL(18,6) NULL,
        funding_pct DECIMAL(18,8) NULL,
        cannibalization_pct DECIMAL(18,8) NULL,
        is_promo BIT NOT NULL,
        is_viral BIT NOT NULL,
        sales_uom NVARCHAR(40) NULL,
        buy_uom NVARCHAR(40) NULL,
        pack_factor DECIMAL(18,6) NULL,
        channel NVARCHAR(80) NULL,
        seasonality_factor DECIMAL(18,8) NULL,
        stock_factor DECIMAL(18,8) NULL,
        sales_per_fte DECIMAL(28,4) NULL,
        vendor_account NVARCHAR(20) NULL,
        brand_name NVARCHAR(160) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_Sku_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_Sku_entity FOREIGN KEY (legal_entity_id) REFERENCES retail.LegalEntity(legal_entity_id),
        CONSTRAINT FK_retail_Sku_category FOREIGN KEY (category_id) REFERENCES retail.Category(category_id),
        CONSTRAINT FK_retail_Sku_vendor FOREIGN KEY (vendor_account) REFERENCES retail.Vendor(vendor_account),
        CONSTRAINT FK_retail_Sku_brand FOREIGN KEY (brand_name) REFERENCES retail.Brand(brand_name),
        CONSTRAINT FK_retail_Sku_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
    CREATE INDEX IX_retail_Sku_entity_category ON retail.Sku(legal_entity_id, category_id);
    CREATE INDEX IX_retail_Sku_vendor ON retail.Sku(vendor_account);
    CREATE INDEX IX_retail_Sku_brand ON retail.Sku(brand_name);
END;
GO

IF OBJECT_ID(N'retail.TradeAgreement', N'U') IS NULL
BEGIN
    CREATE TABLE retail.TradeAgreement (
        sku_id NVARCHAR(30) NOT NULL,
        vendor_account NVARCHAR(20) NOT NULL,
        valid_from DATE NOT NULL,
        min_quantity DECIMAL(28,6) NOT NULL,
        item_name NVARCHAR(240) NOT NULL,
        unit_price DECIMAL(28,4) NOT NULL,
        currency NVARCHAR(10) NOT NULL,
        lead_time_days INT NULL,
        discount_pct DECIMAL(18,8) NULL,
        valid_to DATE NULL,
        is_designated BIT NOT NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_TradeAgreement_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_retail_TradeAgreement PRIMARY KEY (sku_id, vendor_account, valid_from, min_quantity),
        CONSTRAINT FK_retail_TradeAgreement_sku FOREIGN KEY (sku_id) REFERENCES retail.Sku(sku_id),
        CONSTRAINT FK_retail_TradeAgreement_vendor FOREIGN KEY (vendor_account) REFERENCES retail.Vendor(vendor_account),
        CONSTRAINT FK_retail_TradeAgreement_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
    CREATE INDEX IX_retail_TradeAgreement_vendor ON retail.TradeAgreement(vendor_account);
    CREATE INDEX IX_retail_TradeAgreement_designated ON retail.TradeAgreement(sku_id, is_designated);
END;
GO

IF OBJECT_ID(N'retail.Promotion', N'U') IS NULL
BEGIN
    CREATE TABLE retail.Promotion (
        promotion_id NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_Promotion PRIMARY KEY,
        promotion_name NVARCHAR(240) NOT NULL,
        discount_type NVARCHAR(120) NOT NULL,
        scope NVARCHAR(40) NULL,
        legal_entity_id NVARCHAR(10) NOT NULL,
        target_category NVARCHAR(200) NULL,
        season NVARCHAR(160) NULL,
        peak_month NVARCHAR(30) NULL,
        mechanism NVARCHAR(300) NULL,
        discount_pct DECIMAL(18,8) NULL,
        value_rule NVARCHAR(160) NULL,
        min_quantity_threshold NVARCHAR(100) NULL,
        supplier_funding_pct DECIMAL(18,8) NULL,
        expected_uplift_pct DECIMAL(18,8) NULL,
        prebuy_uplift_units DECIMAL(28,6) NULL,
        valid_from DATE NULL,
        valid_to DATE NULL,
        d365_construct NVARCHAR(500) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_Promotion_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_Promotion_entity FOREIGN KEY (legal_entity_id) REFERENCES retail.LegalEntity(legal_entity_id),
        CONSTRAINT FK_retail_Promotion_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
    CREATE INDEX IX_retail_Promotion_entity_dates ON retail.Promotion(legal_entity_id, valid_from, valid_to);
END;
GO

IF OBJECT_ID(N'retail.InventorySnapshot', N'U') IS NULL
BEGIN
    CREATE TABLE retail.InventorySnapshot (
        sku_id NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_InventorySnapshot PRIMARY KEY,
        ads DECIMAL(28,8) NULL,
        inventory_position DECIMAL(28,6) NULL,
        reorder_point DECIMAL(28,6) NULL,
        max_inventory DECIMAL(28,6) NULL,
        days_of_supply DECIMAL(28,8) NULL,
        inventory_state NVARCHAR(40) NULL,
        price DECIMAL(28,4) NULL,
        inventory_value DECIMAL(28,4) NULL,
        at_risk_value DECIMAL(28,4) NULL,
        expiry_units DECIMAL(28,6) NULL,
        order_units DECIMAL(28,6) NULL,
        order_value DECIMAL(28,4) NULL,
        weekly_gmv DECIMAL(28,4) NULL,
        margin_amount DECIMAL(28,4) NULL,
        funding_amount DECIMAL(28,4) NULL,
        open_po_units DECIMAL(28,6) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_InventorySnapshot_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_InventorySnapshot_sku FOREIGN KEY (sku_id) REFERENCES retail.Sku(sku_id),
        CONSTRAINT FK_retail_InventorySnapshot_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
    CREATE INDEX IX_retail_InventorySnapshot_state ON retail.InventorySnapshot(inventory_state);
END;
GO

IF OBJECT_ID(N'retail.StoreSkuSnapshot', N'U') IS NULL
BEGIN
    CREATE TABLE retail.StoreSkuSnapshot (
        sku_id NVARCHAR(30) NOT NULL,
        store_id NVARCHAR(20) NOT NULL,
        ads DECIMAL(28,8) NULL,
        on_hand_units DECIMAL(28,6) NULL,
        open_po_units DECIMAL(28,6) NULL,
        inventory_position DECIMAL(28,6) NULL,
        reorder_point DECIMAL(28,6) NULL,
        max_inventory DECIMAL(28,6) NULL,
        days_of_supply DECIMAL(28,8) NULL,
        inventory_state NVARCHAR(40) NULL,
        price DECIMAL(28,4) NULL,
        inventory_value DECIMAL(28,4) NULL,
        at_risk_value DECIMAL(28,4) NULL,
        forecast_7d DECIMAL(28,8) NULL,
        order_sales_units DECIMAL(28,6) NULL,
        pack_factor DECIMAL(18,6) NULL,
        order_buy_units DECIMAL(28,6) NULL,
        order_value DECIMAL(28,4) NULL,
        promo_incremental_margin DECIMAL(28,4) NULL,
        contribution_per_day DECIMAL(28,4) NULL,
        labour_fte DECIMAL(28,8) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_StoreSkuSnapshot_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_retail_StoreSkuSnapshot PRIMARY KEY (sku_id, store_id),
        CONSTRAINT FK_retail_StoreSkuSnapshot_sku FOREIGN KEY (sku_id) REFERENCES retail.Sku(sku_id),
        CONSTRAINT FK_retail_StoreSkuSnapshot_store FOREIGN KEY (store_id) REFERENCES retail.Store(store_id),
        CONSTRAINT FK_retail_StoreSkuSnapshot_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
    CREATE INDEX IX_retail_StoreSkuSnapshot_store_state ON retail.StoreSkuSnapshot(store_id, inventory_state);
    CREATE INDEX IX_retail_StoreSkuSnapshot_state ON retail.StoreSkuSnapshot(inventory_state);
END;
GO

IF OBJECT_ID(N'retail.ReplenishmentProposal', N'U') IS NULL
BEGIN
    CREATE TABLE retail.ReplenishmentProposal (
        sku_id NVARCHAR(30) NOT NULL CONSTRAINT PK_retail_ReplenishmentProposal PRIMARY KEY,
        reorder_required BIT NOT NULL,
        order_sales_units DECIMAL(28,6) NULL,
        buy_uom NVARCHAR(40) NULL,
        order_buy_units DECIMAL(28,6) NULL,
        designated_vendor_account NVARCHAR(20) NULL,
        designated_unit_price DECIMAL(28,4) NULL,
        amount DECIMAL(28,4) NULL,
        best_price_vendor_account NVARCHAR(20) NULL,
        best_price DECIMAL(28,4) NULL,
        saving_vs_designated DECIMAL(28,4) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_ReplenishmentProposal_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_ReplenishmentProposal_sku FOREIGN KEY (sku_id) REFERENCES retail.Sku(sku_id),
        CONSTRAINT FK_retail_ReplenishmentProposal_designated FOREIGN KEY (designated_vendor_account) REFERENCES retail.Vendor(vendor_account),
        CONSTRAINT FK_retail_ReplenishmentProposal_best FOREIGN KEY (best_price_vendor_account) REFERENCES retail.Vendor(vendor_account),
        CONSTRAINT FK_retail_ReplenishmentProposal_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
    CREATE INDEX IX_retail_ReplenishmentProposal_reorder ON retail.ReplenishmentProposal(reorder_required);
END;
GO

IF OBJECT_ID(N'retail.BrandEvent', N'U') IS NULL
BEGIN
    CREATE TABLE retail.BrandEvent (
        store_id NVARCHAR(20) NOT NULL,
        event_name NVARCHAR(240) NOT NULL,
        legal_entity_id NVARCHAR(10) NOT NULL,
        demand_lift DECIMAL(18,8) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_BrandEvent_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_retail_BrandEvent PRIMARY KEY (store_id, event_name),
        CONSTRAINT FK_retail_BrandEvent_store FOREIGN KEY (store_id) REFERENCES retail.Store(store_id),
        CONSTRAINT FK_retail_BrandEvent_entity FOREIGN KEY (legal_entity_id) REFERENCES retail.LegalEntity(legal_entity_id),
        CONSTRAINT FK_retail_BrandEvent_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
END;
GO

IF OBJECT_ID(N'retail.WorkforceSnapshot', N'U') IS NULL
BEGIN
    CREATE TABLE retail.WorkforceSnapshot (
        store_id NVARCHAR(20) NOT NULL CONSTRAINT PK_retail_WorkforceSnapshot PRIMARY KEY,
        event_name NVARCHAR(240) NULL,
        event_lift DECIMAL(18,8) NULL,
        workforce_base DECIMAL(18,6) NULL,
        peak_factor DECIMAL(18,8) NULL,
        scheduled_fte DECIMAL(28,6) NULL,
        required_fte DECIMAL(28,6) NULL,
        gap_fte DECIMAL(28,6) NULL,
        surplus_fte DECIMAL(28,6) NULL,
        coverage_pct DECIMAL(18,6) NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_WorkforceSnapshot_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_WorkforceSnapshot_store FOREIGN KEY (store_id) REFERENCES retail.Store(store_id),
        CONSTRAINT FK_retail_WorkforceSnapshot_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
END;
GO

IF OBJECT_ID(N'retail.MonthlySales', N'U') IS NULL
BEGIN
    CREATE TABLE retail.MonthlySales (
        period_label NVARCHAR(20) NOT NULL,
        legal_entity_id NVARCHAR(10) NOT NULL,
        sales_amount DECIMAL(28,4) NOT NULL,
        source_load_id BIGINT NOT NULL,
        source_sheet NVARCHAR(128) NOT NULL,
        source_row INT NOT NULL,
        loaded_at DATETIME2(3) NOT NULL CONSTRAINT DF_retail_MonthlySales_loaded_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_retail_MonthlySales PRIMARY KEY (period_label, legal_entity_id),
        CONSTRAINT FK_retail_MonthlySales_entity FOREIGN KEY (legal_entity_id) REFERENCES retail.LegalEntity(legal_entity_id),
        CONSTRAINT FK_retail_MonthlySales_load FOREIGN KEY (source_load_id) REFERENCES retail.SourceLoad(source_load_id)
    );
    CREATE INDEX IX_retail_MonthlySales_entity ON retail.MonthlySales(legal_entity_id, period_label);
END;
GO
