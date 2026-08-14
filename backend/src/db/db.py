from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.common.env import config

def _database_url() -> str:
    connection_string = config.AZURE_SQL_CONNECTIONSTRING

    if not connection_string:
        raise RuntimeError("AZURE_SQL_CONNECTIONSTRING is not configured")

    # AZURE_SQL_CONNECTIONSTRING is written in the ADO.NET/mssql_python shape
    # (Server=...;Database=...;UID=...;PWD=...), which has no Driver= key.
    # pyodbc requires one to pick an installed ODBC driver.
    if "driver=" not in connection_string.lower():
        connection_string = connection_string.rstrip("; ") + ";Driver={ODBC Driver 18 for SQL Server}"

    return "mssql+pyodbc:///?odbc_connect=" + quote_plus(connection_string)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # pool_recycle drops connections that are old enough for the server to
    # have closed them, without a per-checkout probe round trip.
    return create_engine(
        _database_url(),
        pool_recycle=900,
        pool_size=10,
        max_overflow=10,
        pool_timeout=15,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        expire_on_commit=False,
    )


@contextmanager
def session_scope() -> Iterator[Session]:
    with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


def get_db_session() -> Generator[Session, None, None]:
    with session_scope() as session:
        yield session


__all__ = [
    "get_db_session",
    "get_engine",
    "get_session_factory",
    "session_scope",
]