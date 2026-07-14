from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

from src.common.env import config


def _conninfo() -> str:
    """Return a libpq-compatible connection string.

    DATABASE_URL uses the SQLAlchemy-style scheme ``postgresql+psycopg://``;
    libpq/psycopg want a plain ``postgresql://`` DSN. The ``?sslmode=require``
    query string is understood by libpq as-is.
    """
    url = config.DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _clean_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: _safe_json_value(v) for k, v in row.items()} for row in rows]


def run_query(sql: str, params: tuple[Any, ...] | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """Execute a parameterized SELECT and return ``(rows, error)``.

    Always pass user-supplied values via ``params`` (``%s`` placeholders) - never
    interpolate them into the SQL string.
    """
    try:
        with psycopg.connect(_conninfo()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params or ())
                rows = cur.fetchall()
        return _clean_rows(rows), None
    except Exception as exc:
        return [], f"Database read failed: {exc}"
