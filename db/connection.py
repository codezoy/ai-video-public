"""PostgreSQL connection helper for AI-Video DB.

The runtime DB is PostgreSQL only. Configure it with AIVIDEO_DATABASE_URL
or DATABASE_URL; SQLite path fallback is intentionally unsupported.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import connection as PgConnection, cursor as PgCursor, new_type, register_type
from psycopg2.extras import DictCursor

_PROJECT_ROOT = Path(__file__).parent.parent
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

load_dotenv(_PROJECT_ROOT / ".env")


class PostgresConnection:
    """Small compatibility wrapper exposing conn.execute(...)."""

    def __init__(self, conn: PgConnection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: object | None = None) -> PgCursor:
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def cursor(self) -> PgCursor:
        return self._conn.cursor()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._conn, name)


def get_database_url() -> str:
    """Return the configured PostgreSQL URL or fail loudly."""
    database_url = os.environ.get("AIVIDEO_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "PostgreSQL database URL is required. Set AIVIDEO_DATABASE_URL or DATABASE_URL."
        )

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError(
            "AI-Video runtime DB only supports PostgreSQL URLs via AIVIDEO_DATABASE_URL or DATABASE_URL."
        )
    return database_url


def get_connection() -> PostgresConnection:
    """Return a PostgreSQL connection using dict-capable rows."""
    conn = psycopg2.connect(get_database_url(), cursor_factory=DictCursor)
    timestamp_as_text = new_type((1114, 1184), "TIMESTAMP_AS_TEXT", lambda value, _cursor: value)
    register_type(timestamp_as_text, conn)
    conn.autocommit = False
    return PostgresConnection(conn)


def init_db() -> None:
    """Create or update PostgreSQL tables using additive schema SQL."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
