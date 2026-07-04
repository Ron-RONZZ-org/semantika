"""PredicateService — predicate management for the knowledge graph.

Ported from A-semantika's ``_predicate_service.py`` with EO→EN migration.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from semantika.core import SemantikaDB
from semantika.core.crud import CRUDService, now
from semantika.graph.node_helpers import extract_label_text

logger = logging.getLogger(__name__)


class PredicateService(CRUDService):
    """Service for managing predicates (semantic properties)."""

    def __init__(self, db: SemantikaDB) -> None:
        super().__init__(db=db, table="predicates", pk_column="predicate_id")

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a predicate with JSON-serialized dict fields."""
        ts = now()
        raw = {
            "predicate_id": data["predicate_id"],
            "source": data.get("source", "manual"),
            "labels": json.dumps(data.get("labels", {})),
            "descriptions": json.dumps(data.get("descriptions", {})),
            "aliases": json.dumps(data.get("aliases", [])),
            "created_at": ts,
            "updated_at": ts,
        }
        try:
            self.db.execute(
                "INSERT INTO predicates (predicate_id, source, labels, descriptions, "
                "aliases, created_at, updated_at) "
                "VALUES (:predicate_id, :source, :labels, :descriptions, "
                ":aliases, :created_at, :updated_at)",
                raw,
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"Predicate '{data['predicate_id']}' already exists."
            ) from e
        return dict(raw)

    def update(self, predicate_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a predicate, merging labels/descriptions by default."""
        old = self.get(predicate_id)
        if not old:
            raise ValueError(f"Predicate not found: {predicate_id}")

        updates = dict(data)
        ts = now()

        if "labels" in updates and isinstance(updates["labels"], dict):
            # Merge with existing
            try:
                existing_labels = json.loads(old["labels"]) if isinstance(old["labels"], str) else old["labels"]
            except (json.JSONDecodeError, TypeError):
                existing_labels = {}
            merged = {**existing_labels, **updates["labels"]}  # new values win
            updates["labels"] = json.dumps(merged)

        if "descriptions" in updates and isinstance(updates["descriptions"], dict):
            try:
                existing_descs = json.loads(old["descriptions"]) if isinstance(old["descriptions"], str) else old["descriptions"]
            except (json.JSONDecodeError, TypeError):
                existing_descs = {}
            merged = {**existing_descs, **updates["descriptions"]}
            updates["descriptions"] = json.dumps(merged)

        updates["updated_at"] = ts

        set_parts = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [predicate_id]
        sql = f"UPDATE predicates SET {', '.join(set_parts)} WHERE predicate_id = ?"

        with self.db.transaction() as conn:
            conn.execute(sql, params)

        return self.get(predicate_id)

    def resolve_predicate_id_prefix(self, prefix: str) -> dict | None:
        """Resolve a predicate ID prefix to a full predicate dict.

        Tries exact match first, then LIKE prefix search.
        Returns None if no match or ambiguous.
        """
        if not prefix:
            return None

        # Exact match
        pred = self.get(prefix)
        if pred:
            return pred

        # Prefix match via LIKE
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matches = self.db.execute(
            "SELECT * FROM predicates WHERE predicate_id LIKE ? COLLATE NOCASE ESCAPE '\\'",
            (f"{escaped}%",),
        )
        if len(matches) == 1:
            return matches[0]
        return None

    def update_predicate_id(self, old_id: str, new_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rename a predicate's predicate_id, cascading to all references.

        Args:
            old_id: Current predicate_id.
            new_id: New predicate_id.
            data: Optional additional field updates.

        Returns:
            Updated predicate dict.

        Raises:
            ValueError: If old_id not found, new_id already exists, or
                PK/UNIQUE collision would occur.
        """
        old = self.get(old_id)
        if not old:
            raise ValueError(f"Predicate not found: {old_id}")

        existing = self.db.execute_one(
            "SELECT predicate_id FROM predicates WHERE predicate_id = ?", (new_id,)
        )
        if existing:
            raise ValueError(f"New predicate ID '{new_id}' already exists")

        # Check triple PK collision
        old_triples = self.db.execute(
            "SELECT subject_id, object_value, object_type FROM triples "
            "WHERE predicate_id = ?", (old_id,),
        )
        for t in old_triples:
            coll = self.db.execute_one(
                "SELECT 1 FROM triples WHERE subject_id = ? AND predicate_id = ? "
                "AND object_value = ? AND object_type = ?",
                (t["subject_id"], new_id, t["object_value"], t["object_type"]),
            )
            if coll:
                raise ValueError(
                    f"Rename would cause triple PK collision: "
                    f"({t['subject_id']}, {new_id}, {t['object_value']})"
                )

        # Check predicate group member collision
        old_members = self.db.execute(
            "SELECT group_uuid FROM predicate_group_members WHERE predicate_id = ?",
            (old_id,),
        )
        for m in old_members:
            coll = self.db.execute_one(
                "SELECT 1 FROM predicate_group_members WHERE group_uuid = ? AND predicate_id = ?",
                (m["group_uuid"], new_id),
            )
            if coll:
                raise ValueError(
                    f"Rename would cause predicate group member collision: "
                    f"group ({m['group_uuid']}, {new_id}) already exists"
                )

        updates = dict(data or {})
        ts = now()

        if "labels" in updates and isinstance(updates["labels"], dict):
            updates["labels"] = json.dumps(updates["labels"])
        if "descriptions" in updates and isinstance(updates["descriptions"], dict):
            updates["descriptions"] = json.dumps(updates["descriptions"])

        updates["predicate_id"] = new_id
        updates["updated_at"] = ts

        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            set_parts = [f"{k} = ?" for k in updates]
            params = list(updates.values()) + [old_id]
            conn.execute(
                f"UPDATE predicates SET {', '.join(set_parts)} WHERE predicate_id = ?",
                params,
            )

            # Cascade to triples
            conn.execute(
                "UPDATE triples SET predicate_id = ? WHERE predicate_id = ?",
                (new_id, old_id),
            )

            # Cascade to predicate_group_members
            conn.execute(
                "UPDATE predicate_group_members SET predicate_id = ? WHERE predicate_id = ?",
                (new_id, old_id),
            )

        return self.get(new_id)

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Search predicates by ID, labels, descriptions, or aliases."""
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return self.db.execute(
            "SELECT * FROM predicates WHERE "
            "predicate_id LIKE ? COLLATE NOCASE OR "
            "labels LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "descriptions LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "aliases LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "LIMIT ?",
            (f"%{escaped}%", f"%{escaped}%", f"%{escaped}%", f"%{escaped}%", limit),
        )
