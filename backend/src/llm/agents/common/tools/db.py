"""Shared read-only database primitives for agent data tools."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.db.db import get_engine


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _row(row: Any) -> dict[str, Any]:
    return {
        str(key): _json_value(value)
        for key, value in row.items()
    }


def _rows(
    connection: Connection,
    statement: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    result = connection.execute(
        text(statement),
        parameters,
    ).mappings()
    return [_row(row) for row in result]


def _latest_batch_id(
    connection: Connection,
    agent_name: str,
) -> int:
    import_batch_id = connection.execute(
        text(
            """
            SELECT id
            FROM audit.import_batches
            WHERE agent_name = :agent_name
              AND import_status = 'COMPLETED'
            ORDER BY imported_at DESC
            LIMIT 1
            """
        ),
        {"agent_name": agent_name},
    ).scalar_one_or_none()
    if import_batch_id is None:
        raise RuntimeError(
            f"No completed database import exists for {agent_name}."
        )
    return int(import_batch_id)


def latest_import_batch_id(agent_name: str) -> int:
    """Return the newest completed import batch id for an importer agent."""

    with _read_connection() as connection:
        return _latest_batch_id(connection, agent_name)


@contextmanager
def _read_connection() -> Iterator[Connection]:
    with get_engine().connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        yield connection


__all__ = [
    "_json_value",
    "_row",
    "_rows",
    "_latest_batch_id",
    "latest_import_batch_id",
    "_read_connection",
]
