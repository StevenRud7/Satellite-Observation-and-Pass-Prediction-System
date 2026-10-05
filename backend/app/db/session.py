"""
SQLAlchemy engine and session management.

The engine is created lazily (on first use, via `get_engine()`) rather
than at import time, for two reasons: importing this module must not fail
just because `DATABASE_URL` isn't set yet (e.g. in Phase-0/1-style tests
that don't touch the database at all), and creating the engine eagerly at
module import time makes it awkward to reconfigure for tests.

`get_db_session()` is the FastAPI dependency: it yields one Session per
request and always closes it, committing on success and rolling back on
exception. `session_scope()` is the equivalent for use outside a FastAPI
request (scripts, the ranking service, tests).
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Generator, Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


class DatabaseNotConfiguredError(Exception):
    """Raised when database access is attempted but DATABASE_URL isn't set."""


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if not settings.database_url:
        raise DatabaseNotConfiguredError(
            "DATABASE_URL is not set. Set it in the environment (see .env.example) "
            "to use any database-backed feature."
        )
    # pool_pre_ping avoids handing out dead connections after a database
    # goes idle and closes them - relevant for free-tier Postgres hosts
    # (e.g. Neon) that can suspend/reset idle connections.
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency: one Session per request."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context-managed Session for use outside FastAPI's dependency injection."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_cache() -> None:
    """Clear cached engine/session factory - used by tests that reconfigure
    DATABASE_URL between test cases."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
