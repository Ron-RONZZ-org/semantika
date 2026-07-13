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
from semantika.core.fts import FTS5Manager
from semantika.graph.constants import FTS5_KEYWORDS
from semantika.graph.db import compute_iri
from semantika.graph.helpers import escape_like
from semantika.graph.node_helpers import sanitize_node_id, strip_diacritics

logger = logging.getLogger(__name__)


class PredicateService(CRUDService):
    """Service for managing predicates (semantic properties)."""

    def __init__(self, db: SemantikaDB) -> None:
        super().__init__(db=db, table="predicates", pk_column="predicate_id",
                         trash_table="predicates_trash")
        self._fts_initialized: bool = False
        self._fts_mgr_cache: FTS5Manager | None = None
        self._sparql_engine: object | None = None

    @property
    def _fts_mgr(self) -> FTS5Manager:
        """Lazy-initialised shared FTS5 manager for predicates."""
        if self._fts_mgr_cache is None:
            self._fts_mgr_cache = FTS5Manager(
                db=self.db,
                fts_table="predicates_fts",
                content_table="predicates",
                pk_column="predicate_id",
                fts_columns=["labels", "descriptions", "aliases"],
            )
        return self._fts_mgr_cache

    # ── Delete / Trash ──────────────────────────────────────────────────

    def _capture_triples_for_predicate(self, predicate_id: str) -> list[dict]:
        """Read triples referencing this predicate before deletion (for SPARQL sync)."""
        if not self._sparql_engine:
            return []
        return self.db.execute(
            "SELECT * FROM triples WHERE predicate_id = ?", (predicate_id,)
        )

    def _sync_removed_triples(self, triples: list[dict]) -> None:
        """Fire SPARQL sync hooks for removed triples."""
        if not self._sparql_engine or not triples:
            return
        engine = self._sparql_engine  # type: ignore[union-attr]
        for t in triples:
            engine.on_triple_removed(t)

    def delete(self, pk: str, soft: bool = True) -> bool:
        """Delete a predicate: soft (trash) or permanent."""
        # SPARQL sync: capture affected triples before deletion
        removed_triples = self._capture_triples_for_predicate(pk)

        if soft and self._trash_table:
            result = self._move_to_trash(pk)
            self._sync_removed_triples(removed_triples)
            return result
        # Hard delete: cascade-delete triples and proofs first
        entry = self.db.execute_one(
            "SELECT predicate_id FROM predicates WHERE predicate_id = ?", (pk,)
        )
        if not entry:
            return False
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM proofs WHERE predicate_id = ?", (entry["predicate_id"],))
            conn.execute("DELETE FROM triples WHERE predicate_id = ?", (entry["predicate_id"],))
            conn.execute("DELETE FROM predicates WHERE predicate_id = ?", (entry["predicate_id"],))
        self._sync_removed_triples(removed_triples)
        return True

    def _move_to_trash(self, predicate_id: str) -> bool:
        """Move predicate to trash, cascading triple deletion."""
        entry = self.db.execute_one(
            "SELECT predicate_id, source, labels, descriptions, aliases, "
            "created_at, updated_at FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not entry:
            return False
        entry["deleted_at"] = now()
        entry.setdefault("updated_at", entry["deleted_at"])
        columns = list(entry.keys())
        values = [entry[k] for k in columns]
        ph = ", ".join(["?"] * len(columns))
        with self.db.transaction() as conn:
            self._remove_from_fts(predicate_id, conn=conn)
            conn.execute("DELETE FROM triples WHERE predicate_id = ?", (predicate_id,))
            # Cascade-delete proofs attached to the deleted triples
            conn.execute("DELETE FROM proofs WHERE predicate_id = ?", (predicate_id,))
            conn.execute(f"INSERT OR REPLACE INTO predicates_trash ({', '.join(columns)}) VALUES ({ph})", values)
            conn.execute("DELETE FROM predicates WHERE predicate_id = ?", (predicate_id,))
        return True

    # ── Trash management ────────────────────────────────────────────────

    def list_trash(self) -> list[dict]:
        """List all trashed predicates."""
        return self.db.execute("SELECT * FROM predicates_trash ORDER BY deleted_at DESC")

    def restore_from_trash(self, predicate_id: str) -> dict | None:
        """Restore a trashed predicate; returns None if not found."""
        entry = self.db.execute_one("SELECT * FROM predicates_trash WHERE predicate_id = ?", (predicate_id,))
        if not entry:
            return None
        restored = dict(entry)
        restored.pop("deleted_at", None)
        with self.db.transaction() as conn:
            self._remove_from_fts(predicate_id, conn=conn)
            conn.execute("DELETE FROM predicates_trash WHERE predicate_id = ?", (predicate_id,))
            restored["updated_at"] = now()
            cols = [c for c in restored if c != "deleted_at"]
            vals = [restored[c] for c in cols]
            ph = ", ".join(["?"] * len(cols))
            conn.execute(f"INSERT OR REPLACE INTO predicates ({', '.join(cols)}) VALUES ({ph})", vals)
            self._index_fts(predicate_id, conn=conn)
        return self.get(predicate_id)

    def empty_trash(self) -> int:
        """Permanently delete all trashed predicates."""
        items = self.db.execute("SELECT COUNT(*) AS cnt FROM predicates_trash")
        count = items[0]["cnt"] if items else 0
        if count > 0:
            self.db.execute("DELETE FROM predicates_trash")
        return count

    # ── FTS5 Management (delegated to FTS5Manager) ────────────────────

    def _ensure_fts(self) -> bool:
        """Ensure predicates_fts exists and is populated. Returns True if usable.

        Uses a boolean flag to avoid repeated SQL queries on every search
        after the FTS table has been confirmed to exist and be populated.
        """
        if self._fts_initialized:
            return True

        vt = self.db.execute_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='predicates_fts'"
        )
        if not vt:
            try:
                self._fts_mgr.ensure()
            except sqlite3.DatabaseError:
                return False
        else:
            # Table exists — populate if empty
            count = self.db.execute_one("SELECT COUNT(*) AS cnt FROM predicates_fts")
            if count and count["cnt"] == 0:
                self._fts_mgr.populate()
        self._fts_initialized = True
        return True

    def _populate_fts(self) -> None:
        """Populate predicates_fts from content table."""
        self._fts_mgr.populate()

    def _rebuild_fts(self) -> None:
        """Rebuild the predicates FTS index from all content."""
        self._fts_mgr.rebuild()

    def _index_fts(self, predicate_id: str,
                   conn: sqlite3.Connection) -> None:
        """Index a single predicate in FTS5.

        Must be called inside a transaction with an active connection.

        Args:
            predicate_id: The predicate ID to index.
            conn: Active database connection (required).
        """
        self._fts_mgr.index(predicate_id, conn=conn)

    def _remove_from_fts(self, predicate_id: str,
                         conn: sqlite3.Connection,
                         rowid: int | None = None) -> bool:
        """Remove a predicate from FTS index.

        Must be called inside a transaction with an active connection.

        Args:
            predicate_id: Predicate to remove from index.
            conn: Active database connection (required).
            rowid: Pre-fetched rowid (avoids a SELECT if known).
        """
        return self._fts_mgr.remove(predicate_id, conn=conn, rowid=rowid)

    def _remove_fts_by_rowid(self, predicate_id: str, rowid: int,
                             conn: sqlite3.Connection) -> bool:
        """Remove a rowid from the predicates FTS index.

        Must be called inside a transaction with an active connection.

        Args:
            predicate_id: Predicate being removed.
            rowid: Rowid of the predicate to remove from FTS.
            conn: Active database connection (required).
        """
        return self._fts_mgr.remove_by_rowid(predicate_id, rowid, conn=conn)

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitize a user query string for FTS5 MATCH."""
        return FTS5Manager.sanitize_query(query)

    # ── Create / Update / Search with FTS5 support ────────────────────

    def create(self, data: dict[str, Any], normalize_ids: bool | None = None) -> dict[str, Any]:
        """Create a predicate with JSON-serialized dict fields.

        Args:
            data: Predicate data dict. Must contain 'predicate_id'.
            normalize_ids: If True, strip diacritics from the predicate_id.
                ``None`` means default sanitization (invisible char removal)
                still applies.
        """
        raw_id = data["predicate_id"]
        cleaned_id = sanitize_node_id(raw_id)
        if normalize_ids:
            cleaned_id = strip_diacritics(cleaned_id)
        ts = now()
        # iri column: empty for template-default, populated for custom --canonical
        canonical_iri = data.get("iri", "")
        raw = {
            "predicate_id": cleaned_id,
            "iri": canonical_iri,
            "source": data.get("source", "manual"),
            "labels": json.dumps(data.get("labels", {})),
            "descriptions": json.dumps(data.get("descriptions", {})),
            "aliases": json.dumps(data.get("aliases", [])),
            "created_at": ts,
            "updated_at": ts,
        }
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO predicates (predicate_id, iri, source, labels, descriptions, "
                    "aliases, created_at, updated_at) "
                    "VALUES (:predicate_id, :iri, :source, :labels, :descriptions, "
                    ":aliases, :created_at, :updated_at)",
                    raw,
                )
                self._index_fts(raw["predicate_id"], conn=conn)
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"Predicate '{cleaned_id}' already exists."
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
        params = [*list(updates.values()), predicate_id]
        sql = f"UPDATE predicates SET {', '.join(set_parts)} WHERE predicate_id = ?"

        with self.db.transaction() as conn:
            removed = self._remove_from_fts(predicate_id, conn=conn)
            conn.execute(sql, params)
            if removed:
                self._index_fts(predicate_id, conn=conn)

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
        escaped = escape_like(prefix)
        matches = self.db.execute(
            "SELECT * FROM predicates WHERE predicate_id LIKE ? COLLATE NOCASE ESCAPE '\\'",
            (f"{escaped}%",),
        )
        if len(matches) == 1:
            return matches[0]
        return None

    def get_by_ids(self, predicate_ids: list[str]) -> list[dict]:
        """Fetch multiple predicates in one query (O(1) vs O(N) loop)."""
        if not predicate_ids:
            return []
        placeholders = ", ".join(["?"] * len(predicate_ids))
        return self.db.execute(
            f"SELECT * FROM predicates WHERE predicate_id IN ({placeholders})",
            tuple(predicate_ids),
        )

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

        # Check triple PK collision (single query instead of N+1 loop)
        triple_coll = self.db.execute_one(
            """SELECT 1 FROM triples t1
               JOIN triples t2 ON t1.subject_id = t2.subject_id
                  AND t1.object_value = t2.object_value
                  AND t1.object_type = t2.object_type
               WHERE t1.predicate_id = ? AND t2.predicate_id = ?
               LIMIT 1""",
            (new_id, old_id),
        )
        if triple_coll:
            raise ValueError(
                f"Rename would cause triple PK collision "
                f"with predicate_id '{new_id}'"
            )

        # Check predicate group member collision (single query)
        group_coll = self.db.execute_one(
            """SELECT 1 FROM predicate_group_members pg1
               JOIN predicate_group_members pg2
                  ON pg1.group_uuid = pg2.group_uuid
               WHERE pg1.predicate_id = ? AND pg2.predicate_id = ?
               LIMIT 1""",
            (new_id, old_id),
        )
        if group_coll:
            raise ValueError(
                f"Rename would cause predicate group member collision: "
                f"predicate '{new_id}' already in the same group"
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
            # Temporarily disable FK enforcement for the PK rename.
            # Cascade updates below restore consistency before commit.
            conn.execute("PRAGMA foreign_keys=OFF")
            try:
                # FTS operations inside the transaction so rollback keeps them in sync
                self._remove_from_fts(old_id, conn=conn)
                set_parts = [f"{k} = ?" for k in updates]
                params = [*list(updates.values()), old_id]
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

                self._index_fts(new_id, conn=conn)
            finally:
                conn.execute("PRAGMA foreign_keys=ON")

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
        escaped = escape_like(query)
        return self.db.execute(
            "SELECT *, 0 AS _rank FROM predicates WHERE "
            "predicate_id LIKE ? COLLATE NOCASE OR "
            "labels LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "descriptions LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "aliases LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "LIMIT ?",
            (f"%{escaped}%", f"%{escaped}%", f"%{escaped}%", f"%{escaped}%", limit),
        )
