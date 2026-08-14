"""SUPERSEDED: the backend now runs on Azure SQL exclusively (get_engine() in
src/db/db.py builds an mssql+pyodbc connection from AZURE_SQL_CONNECTIONSTRING),
and this script's DDL is Postgres syntax, which will fail against Azure SQL.
The current schema definition is sql/retail/002_create_orm_schema.sql. Kept
here only as the historical record of the Postgres-era shape.

Create the `chat` schema and `retail.formula`: everything the agents write to.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/create_chat_schema.py

Idempotent by `CREATE TABLE IF NOT EXISTS`, like `create_retail_schema.py` and
for the same reason: conversations and alerts accumulate, and a script that
drops them would destroy a demo mid-run. To start over, `DROP SCHEMA chat
CASCADE` by hand and mean it.

WHY THIS EXISTS
---------------
`ai-retail-pg-db` carried `retail` and `audit` but no `chat`, so nothing in the
retail database could store a conversation, a message, an alert or an action.
The sibling `ai-finance-forum-pg-db` has all four. The DDL below is that
schema, read back off the live finance database rather than rewritten from
memory, because `src/actions/repository.py` and `src/chatflow/repository.py`
issue raw SQL against these exact column names.

Two details are load-bearing and deliberately match finance rather than
improve on it:

* No `gen_random_uuid()` default on any `id`. Both repositories generate the
  UUID in Python (`repository.py:153`, `chatflow/repository.py:31`) and pass it
  in. A database-side default would be dead code that quietly disagrees with
  the id the application already returned to its caller.
* `chat.actions.routes` is `text[]`, not a join table. It is a list of owner
  labels the model chose from a fixed prompt list, never queried by element.

`retail.formula` joins them here rather than living in `create_retail_schema.py`
because it is the same kind of table: application state the agents read and the
Formula Manager writes, not warehouse data seeded from the workbook.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402

# (label, statement). Order matters: a table may only reference one already
# created above it.
STATEMENTS: list[tuple[str, str]] = [
    (
        "schema chat",
        "CREATE SCHEMA IF NOT EXISTS chat",
    ),
    (
        "schema retail",
        "CREATE SCHEMA IF NOT EXISTS retail",
    ),
    # ------------------------------------------------------------ conversations
    (
        "chat.conversations",
        """
        CREATE TABLE IF NOT EXISTS chat.conversations (
            id         uuid PRIMARY KEY,
            title      varchar NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ),
    (
        "chat.messages",
        """
        CREATE TABLE IF NOT EXISTS chat.messages (
            id              uuid PRIMARY KEY,
            conversation_id uuid NOT NULL
                            REFERENCES chat.conversations(id) ON DELETE CASCADE,
            -- 'user' or 'chatbot'; `channel` carries the agent id the message
            -- was sent on, which is how one conversation stays attributable
            -- when the reader switches boards.
            sender          varchar NOT NULL,
            channel         varchar NOT NULL,
            message         text NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
        """,
    ),
    (
        "idx_chat_messages_conversation",
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
            ON chat.messages (conversation_id)
        """,
    ),
    (
        "idx_chat_messages_created_at",
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at
            ON chat.messages (created_at)
        """,
    ),
    # ------------------------------------------------------------------ alerts
    (
        "chat.alerts",
        """
        CREATE TABLE IF NOT EXISTS chat.alerts (
            id           uuid PRIMARY KEY,
            -- Every column but the id is nullable, matching finance. A
            -- monitoring pass that returns a partial alert is still worth
            -- storing; losing it to a NOT NULL would hide the fact that the
            -- pass ran at all.
            name         varchar,
            subagent     varchar,
            agent        varchar,
            issue        text,
            date_created timestamptz
        )
        """,
    ),
    (
        "idx_chat_alerts_agent",
        """
        CREATE INDEX IF NOT EXISTS idx_chat_alerts_agent
            ON chat.alerts (agent)
        """,
    ),
    # ----------------------------------------------------------------- actions
    (
        "chat.actions",
        """
        CREATE TABLE IF NOT EXISTS chat.actions (
            id                 uuid PRIMARY KEY,
            action             varchar NOT NULL,
            agent              varchar NOT NULL,
            routes             text[] NOT NULL,
            alert_id           uuid REFERENCES chat.alerts(id) ON DELETE CASCADE,
            -- 'planned' until an owner approves. Never defaulted to approved:
            -- the whole workflow rests on a stored action being a proposal.
            status             varchar DEFAULT 'planned',
            -- Written explicitly by `repository.save_actions` as NOW(), not
            -- defaulted, which is why it is nullable here: matching finance
            -- exactly keeps that INSERT working unchanged.
            created_at         timestamptz,
            spec               text,
            impact             text,
            simulation_summary jsonb,
            reason             text
        )
        """,
    ),
    (
        "chat.actions.created_at (existing tables)",
        # CREATE TABLE IF NOT EXISTS is a no-op on a table that already exists,
        # so a column added after the first run needs its own statement. This
        # one is here because the first cut of this script omitted created_at
        # and `save_actions` writes to it.
        """
        ALTER TABLE chat.actions
            ADD COLUMN IF NOT EXISTS created_at timestamptz
        """,
    ),
    (
        "idx_chat_actions_alert_id",
        """
        CREATE INDEX IF NOT EXISTS idx_chat_actions_alert_id
            ON chat.actions (alert_id)
        """,
    ),
    (
        "idx_chat_actions_status",
        """
        CREATE INDEX IF NOT EXISTS idx_chat_actions_status
            ON chat.actions (status)
        """,
    ),
    # ---------------------------------------------------------------- formulas
    (
        "retail.formula",
        """
        CREATE TABLE IF NOT EXISTS retail.formula (
            id          text PRIMARY KEY,
            number      integer NOT NULL,
            name        text NOT NULL,
            logic       text,
            -- What one row of this rule's inputs counts. Explicit and
            -- constrained because it decides which table the rule may be fed
            -- from, and getting it wrong produces a plausible wrong number
            -- rather than an error: `f04-position` (store_sku) and
            -- `f20-days-of-supply` (chain_sku) both take a parameter named
            -- `position` and mean different things by it.
            --
            -- The CHECK is not only a guard. `describe_retail_*_tables`
            -- surfaces CHECK definitions to the agents, and SCHEMA_TOOLS_PROMPT
            -- tells them to treat those as binding, so the legal grains
            -- document themselves with no prompt to keep in step.
            grain       text NOT NULL
                        CHECK (grain IN ('store_sku', 'chain_sku', 'store_roster')),
            -- Provenance only: which workbook sheet the rule was transcribed
            -- from. Free text, nullable, and read by nothing. Grain used to be
            -- inferred from it, which asked whoever adds a rule through the
            -- Formula Manager to know that 'ENGINE_STORE' means per-store --
            -- and they do not have the workbook.
            sheet       text,
            result_type text NOT NULL DEFAULT 'number',
            expression  text NOT NULL,
            -- The whole parameter list, as the service already validates and
            -- rewrites it (`service._check_parameters`). A child table would
            -- add joins and a second write path for no gain.
            parameters  jsonb NOT NULL DEFAULT '[]'::jsonb,
            updated_at  timestamptz NOT NULL DEFAULT now()
        )
        """,
    ),
    (
        "idx_retail_formula_number",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_retail_formula_number
            ON retail.formula (number)
        """,
    ),
]

EXPECTED: dict[str, tuple[str, ...]] = {
    "chat": ("actions", "alerts", "conversations", "messages"),
    "retail": ("formula",),
}


def main() -> int:
    engine = get_engine()
    print(f"database: {engine.url.database}\n")

    with engine.begin() as connection:
        for label, statement in STATEMENTS:
            connection.execute(text(statement))
            print(f"  ok  {label}")

    # Report what is actually there, not what the script believes it wrote. A
    # rerun against the wrong database is the failure worth catching, and it
    # shows up here as a table list that does not contain what was asked for.
    missing: list[str] = []
    with engine.connect() as connection:
        for schema, wanted in EXPECTED.items():
            present = set(
                connection.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = :schema
                        """
                    ),
                    {"schema": schema},
                )
                .scalars()
                .all()
            )
            print(f"\nSchema {schema}:")
            for name in wanted:
                mark = "ok " if name in present else "MISSING"
                print(f"  {mark} {schema}.{name}")
                if name not in present:
                    missing.append(f"{schema}.{name}")

    if missing:
        print(f"\nFAIL  {len(missing)} table(s) missing: {', '.join(missing)}")
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
