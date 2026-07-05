"""PredicateGroupService — logical collections of predicates.

Ported from A-semantika's ``_predicate_group_service.py``.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid as _uuid
from typing import Any

from semantika.core import SemantikaDB
from semantika.core.crud import CRUDService, now

logger = logging.getLogger(__name__)


class PredicateGroupService(CRUDService):
    """Service for managing predicate groups (logical collections of predicates)."""

    def __init__(self, db: SemantikaDB) -> None:
        super().__init__(db=db, table="predicate_groups")

    def delete(self, pk: str, soft: bool = True) -> bool:
        """Delete a predicate group.

        Predicate groups do not have a trash table — the *soft* parameter
        is accepted for interface compatibility but always performs a
        permanent delete.
        """
        if soft:
            logger.warning(
                "PredicateGroup delete called with soft=True — no trash table exists, "
                "performing permanent delete of %s",
                pk,
            )
        return super().delete(pk, soft=False)

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new predicate group."""
        ts = now()
        raw = {
            "uuid": str(_uuid.uuid4()),
            "group_name": data["group_name"],
            "created_at": ts,
            "updated_at": ts,
        }
        try:
            self.db.execute(
                "INSERT INTO predicate_groups (uuid, group_name, created_at, updated_at) "
                "VALUES (:uuid, :group_name, :created_at, :updated_at)",
                raw,
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"Group '{data['group_name']}' already exists."
            ) from e
        return dict(raw)

    def add_member(self, group_uuid: str, predicate_id: str) -> dict:
        """Add a predicate to a group."""
        row = {
            "uuid": str(_uuid.uuid4()),
            "group_uuid": group_uuid,
            "predicate_id": predicate_id,
            "created_at": now(),
        }
        try:
            self.db.execute(
                "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, created_at) "
                "VALUES (:uuid, :group_uuid, :predicate_id, :created_at)",
                row,
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"Predicate '{predicate_id}' already in group."
            ) from e
        return dict(row)

    def remove_member(self, group_uuid: str, predicate_id: str) -> bool:
        """Remove a predicate from a group."""
        cursor = self.db.execute(
            "DELETE FROM predicate_group_members WHERE group_uuid = ? AND predicate_id = ?",
            (group_uuid, predicate_id),
        )
        return len(cursor) > 0

    def list_members(self, group_uuid: str) -> list[dict]:
        """List all predicates in a group."""
        return self.db.execute(
            "SELECT p.* FROM predicates p "
            "JOIN predicate_group_members m ON p.predicate_id = m.predicate_id "
            "WHERE m.group_uuid = ? ORDER BY m.predicate_id",
            (group_uuid,),
        )

    def resolve_group_name(self, name: str) -> dict | None:
        """Resolve a group by name (exact or prefix)."""
        group = self.db.execute_one(
            "SELECT * FROM predicate_groups WHERE group_name = ? COLLATE NOCASE",
            (name,),
        )
        if group:
            return group
        escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return self.db.execute_one(
            "SELECT * FROM predicate_groups WHERE group_name LIKE ? COLLATE NOCASE ESCAPE '\\'",
            (f"{escaped}%",),
        )
