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
            merged = {**updates["labels"], **existing_labels}  # new values win
            updates["labels"] = json.dumps(merged)

        if "descriptions" in updates and isinstance(updates["descriptions"], dict):
            try:
                existing_descs = json.loads(old["descriptions"]) if isinstance(old["descriptions"], str) else old["descriptions"]
            except (json.JSONDecodeError, TypeError):
                existing_descs = {}
            merged = {**updates["descriptions"], **existing_descs}
            updates["descriptions"] = json.dumps(merged)

        updates["updated_at"] = ts

        set_parts = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [predicate_id]
        sql = f"UPDATE predicates SET {', '.join(set_parts)} WHERE predicate_id = ?"

        with self.db.transaction() as conn:
            conn.execute(sql, params)

        return self.get(predicate_id)

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
