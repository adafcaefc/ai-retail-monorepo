/*
  Persisted cross-agent inbox handoffs.

  This migration is additive and rerunnable.  It deliberately lives outside
  chat.actions: a forecast basket can contain 16,000 rows, and its immutable
  snapshot is a business handoff rather than a monitoring action.
*/

IF SCHEMA_ID(N'retail') IS NULL
    EXEC(N'CREATE SCHEMA retail');
GO

IF OBJECT_ID(N'retail.agent_handoffs', N'U') IS NULL
BEGIN
    CREATE TABLE retail.agent_handoffs (
        handoff_id             UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT PK_retail_agent_handoffs PRIMARY KEY,
        source_agent           NVARCHAR(80) NOT NULL,
        target_agent           NVARCHAR(80) NOT NULL,
        handoff_type           NVARCHAR(40) NOT NULL,
        status                 NVARCHAR(30) NOT NULL,
        scope_json             NVARCHAR(MAX) NOT NULL,
        source_snapshot_date   DATE NOT NULL,
        source_import_batch_id BIGINT NULL,
        basket_hash             CHAR(64) NOT NULL,
        payload_json            NVARCHAR(MAX) NOT NULL,
        created_at             DATETIME2(3) NOT NULL
            CONSTRAINT DF_retail_agent_handoffs_created_at DEFAULT SYSUTCDATETIME(),
        updated_at             DATETIME2(3) NOT NULL
            CONSTRAINT DF_retail_agent_handoffs_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_retail_agent_handoffs_route CHECK (
            (source_agent = N'retail.demand_forecasting'
             AND target_agent = N'retail.replenishment'
             AND handoff_type = N'forecast_basket')
            OR
            (source_agent = N'retail.demand_forecasting'
             AND target_agent = N'retail.inventory_risk'
             AND handoff_type = N'risk_flag')
        ),
        CONSTRAINT CK_retail_agent_handoffs_status CHECK (
            status IN (N'approved', N'rejected', N'cancelled', N'reopened', N'sent')
        ),
        CONSTRAINT CK_retail_agent_handoffs_scope_json CHECK (ISJSON(scope_json) = 1),
        CONSTRAINT CK_retail_agent_handoffs_payload_json CHECK (ISJSON(payload_json) = 1),
        CONSTRAINT CK_retail_agent_handoffs_hash CHECK (
            LEN(basket_hash) = 64
            AND basket_hash NOT LIKE '%[^0-9a-fA-F]%'
        )
    );
END;
GO

IF OBJECT_ID(N'retail.agent_handoff_events', N'U') IS NULL
BEGIN
    CREATE TABLE retail.agent_handoff_events (
        event_id     BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_retail_agent_handoff_events PRIMARY KEY,
        handoff_id   UNIQUEIDENTIFIER NOT NULL,
        from_status  NVARCHAR(30) NULL,
        to_status    NVARCHAR(30) NOT NULL,
        created_at   DATETIME2(3) NOT NULL
            CONSTRAINT DF_retail_agent_handoff_events_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_retail_agent_handoff_events_handoff
            FOREIGN KEY (handoff_id)
            REFERENCES retail.agent_handoffs(handoff_id)
            ON DELETE CASCADE,
        CONSTRAINT CK_retail_agent_handoff_events_from_status CHECK (
            from_status IS NULL
            OR from_status IN (N'approved', N'rejected', N'cancelled', N'reopened', N'sent')
        ),
        CONSTRAINT CK_retail_agent_handoff_events_to_status CHECK (
            to_status IN (N'approved', N'rejected', N'cancelled', N'reopened', N'sent')
        )
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_retail_agent_handoffs_target_status_created'
      AND object_id = OBJECT_ID(N'retail.agent_handoffs')
)
BEGIN
    CREATE INDEX IX_retail_agent_handoffs_target_status_created
        ON retail.agent_handoffs(target_agent, status, created_at DESC);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_retail_agent_handoffs_source_hash'
      AND object_id = OBJECT_ID(N'retail.agent_handoffs')
)
BEGIN
    CREATE INDEX IX_retail_agent_handoffs_source_hash
        ON retail.agent_handoffs(source_agent, handoff_type, basket_hash);
END;
GO

/* A risk flag is idempotent for one immutable basket.  The filtered unique
   index closes the race where two clicks arrive before either request can
   observe the other's sent row; the service still returns an existing row for
   the normal repeat-click path. */
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'UX_retail_agent_handoffs_risk_snapshot'
      AND object_id = OBJECT_ID(N'retail.agent_handoffs')
)
BEGIN
    CREATE UNIQUE INDEX UX_retail_agent_handoffs_risk_snapshot
        ON retail.agent_handoffs(source_agent, target_agent, handoff_type, basket_hash)
        WHERE handoff_type = N'risk_flag' AND status = N'sent';
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_retail_agent_handoff_events_handoff_created'
      AND object_id = OBJECT_ID(N'retail.agent_handoff_events')
)
BEGIN
    CREATE INDEX IX_retail_agent_handoff_events_handoff_created
        ON retail.agent_handoff_events(handoff_id, created_at, event_id);
END;
GO
