"""SQLite database wrapper with WAL mode and per-thread connection caching.

Vendored from A-core's ``A.data.base.SQLiteDB``.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any


class SemantikaDB:
    """SQLite database with WAL mode and thread-safe per-thread connections.

    Connections are cached per-thread via ``threading.local``.
    Each thread gets its own ``sqlite3.Connection``, avoiding the
    ``ProgrammingError: SQLite objects created in a thread can only be
    used in that same thread`` error.

    Within a single thread, the connection is lazily created on first use
    and reused for subsequent queries.

    Call :meth:`close()` to release the calling thread's cached connection.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def close(self) -> None:
        """Checkpoint WAL and close the calling thread's connection."""
        conn = getattr(self._local, "_conn", None)
        if conn is not None:
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            self._local._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a per-thread cached connection with WAL mode."""
        conn = getattr(self._local, "_conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA wal_autocheckpoint=100")
            conn.row_factory = sqlite3.Row
            self._local._conn = conn
        return conn

    def execute(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute SQL and return results as dicts. Auto-commits."""
        conn = self._get_conn()
        cursor = conn.execute(sql, params or ())
        rows = cursor.fetchall()
        conn.commit()
        return [dict(r) for r in rows]

    def execute_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Execute SQL and return first result, or None."""
        results = self.execute(sql, params)
        return results[0] if results else None

    def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute SQL with multiple parameter sets."""
        conn = self._get_conn()
        conn.executemany(sql, params_list)
        conn.commit()

    def transaction(self):
        """Context manager yielding a connection with auto-commit/rollback."""

        class _TransactionContext:
            def __init__(self, db: SemantikaDB):
                self.db = db

            def __enter__(self):
                return self.db._get_conn()

            def __exit__(self, exc_type, exc_val, exc_tb):
                conn = self.db._get_conn()
                if exc_type is None:
                    conn.commit()
                else:
                    conn.rollback()

        return _TransactionContext(self)

    def init_schema(self, schema: dict[str, str]) -> None:
        """Initialize database tables from a schema dict.

        Args:
            schema: Mapping of table_name → CREATE TABLE SQL.
                Tables that already exist are skipped.
        """
        conn = self._get_conn()
        for table, sql in schema.items():
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if cursor.fetchone() is None:
                conn.executescript(sql)
        conn.commit()

    def get_pragma_table_info(self, table: str) -> list[dict[str, Any]]:
        """Return PRAGMA table_info for a table."""
        return self.execute(f"PRAGMA table_info({table})")

    def table_exists(self, name: str) -> bool:
        """Check if a table exists in the database."""
        return self.execute_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ) is not None

    def backup(self, dest_path: str | Path) -> None:
        """Backup the database to *dest_path* using SQLite's backup API."""
        dest = sqlite3.connect(str(dest_path))
        try:
            conn = self._get_conn()
            conn.backup(dest)
        finally:
            dest.close()
