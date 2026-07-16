BEGIN;

CREATE SCHEMA IF NOT EXISTS collections;


CREATE TABLE IF NOT EXISTS collections.assumptions (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    assumption_group VARCHAR(100) NOT NULL,
    assumption_name VARCHAR(255) NOT NULL,

    numeric_value NUMERIC(24, 8),
    text_value TEXT,
    unit VARCHAR(50),
    notes TEXT,

    source_sheet VARCHAR(100) NOT NULL
        DEFAULT '01 Assumptions',

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_collections_assumptions_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_collections_assumptions_batch_name
        UNIQUE (
            import_batch_id,
            assumption_group,
            assumption_name
        )
);


CREATE TABLE IF NOT EXISTS collections.customer_credit_aging (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    customer_id VARCHAR(50) NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_segment VARCHAR(100),

    payment_terms VARCHAR(50),
    currency VARCHAR(10) NOT NULL,

    credit_limit_idr_mn NUMERIC(20, 2),
    days_beyond_terms INTEGER NOT NULL DEFAULT 0,

    payment_trend VARCHAR(30),
    has_dispute BOOLEAN NOT NULL DEFAULT FALSE,
    on_time_percentage NUMERIC(12, 8),

    current_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    overdue_1_30_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    overdue_31_60_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    overdue_61_90_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    overdue_90_plus_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,

    total_ar_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    overdue_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    overdue_percentage NUMERIC(12, 8),
    credit_utilization NUMERIC(12, 8),

    source_sheet VARCHAR(100) NOT NULL
        DEFAULT '02 Customer Credit & Aging',

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_customer_credit_aging_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_customer_credit_aging_batch_customer
        UNIQUE (
            import_batch_id,
            customer_id
        ),

    CONSTRAINT chk_customer_credit_currency
        CHECK (
            currency IN (
                'IDR',
                'USD'
            )
        ),

    CONSTRAINT chk_customer_credit_trend
        CHECK (
            payment_trend IS NULL
            OR payment_trend IN (
                'Improving',
                'Stable',
                'Worsening'
            )
        ),

    CONSTRAINT chk_customer_credit_non_negative
        CHECK (
            credit_limit_idr_mn >= 0
            AND days_beyond_terms >= 0
            AND current_idr_mn >= 0
            AND overdue_1_30_idr_mn >= 0
            AND overdue_31_60_idr_mn >= 0
            AND overdue_61_90_idr_mn >= 0
            AND overdue_90_plus_idr_mn >= 0
            AND total_ar_idr_mn >= 0
            AND overdue_idr_mn >= 0
        )
);


CREATE TABLE IF NOT EXISTS collections.risk_scores (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    customer_id VARCHAR(50) NOT NULL,
    customer_name VARCHAR(255) NOT NULL,

    balance_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    utilization_percentage NUMERIC(12, 8),
    overdue_61_plus_idr_mn NUMERIC(20, 2) NOT NULL DEFAULT 0,
    overdue_severity_percentage NUMERIC(12, 8),

    days_beyond_terms INTEGER NOT NULL DEFAULT 0,
    payment_trend VARCHAR(30),
    has_dispute BOOLEAN NOT NULL DEFAULT FALSE,

    dbt_points NUMERIC(12, 6) NOT NULL DEFAULT 0,
    severity_points NUMERIC(12, 6) NOT NULL DEFAULT 0,
    utilization_points NUMERIC(12, 6) NOT NULL DEFAULT 0,
    trend_points NUMERIC(12, 6) NOT NULL DEFAULT 0,
    dispute_points NUMERIC(12, 6) NOT NULL DEFAULT 0,

    risk_score NUMERIC(12, 6) NOT NULL,
    risk_tier VARCHAR(20) NOT NULL,
    risk_rank INTEGER NOT NULL,

    source_sheet VARCHAR(100) NOT NULL
        DEFAULT '03 Risk Scoring',

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_risk_scores_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_risk_scores_batch_customer
        UNIQUE (
            import_batch_id,
            customer_id
        ),

    CONSTRAINT chk_risk_score_tier
        CHECK (
            risk_tier IN (
                'Low',
                'Medium',
                'High'
            )
        ),

    CONSTRAINT chk_risk_score_range
        CHECK (
            risk_score >= 0
            AND risk_score <= 100
        ),

    CONSTRAINT chk_risk_rank_positive
        CHECK (
            risk_rank > 0
        )
);


CREATE TABLE IF NOT EXISTS collections.dso_cash_impact (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    total_ar_idr_mn NUMERIC(20, 2) NOT NULL,
    current_ar_idr_mn NUMERIC(20, 2) NOT NULL,
    overdue_ar_idr_mn NUMERIC(20, 2) NOT NULL,
    overdue_percentage NUMERIC(12, 8) NOT NULL,

    annual_credit_sales_idr_mn NUMERIC(20, 2) NOT NULL,
    daily_credit_sales_idr_mn NUMERIC(20, 8) NOT NULL,

    current_dso_days NUMERIC(12, 6) NOT NULL,
    target_dso_days NUMERIC(12, 6) NOT NULL,
    dso_gap_days NUMERIC(12, 6) NOT NULL,

    cash_freed_at_target_idr_mn NUMERIC(20, 8) NOT NULL,
    high_risk_provision_idr_mn NUMERIC(20, 2),

    source_sheet VARCHAR(100) NOT NULL
        DEFAULT '04 DSO & Cash Impact',

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_dso_cash_impact_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_dso_cash_impact_batch
        UNIQUE (import_batch_id),

    CONSTRAINT chk_dso_cash_impact_non_negative
        CHECK (
            total_ar_idr_mn >= 0
            AND current_ar_idr_mn >= 0
            AND overdue_ar_idr_mn >= 0
            AND annual_credit_sales_idr_mn >= 0
            AND daily_credit_sales_idr_mn >= 0
            AND current_dso_days >= 0
            AND target_dso_days >= 0
            AND cash_freed_at_target_idr_mn >= 0
        )
);


CREATE TABLE IF NOT EXISTS collections.risk_tier_exposure (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    risk_tier VARCHAR(20) NOT NULL,
    customer_count INTEGER NOT NULL,
    exposure_idr_mn NUMERIC(20, 2) NOT NULL,
    percentage_of_ar NUMERIC(12, 8) NOT NULL,

    notes TEXT,

    source_sheet VARCHAR(100) NOT NULL
        DEFAULT '04 DSO & Cash Impact',

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_risk_tier_exposure_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_risk_tier_exposure_batch_tier
        UNIQUE (
            import_batch_id,
            risk_tier
        ),

    CONSTRAINT chk_risk_tier_exposure_tier
        CHECK (
            risk_tier IN (
                'Low',
                'Medium',
                'High'
            )
        ),

    CONSTRAINT chk_risk_tier_exposure_non_negative
        CHECK (
            customer_count >= 0
            AND exposure_idr_mn >= 0
            AND percentage_of_ar >= 0
        )
);


CREATE TABLE IF NOT EXISTS collections.worklist (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    priority_rank INTEGER NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_segment VARCHAR(100),

    overdue_idr_mn NUMERIC(20, 2) NOT NULL,
    oldest_aging_bucket VARCHAR(50),

    risk_tier VARCHAR(20) NOT NULL,
    risk_score NUMERIC(12, 6) NOT NULL,

    recommended_action TEXT NOT NULL,

    recovery_percentage NUMERIC(12, 8) NOT NULL,
    expected_recovery_idr_mn NUMERIC(20, 2) NOT NULL,

    source_sheet VARCHAR(100) NOT NULL
        DEFAULT '05 Collections Worklist',

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_worklist_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_worklist_batch_rank
        UNIQUE (
            import_batch_id,
            priority_rank
        ),

    CONSTRAINT chk_worklist_priority_rank
        CHECK (
            priority_rank > 0
        ),

    CONSTRAINT chk_worklist_risk_tier
        CHECK (
            risk_tier IN (
                'Low',
                'Medium',
                'High'
            )
        ),

    CONSTRAINT chk_worklist_amounts
        CHECK (
            overdue_idr_mn >= 0
            AND risk_score >= 0
            AND risk_score <= 100
            AND recovery_percentage >= 0
            AND recovery_percentage <= 1
            AND expected_recovery_idr_mn >= 0
        )
);


CREATE TABLE IF NOT EXISTS collections.recommendations (
    id BIGSERIAL PRIMARY KEY,
    import_batch_id BIGINT NOT NULL,

    recommendation_type VARCHAR(30) NOT NULL,
    recommendation_order INTEGER NOT NULL,

    action_title VARCHAR(255) NOT NULL,
    action_description TEXT NOT NULL,
    expected_impact TEXT,

    requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
    approval_route VARCHAR(255),

    source_sheet VARCHAR(100) NOT NULL
        DEFAULT '06 Recommendation',

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_collections_recommendations_import_batch
        FOREIGN KEY (import_batch_id)
        REFERENCES audit.import_batches (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_collections_recommendations_order
        UNIQUE (
            import_batch_id,
            recommendation_order
        ),

    CONSTRAINT chk_collections_recommendation_type
        CHECK (
            recommendation_type IN (
                'ACCELERATE',
                'CONTAIN',
                'PREVENT'
            )
        ),

    CONSTRAINT chk_collections_recommendation_order
        CHECK (
            recommendation_order > 0
        )
);


CREATE INDEX IF NOT EXISTS idx_collections_assumptions_batch
    ON collections.assumptions (import_batch_id);


CREATE INDEX IF NOT EXISTS idx_customer_credit_aging_batch
    ON collections.customer_credit_aging (import_batch_id);


CREATE INDEX IF NOT EXISTS idx_customer_credit_aging_overdue
    ON collections.customer_credit_aging (
        import_batch_id,
        overdue_idr_mn DESC
    );


CREATE INDEX IF NOT EXISTS idx_risk_scores_batch
    ON collections.risk_scores (import_batch_id);


CREATE INDEX IF NOT EXISTS idx_risk_scores_tier
    ON collections.risk_scores (
        import_batch_id,
        risk_tier
    );


CREATE INDEX IF NOT EXISTS idx_risk_scores_rank
    ON collections.risk_scores (
        import_batch_id,
        risk_rank
    );


CREATE INDEX IF NOT EXISTS idx_dso_cash_impact_batch
    ON collections.dso_cash_impact (import_batch_id);


CREATE INDEX IF NOT EXISTS idx_risk_tier_exposure_batch
    ON collections.risk_tier_exposure (import_batch_id);


CREATE INDEX IF NOT EXISTS idx_collections_worklist_batch
    ON collections.worklist (import_batch_id);


CREATE INDEX IF NOT EXISTS idx_collections_worklist_priority
    ON collections.worklist (
        import_batch_id,
        priority_rank
    );


CREATE INDEX IF NOT EXISTS idx_collections_recommendations_batch
    ON collections.recommendations (import_batch_id);


COMMIT;