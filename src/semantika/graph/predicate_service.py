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
from semantika.graph.constants import FTS5_KEYWORDS
from semantika.graph.node_helpers import extract_label_text

logger = logging.getLogger(__name__)


class PredicateService(CRUDService):
    """Service for managing predicates (semantic properties)."""

    def __init__(self, db: SemantikaDB) -> None:
        super().__init__(db=db, table="predicates", pk_column="predicate_id")

    # ── Delete ─────────────────────────────────────────────────────────

    def delete(self, pk: str, soft: bool = True) -> bool:
        """Delete a predicate.

        Predicates do not have a trash table — the *soft* parameter is
        accepted for interface compatibility but always performs a
        permanent delete. Use ``soft=False`` explicitly to avoid confusion.
        """
        if soft:
            logger.warning(
                "Predicate delete called with soft=True — no trash table exists, "
                "performing permanent delete of %s",
                pk,
            )
        return super().delete(pk, soft=False)

    # ── FTS5 Management ──────────────────────────────────────────────

    def _ensure_fts(self) -> bool:
        """Ensure predicates_fts exists and is populated. Returns True if usable."""
        vt = self.db.execute_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='predicates_fts'"
        )
        if not vt:
            try:
                self.db.execute(
                    "CREATE VIRTUAL TABLE predicates_fts USING fts5("
                    "  predicate_id UNINDEXED, labels, descriptions, aliases,"
                    "  content=predicates, content_rowid=rowid, tokenize='unicode61'"
                    ")"
                )
            except sqlite3.DatabaseError:
                return False

        count = self.db.execute_one("SELECT COUNT(*) AS cnt FROM predicates_fts")
        if count and count["cnt"] == 0:
            self._populate_fts()
        return True

    def _populate_fts(self) -> None:
        """Populate predicates_fts from content table."""
        try:
            self.db.execute(
                "INSERT INTO predicates_fts (rowid, predicate_id, labels, descriptions, aliases)"
                " SELECT rowid, predicate_id, labels, descriptions, aliases FROM predicates"
            )
        except sqlite3.DatabaseError:
            logger.warning("Predicate FTS population failed — LIKE fallback will work")

    def _rebuild_fts(self) -> None:
        """Rebuild the predicates FTS index from all content."""
        try:
            self.db.execute(
                "INSERT INTO predicates_fts(predicates_fts) VALUES('rebuild')"
            )
        except sqlite3.DatabaseError:
            self.db.execute("DROP TABLE IF EXISTS predicates_fts")
            self._ensure_fts()

    def _index_fts(self, predicate_id: str) -> None:
        """Index a single predicate in FTS5."""
        entry = self.db.execute_one(
            "SELECT rowid, predicate_id, labels, descriptions, aliases"
            " FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not entry:
            return
        try:
            self.db.execute(
                "INSERT INTO predicates_fts(rowid, predicate_id, labels, descriptions, aliases)"
                " VALUES(?, ?, ?, ?, ?)",
                (entry["rowid"], predicate_id,
                 entry.get("labels", ""), entry.get("descriptions", ""),
                 entry.get("aliases", "")),
            )
        except sqlite3.DatabaseError:
            pass

    def _remove_from_fts(self, predicate_id: str) -> bool:
        """Remove a predicate from FTS index using FTS5 'delete' command."""
        row = self.db.execute_one(
            "SELECT rowid FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not row or row.get("rowid") is None:
            return False
        return self._remove_fts_by_rowid(predicate_id, row["rowid"])

    def _remove_fts_by_rowid(self, predicate_id: str, rowid: int) -> bool:
        """Remove a rowid from the predicates FTS index."""
        try:
            self.db.execute(
                "INSERT INTO predicates_fts(predicates_fts, rowid) VALUES('delete', ?)",
                (rowid,),
            )
            return True
        except sqlite3.DatabaseError as exc:
            logger.warning("FTS 'delete' failed for %s (rowid=%s): %s", predicate_id, rowid, exc)
            self._rebuild_fts()
            return False

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitize a user query string for FTS5 MATCH."""
        if not query or "_" in query or "%" in query:
            return ""
        safe_tokens = []
        for word in query.strip().split():
            cleaned = "".join(c for c in word if c.isalnum())
            if not cleaned:
                continue
            if cleaned.upper() in FTS5_KEYWORDS:
                cleaned = cleaned.lower()
            safe_tokens.append(f"{cleaned}*")
        if not safe_tokens:
            return ""
        return " OR ".join(safe_tokens)

    # ── Create / Update / Search with FTS5 support ────────────────────

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
        self._index_fts(raw["predicate_id"])
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
            removed = self._remove_from_fts(predicate_id)
            conn.execute(sql, params)
            if removed:
                self._index_fts(predicate_id)

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

        # Remove old FTS entry BEFORE transaction (uses own DB connection)
        self._remove_from_fts(old_id)

        # Set defer_foreign_keys before the transaction starts
        self.db.execute("PRAGMA defer_foreign_keys=ON")
        with self.db.transaction() as conn:
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

        # Re-index FTS after the transaction completes
        self._index_fts(new_id)

        return self.get(new_id)

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Search predicates using FTS5, falling back to LIKE.

        Uses FTS5 on labels/descriptions/aliases first for relevance-ranked
        results, then falls back to LIKE on all text fields for edge cases.
        """
        if not query or not query.strip():
            return self.list(limit=limit)

        # Try FTS5 first
        fts_ok = self._ensure_fts()
        fts_query = self._sanitize_fts_query(query) if fts_ok else ""
        if fts_query:
            fts_sql = """
                SELECT p.*, bm25(predicates_fts, 1.2, 0.75, 0.0, -5.0, -1.0, -0.5) AS _rank
                FROM predicates p
                JOIN predicates_fts f ON p.rowid = f.rowid
                WHERE predicates_fts MATCH ?
                ORDER BY _rank
                LIMIT ?
            """
            try:
                results = self.db.execute(fts_sql, (fts_query, limit))
            except sqlite3.DatabaseError:
                logger.warning("Predicate FTS search failed — rebuilding and retrying")
                try:
                    self._rebuild_fts()
                    results = self.db.execute(fts_sql, (fts_query, limit))
                except sqlite3.DatabaseError:
                    results = []
            if results:
                return results

        # Fallback: LIKE on predicate_id and JSON text fields
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return self.db.execute(
            "SELECT *, 0 AS _rank FROM predicates WHERE "
            "predicate_id LIKE ? COLLATE NOCASE OR "
            "labels LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "descriptions LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "aliases LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "LIMIT ?",
            (f"%{escaped}%", f"%{escaped}%", f"%{escaped}%", f"%{escaped}%", limit),
        )
