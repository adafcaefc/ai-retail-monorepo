BEGIN;

CREATE TABLE IF NOT EXISTS cashflow.assumptions (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    assumption_group VARCHAR(100) NOT NULL,
    assumption_name VARCHAR(255) NOT NULL,

    numeric_value NUMERIC(20, 6),
    text_value TEXT,
    date_value DATE,

    unit VARCHAR(50),
    notes TEXT,
    source_sheet VARCHAR(100) NOT NULL DEFAULT '02 Assumptions',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_assumptions_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_assumptions_batch_name
        UNIQUE (
            import_batch_id,
            assumption_group,
            assumption_name
        )
);

CREATE TABLE IF NOT EXISTS cashflow.ar_collections (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    invoice_number VARCHAR(50) NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_segment VARCHAR(100),

    invoice_date DATE,
    payment_terms_days INTEGER,
    due_date DATE,

    original_week INTEGER,
    expected_week INTEGER,

    currency VARCHAR(10) NOT NULL,
    amount_idr_mn NUMERIC(20, 2),
    usd_amount NUMERIC(20, 2),
    idr_value_mn NUMERIC(20, 2),

    delay_flag VARCHAR(100),
    notes TEXT,

    source_sheet VARCHAR(100) NOT NULL DEFAULT '03 AR Collections',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ar_collections_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_ar_collections_batch_invoice
        UNIQUE (
            import_batch_id,
            invoice_number
        ),

    CONSTRAINT chk_ar_original_week
        CHECK (
            original_week IS NULL
            OR original_week BETWEEN 1 AND 13
        ),

    CONSTRAINT chk_ar_expected_week
        CHECK (
            expected_week IS NULL
            OR expected_week BETWEEN 1 AND 13
        )
);

CREATE TABLE IF NOT EXISTS cashflow.ap_payables (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    bill_number VARCHAR(50) NOT NULL,
    vendor_name VARCHAR(255) NOT NULL,
    category VARCHAR(255),

    payment_terms_days INTEGER,
    due_date DATE,
    payment_week INTEGER,

    currency VARCHAR(10) NOT NULL,
    amount_idr_mn NUMERIC(20, 2),
    usd_amount NUMERIC(20, 2),
    idr_value_mn NUMERIC(20, 2),

    is_deferrable BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,

    source_sheet VARCHAR(100) NOT NULL DEFAULT '04 AP USD Payables',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ap_payables_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_ap_payables_batch_bill
        UNIQUE (
            import_batch_id,
            bill_number
        ),

    CONSTRAINT chk_ap_payment_week
        CHECK (
            payment_week IS NULL
            OR payment_week BETWEEN 1 AND 13
        )
);

CREATE TABLE IF NOT EXISTS cashflow.other_outflows (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    category VARCHAR(255) NOT NULL,
    week_number INTEGER NOT NULL,
    amount_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,

    source_sheet VARCHAR(100) NOT NULL DEFAULT '05 Other Outflows',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_other_outflows_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_other_outflows_batch_category_week
        UNIQUE (
            import_batch_id,
            category,
            week_number
        ),

    CONSTRAINT chk_other_outflows_week
        CHECK (
            week_number BETWEEN 1 AND 13
        )
);

CREATE TABLE IF NOT EXISTS cashflow.weekly_forecast (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    week_number INTEGER NOT NULL,
    week_start DATE,
    week_end DATE,

    customer_collections_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    total_inflows_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,

    vendor_payments_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    vendor_payments_usd_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    payroll_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    rent_utilities_opex_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    taxes_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    loan_repayment_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,

    total_outflows_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    net_cash_flow_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,

    opening_cash_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    closing_cash_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,

    minimum_buffer_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    headroom_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,

    status VARCHAR(30) NOT NULL,

    source_sheet VARCHAR(100) NOT NULL DEFAULT '06 Cash Forecast 13W',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_weekly_forecast_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_weekly_forecast_batch_week
        UNIQUE (
            import_batch_id,
            week_number
        ),

    CONSTRAINT chk_weekly_forecast_week
        CHECK (
            week_number BETWEEN 1 AND 13
        ),

    CONSTRAINT chk_weekly_forecast_status
        CHECK (
            status IN (
                'OK',
                'SHORTAGE',
                'RISK'
            )
        )
);

CREATE TABLE IF NOT EXISTS cashflow.fx_scenarios (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    scenario_name VARCHAR(255) NOT NULL,
    action_description TEXT,

    usd_exposure NUMERIC(20, 2),
    fx_rate_idr_per_usd NUMERIC(20, 4),
    movement_vs_spot NUMERIC(20, 4),

    fx_cash_impact_idr_mn NUMERIC(20, 2),
    downside_avoided_idr_mn NUMERIC(20, 2),
    premium_idr_mn NUMERIC(20, 2),

    liquidity_effect TEXT,
    confidence_label VARCHAR(100),
    notes TEXT,

    is_recommended BOOLEAN NOT NULL DEFAULT FALSE,

    source_sheet VARCHAR(100) NOT NULL DEFAULT '07 FX Scenarios',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_fx_scenarios_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_fx_scenarios_batch_name
        UNIQUE (
            import_batch_id,
            scenario_name
        )
);

CREATE TABLE IF NOT EXISTS cashflow.recommendations (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    recommendation_type VARCHAR(50) NOT NULL,
    recommendation_order INTEGER NOT NULL DEFAULT 1,

    action_title VARCHAR(255) NOT NULL,
    action_description TEXT NOT NULL,

    expected_impact TEXT,
    assumptions JSONB NOT NULL DEFAULT '[]'::JSONB,
    risks JSONB NOT NULL DEFAULT '[]'::JSONB,

    requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
    approval_route VARCHAR(255),

    source_sheet VARCHAR(100) NOT NULL DEFAULT '08 Recommendation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_recommendations_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT chk_recommendation_type
        CHECK (
            recommendation_type IN (
                'LIQUIDITY',
                'FX',
                'GOVERNANCE'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_assumptions_import_batch
    ON cashflow.assumptions (import_batch_id);

CREATE INDEX IF NOT EXISTS idx_ar_collections_import_batch
    ON cashflow.ar_collections (import_batch_id);

CREATE INDEX IF NOT EXISTS idx_ar_collections_expected_week
    ON cashflow.ar_collections (expected_week);

CREATE INDEX IF NOT EXISTS idx_ap_payables_import_batch
    ON cashflow.ap_payables (import_batch_id);

CREATE INDEX IF NOT EXISTS idx_ap_payables_payment_week
    ON cashflow.ap_payables (payment_week);

CREATE INDEX IF NOT EXISTS idx_other_outflows_import_batch
    ON cashflow.other_outflows (import_batch_id);

CREATE INDEX IF NOT EXISTS idx_weekly_forecast_import_batch
    ON cashflow.weekly_forecast (import_batch_id);

CREATE INDEX IF NOT EXISTS idx_fx_scenarios_import_batch
    ON cashflow.fx_scenarios (import_batch_id);

CREATE INDEX IF NOT EXISTS idx_recommendations_import_batch
    ON cashflow.recommendations (import_batch_id);

COMMIT;