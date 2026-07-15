BEGIN;

CREATE SCHEMA IF NOT EXISTS cashflow;
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.import_batches (
    id BIGSERIAL PRIMARY KEY,

    agent_name VARCHAR(100) NOT NULL,
    workbook_name VARCHAR(255) NOT NULL,
    workbook_version VARCHAR(100),
    workbook_path VARCHAR(500),

    import_status VARCHAR(30) NOT NULL DEFAULT 'STARTED',

    imported_by VARCHAR(255),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    total_sheets INTEGER NOT NULL DEFAULT 0,
    total_rows INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    CONSTRAINT import_batches_status_check
        CHECK (
            import_status IN (
                'STARTED',
                'COMPLETED',
                'FAILED',
                'CANCELLED'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_import_batches_agent_name
    ON audit.import_batches (agent_name);

CREATE INDEX IF NOT EXISTS idx_import_batches_imported_at
    ON audit.import_batches (imported_at DESC);

CREATE INDEX IF NOT EXISTS idx_import_batches_status
    ON audit.import_batches (import_status);

COMMIT;