from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

from src.common.env import config


def _conninfo() -> str:
    """
    Return a libpq-compatible PostgreSQL connection string.
    """

    url = config.DATABASE_URL

    if not url:
        raise RuntimeError("DATABASE_URL is not configured")

    return url.replace(
        "postgresql+psycopg://",
        "postgresql://",
        1,
    )


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    return value


def _clean_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            key: _safe_json_value(value)
            for key, value in row.items()
        }
        for row in rows
    ]


def run_query(
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Execute a parameterized SELECT query.

    Returns:
        tuple containing rows and error message.
    """

    try:
        with psycopg.connect(_conninfo()) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, params or ())
                rows = cursor.fetchall()

        return _clean_rows(rows), None

    except Exception as error:
        return [], f"Database read failed: {error}"


def execute_statement(
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> tuple[int, str | None]:
    """
    Execute one INSERT, UPDATE, or DELETE statement.

    Returns:
        tuple containing affected row count and error message.
    """

    try:
        with psycopg.connect(_conninfo()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params or ())
                affected_rows = cursor.rowcount

            connection.commit()

        return affected_rows, None

    except Exception as error:
        return 0, f"Database write failed: {error}"


def execute_returning(
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Execute an INSERT or UPDATE statement with RETURNING.

    Returns:
        tuple containing one returned row and error message.
    """

    try:
        with psycopg.connect(_conninfo()) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql, params or ())
                row = cursor.fetchone()

            connection.commit()

        if row is None:
            return None, None

        cleaned_row = {
            key: _safe_json_value(value)
            for key, value in row.items()
        }

        return cleaned_row, None

    except Exception as error:
        return None, f"Database write failed: {error}"


def execute_many(
    sql: str,
    params_list: list[tuple[Any, ...]],
) -> tuple[int, str | None]:
    """
    Execute the same INSERT or UPDATE statement for multiple rows.

    All rows are processed inside one transaction.
    """

    if not params_list:
        return 0, None

    try:
        with psycopg.connect(_conninfo()) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(sql, params_list)
                affected_rows = cursor.rowcount

            connection.commit()

        return affected_rows, None

    except Exception as error:
        return 0, f"Database bulk write failed: {error}"