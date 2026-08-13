"""PostgreSQL-only connection helper for the AI-Video runtime DB."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extensions import connection as PsycopgConnection
from psycopg2.extras import DictCursor

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - python-dotenv is a runtime dependency.
    load_dotenv = None

_PROJECT_ROOT = Path(__file__).parent.parent
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_ENV_LOADED = False


class PostgresRuntimeConnection:
    """Small compatibility wrapper exposing conn.execute(...).fetchone()."""

    def __init__(self, conn: PsycopgConnection):
        self._conn = conn

    def execute(self, query: str, params: Any | None = None):
        cur = self._conn.cursor(cursor_factory=DictCursor)
        cur.execute(query, params)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def cursor(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("cursor_factory", DictCursor)
        return self._conn.cursor(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if load_dotenv is not None:
        load_dotenv(_PROJECT_ROOT / ".env", override=False)
    _ENV_LOADED = True


def get_database_url() -> str:
    """Return the configured PostgreSQL URL or fail without fallback."""
    _load_env()
    backend = os.environ.get("AIVIDEO_DB_BACKEND", "postgresql").strip().lower()
    if backend not in {"postgresql", "postgres"}:
        raise RuntimeError("AIVIDEO_DB_BACKEND must be 'postgresql'; SQLite fallback is not supported")

    database_url = os.environ.get("AIVIDEO_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("AIVIDEO_DATABASE_URL or DATABASE_URL is required for PostgreSQL runtime")
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Configured database URL must use the PostgreSQL scheme")
    return database_url


def get_connection(database_url: str | None = None) -> PostgresRuntimeConnection:
    """Return a PostgreSQL runtime connection.

    The runtime intentionally has no SQLite path or fallback. Missing PostgreSQL
    configuration raises immediately so API/worker processes do not start on a
    split-brain local database.
    """
    raw = psycopg2.connect(database_url or get_database_url())
    raw.autocommit = False
    return PostgresRuntimeConnection(raw)


def init_db(database_url: str | None = None) -> None:
    """Create or update the PostgreSQL schema from db/schema.sql."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection(database_url)
    try:
        conn.execute(schema_sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
