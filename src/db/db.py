from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.common.env import config


def _database_url() -> str:
    url = config.DATABASE_URL

    if not url:
        raise RuntimeError("DATABASE_URL is not configured")

    if url.startswith("postgres://"):
        return url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )

    if url.startswith("postgresql://"):
        return url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        _database_url(),
        pool_pre_ping=True,
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