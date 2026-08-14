"""Shared read-only database primitives for agent data tools."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
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
    *,
    expand: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Run `statement`. Pass `expand` to bind list-valued params as `IN (...)`."""
    compiled = text(statement)
    if expand:
        compiled = compiled.bindparams(
            *(bindparam(name, expanding=True) for name in expand)
        )
    result = connection.execute(
        compiled,
        parameters,
    ).mappings()
    return [_row(row) for row in result]


def _legal_entities(connection: Connection) -> list[dict[str, Any]]:
    """The three legal entities every fact table in `newdata` can be sliced
    by, for the entity dropdown every agent's dashboard payload carries.

    Read live rather than hardcoded: `dim_legal_entity` is dimension data, and
    a fourth entity added to the dataset later should not need a matching
    code change here to appear in the dropdown.
    """
    return _rows(
        connection,
        """
        SELECT legal_entity_id, legal_entity_name, country
        FROM newdata.dim_legal_entity
        ORDER BY legal_entity_id
        """,
        {},
    )


def _available_months(
    connection: Connection,
    table: str,
    window_clause: str,
    window_params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Distinct months a table's window covers, as `{month_key, month_label}`
    pairs for a Period dropdown.

    `month_key` is the table's own `month` date, ISO-formatted ("2026-03-01")
    — the same column every fact table's window clause already filters on, so
    a caller narrowing to one of these values needs no new column and a month
    can never appear in the dropdown with no data behind it.

    `table` is interpolated, never a bound parameter — SQL does not allow
    binding an identifier — so this must only ever be called with a literal
    table name from source, never a value that reached this process from an
    HTTP request.
    """
    rows = connection.execute(
        text(
            f"""
            SELECT DISTINCT month
            FROM newdata.{table}
            WHERE {window_clause}
            ORDER BY month
            """
        ),
        window_params,
    ).mappings().all()
    return [
        {
            "month_key": row["month"].isoformat(),
            "month_label": row["month"].strftime("%B %Y"),
        }
        for row in rows
    ]


def _latest_batch_id(
    connection: Connection,
    agent_name: str,
) -> int:
    import_batch_id = connection.execute(
        text(
            """
            SELECT TOP (1) id
            FROM audit.import_batches
            WHERE agent_name = :agent_name
              AND import_status = 'COMPLETED'
            ORDER BY imported_at DESC
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
    # No T-SQL equivalent of Postgres's "SET TRANSACTION READ ONLY" exists
    # for an ad hoc session against Azure SQL, so this is enforced by
    # convention (only SELECTs are issued through this helper) rather than
    # by the database.
    with get_engine().connect() as connection:
        yield connection


__all__ = [
    "_json_value",
    "_row",
    "_rows",
    "_legal_entities",
    "_available_months",
    "_latest_batch_id",
    "latest_import_batch_id",
    "_read_connection",
]
