"""Add `chat.monitoring_runs` and a `run_id` column on alerts/actions.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/migrate_monitoring_runs.py

Idempotent throughout (`IF NOT EXISTS` on the table, indexes and both new
columns), like `create_chat_schema.py` -- safe to run against a database that
already has alerts/actions rows from before this migration existed. Those
older rows simply keep `run_id = NULL`, which is why the column is nullable
rather than backfilled: there is no run to point them at.

WHY THIS EXISTS
---------------
Monitoring stopped deleting on every recalculate (`populate_alerts` now only
appends). `chat.monitoring_runs` makes "the previous batch is saved" a
first-class, queryable fact -- one row per populate_alerts call, mirroring the
existing `audit.import_batches` pattern -- and `run_id` on `chat.alerts` /
`chat.actions` ties every row it wrote back to that run.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402

STATEMENTS: list[tuple[str, str]] = [
    (
        "chat.monitoring_runs",
        """
        CREATE TABLE IF NOT EXISTS chat.monitoring_runs (
            id                 BIGSERIAL PRIMARY KEY,
            agent              VARCHAR(60) NOT NULL,
            -- STARTED/COMPLETED/FAILED, matching audit.import_batches'
            -- import_status vocabulary rather than inventing a new one.
            run_status         VARCHAR(30) NOT NULL DEFAULT 'STARTED',
            started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at       TIMESTAMPTZ,
            monitoring_passes  INTEGER NOT NULL DEFAULT 0,
            alerts_created     INTEGER NOT NULL DEFAULT 0,
            actions_created    INTEGER NOT NULL DEFAULT 0,
            error_message      TEXT
        )
        """,
    ),
    (
        "idx_chat_monitoring_runs_agent",
        """
        CREATE INDEX IF NOT EXISTS idx_chat_monitoring_runs_agent
            ON chat.monitoring_runs (agent, started_at DESC)
        """,
    ),
    (
        "chat.alerts.run_id",
        """
        ALTER TABLE chat.alerts
            ADD COLUMN IF NOT EXISTS run_id BIGINT
                REFERENCES chat.monitoring_runs(id) ON DELETE SET NULL
        """,
    ),
    (
        "idx_chat_alerts_agent_date_created",
        """
        CREATE INDEX IF NOT EXISTS idx_chat_alerts_agent_date_created
            ON chat.alerts (agent, date_created DESC)
        """,
    ),
    (
        "chat.actions.run_id",
        """
        ALTER TABLE chat.actions
            ADD COLUMN IF NOT EXISTS run_id BIGINT
                REFERENCES chat.monitoring_runs(id) ON DELETE SET NULL
        """,
    ),
    (
        "idx_chat_actions_agent_created_at",
        """
        CREATE INDEX IF NOT EXISTS idx_chat_actions_agent_created_at
            ON chat.actions (agent, created_at DESC)
        """,
    ),
]

EXPECTED_TABLES: tuple[str, ...] = ("monitoring_runs",)
EXPECTED_COLUMNS: dict[str, str] = {
    "chat.alerts": "run_id",
    "chat.actions": "run_id",
}


def main() -> int:
    engine = get_engine()
    print(f"database: {engine.url.database}\n")

    with engine.begin() as connection:
        for label, statement in STATEMENTS:
            connection.execute(text(statement))
            print(f"  ok  {label}")

    missing: list[str] = []
    with engine.connect() as connection:
        present_tables = set(
            connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'chat'
                    """
                )
            )
            .scalars()
            .all()
        )
        print("\nSchema chat:")
        for name in EXPECTED_TABLES:
            mark = "ok " if name in present_tables else "MISSING"
            print(f"  {mark} chat.{name}")
            if name not in present_tables:
                missing.append(f"chat.{name}")

        print()
        for qualified, column in EXPECTED_COLUMNS.items():
            schema, table = qualified.split(".")
            found = connection.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = :table
                      AND column_name = :column
                    """
                ),
                {"schema": schema, "table": table, "column": column},
            ).first()
            mark = "ok " if found else "MISSING"
            print(f"  {mark} {qualified}.{column}")
            if not found:
                missing.append(f"{qualified}.{column}")

    if missing:
        print(f"\nFAIL  {len(missing)} item(s) missing: {', '.join(missing)}")
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
