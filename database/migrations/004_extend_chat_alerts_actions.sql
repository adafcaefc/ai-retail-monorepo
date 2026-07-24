BEGIN;

-- Extend chat.alerts / chat.actions for monitoring action-specs,
-- simulation summaries, and planned/approved workflow.

ALTER TABLE chat.actions
    ADD COLUMN IF NOT EXISTS spec TEXT;

ALTER TABLE chat.actions
    ADD COLUMN IF NOT EXISTS impact TEXT;

ALTER TABLE chat.actions
    ADD COLUMN IF NOT EXISTS simulation_summary JSONB;

-- Prefer lowercase planned / approved status strings.
UPDATE chat.actions
SET status = lower(status)
WHERE status IS NOT NULL
  AND status <> lower(status);

UPDATE chat.actions
SET status = 'planned'
WHERE status IS NULL
   OR lower(status) IN ('pending');

ALTER TABLE chat.actions
    ALTER COLUMN status SET DEFAULT 'planned';

-- Keep names readable for longer CFO action titles.
ALTER TABLE chat.actions
    ALTER COLUMN action TYPE VARCHAR(120);

ALTER TABLE chat.alerts
    ALTER COLUMN name TYPE VARCHAR(120);

ALTER TABLE chat.alerts
    ALTER COLUMN issue TYPE TEXT;

-- Optional FK when alert_id is present (ignore if already exists).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_chat_actions_alert_id'
    ) THEN
        ALTER TABLE chat.actions
            ADD CONSTRAINT fk_chat_actions_alert_id
            FOREIGN KEY (alert_id)
            REFERENCES chat.alerts (id)
            ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chat_actions_alert_id
    ON chat.actions (alert_id);

CREATE INDEX IF NOT EXISTS idx_chat_actions_status
    ON chat.actions (status);

CREATE INDEX IF NOT EXISTS idx_chat_alerts_agent
    ON chat.alerts (agent);

COMMIT;
