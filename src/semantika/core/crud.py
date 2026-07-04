"""CRUD service base class for Semantika.

Simplified fork of A-core's ``A.core.service.CRUDService``.
Supports FTS5, soft-delete, and JSON field serialisation.
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Callable

from semantika.core.db import SemantikaDB


def now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def now_ts() -> str:
    """Alias for now()."""
    return now()


class CRUDService:
    """CRUD operations with auto-timestamps (created_at, updated_at).

    Supports:
    - Auto-generated UUID primary keys (override by passing ``uuid`` in data)
    - ``created_at`` / ``updated_at`` timestamp management
    - Soft-delete via ``_trash_table`` (subclass must set)
    - ``_post_create`` / ``_post_update`` / ``_post_delete`` hooks
    - ``list()`` with ordering, limit, offset
    - ``search()`` via LIKE on any column
    """

    def __init__(
        self,
        db: SemantikaDB,
        table: str,
        trash_table: str | None = None,
        pk_column: str = "uuid",
    ):
        self.db = db
        self.table = table
        self._trash_table = trash_table
        self._pk_column = pk_column

    # ── Hooks (override in subclass) ────────────────────────────────────

    def _post_create(self, data: dict[str, Any], result: dict[str, Any]) -> None:
        """Called after successful create."""

    def _post_update(
        self, pk: str, old_data: dict[str, Any] | None, new_data: dict[str, Any]
    ) -> None:
        """Called after successful update."""

    def _post_delete(self, pk: str, data: dict[str, Any] | None) -> None:
        """Called after successful delete."""

    def _move_to_trash(self, pk: str) -> None:
        """Move entry to trash table. Override in subclass for custom PK."""

    # ── List / Get ──────────────────────────────────────────────────────

    def list(
        self,
        order_by: str | None = None,
        desc: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List entries, optionally ordered and limited."""
        if order_by is None:
            order_by = self._pk_column
        direction = "DESC" if desc else "ASC"
        return self.db.execute(
            f"SELECT * FROM {self.table} ORDER BY {order_by} {direction} LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get(self, pk: str) -> dict[str, Any] | None:
        """Get a single entry by primary key."""
        return self.db.execute_one(
            f"SELECT * FROM {self.table} WHERE {self._pk_column} = ? COLLATE NOCASE",
            (pk,),
        )

    def count(self) -> int:
        """Return the number of entries in the table."""
        row = self.db.execute_one(f"SELECT COUNT(*) AS cnt FROM {self.table}")
        return row["cnt"] if row else 0

    # ── Create / Update / Delete ────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new entry with auto-generated UUID and timestamps."""
        ts = now()
        data.setdefault("uuid", str(_uuid.uuid4()))
        data.setdefault("created_at", ts)
        data["updated_at"] = ts

        columns = list(data.keys())
        values = [data[k] for k in columns]
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(sql, values)

        result = data.copy()
        self._post_create(data, result)
        return result

    def update(self, pk: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an entry, preserving creation timestamp."""
        old_data = self.get(pk)
        data["updated_at"] = now()

        set_clauses = [f"{k} = ?" for k in data.keys()]
        values = [data[k] for k in data.keys()] + [pk]
        sql = f"UPDATE {self.table} SET {', '.join(set_clauses)} WHERE {self._pk_column} = ?"

        with self.db.transaction() as conn:
            conn.execute(sql, values)

        self._post_update(pk, old_data, data)
        return {**(old_data or {}), **data}

    def delete(self, pk: str, soft: bool = True) -> bool:
        """Delete an entry.

        Args:
            pk: Primary key value.
            soft: If True, move to trash table. If False, permanent delete.

        Returns:
            True if an entry was deleted.
        """
        old_data = self.get(pk)
        if not old_data:
            return False

        if soft and self._trash_table:
            self._move_to_trash(pk)
        else:
            sql = f"DELETE FROM {self.table} WHERE {self._pk_column} = ?"
            with self.db.transaction() as conn:
                conn.execute(sql, (pk,))

        self._post_delete(pk, old_data)
        return True

    # ── Trash management ────────────────────────────────────────────────

    def list_trash(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List soft-deleted entries."""
        if not self._trash_table:
            return []
        return self.db.execute(
            f"SELECT * FROM {self._trash_table} ORDER BY deleted_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def restore_from_trash(self, pk: str) -> dict[str, Any] | None:
        """Restore a soft-deleted entry.

        Returns the restored entry, or None if not found in trash.
        """
        if not self._trash_table:
            return None
        entry = self.db.execute_one(
            f"SELECT * FROM {self._trash_table} WHERE {self._pk_column} = ?",
            (pk,),
        )
        if not entry:
            return None
        restored = dict(entry)
        restored.pop("deleted_at", None)

        with self.db.transaction() as conn:
            conn.execute(
                f"DELETE FROM {self._trash_table} WHERE {self._pk_column} = ?",
                (pk,),
            )
            columns = list(restored.keys())
            values = [restored[k] for k in columns]
            placeholders = ", ".join(["?"] * len(columns))
            conn.execute(
                f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )

        return restored

    # ── Search ──────────────────────────────────────────────────────────

    def search(
        self, field: str, query: str, case_sensitive: bool = False, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Search entries by field containing a substring (LIKE)."""
        if case_sensitive:
            sql = f"SELECT * FROM {self.table} WHERE {field} LIKE ? LIMIT ?"
        else:
            sql = f"SELECT * FROM {self.table} WHERE LOWER({field}) LIKE LOWER(?) COLLATE NOCASE LIMIT ?"
        return self.db.execute(sql, (f"%{query}%", limit))
