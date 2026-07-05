"""NodeService — knowledge graph entity management.

Ported from A-semantika's ``_node_service.py``, ``_node_search.py``, ``_node_merge_mixin.py``
with Esperanto-to-English migration.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid as _uuid
from typing import Any

from semantika.core import SemantikaDB, AmbiguousIDError
from semantika.core.crud import CRUDService, now
from semantika.core.fts import FTSConfig
from semantika.graph.constants import FTS5_KEYWORDS
from semantika.graph.node_helpers import (
    extract_definition_text,
    extract_label_text,
    get_label_from_node,
    sanitize_node_id,
)

logger = logging.getLogger(__name__)

FTS_CONFIG = FTSConfig(
    table="nodes",
    fts_columns=["label_text", "definition_text"],
    fts_table="nodes_fts",
)


class NodeService(CRUDService):
    """Service for managing knowledge graph nodes with FTS5 search and label support."""

    def __init__(self, db: SemantikaDB) -> None:
        super().__init__(db=db, table="nodes", trash_table="nodes_trash", pk_column="node_id")

    # ── Node ID Resolution ──────────────────────────────────────────────

    def resolve_node_id_prefix(self, prefix: str) -> dict | None:
        """Resolve a node_id prefix to a full node.

        Returns node dict if exactly one match, None if no match.
        Raises AmbiguousIDError if prefix matches multiple nodes.
        """
        if not prefix:
            return None
        prefix = sanitize_node_id(prefix)

        # Exact match first
        node = self.db.execute_one(
            "SELECT * FROM nodes WHERE node_id = ? COLLATE NOCASE", (prefix,)
        )
        if node:
            return node

        # Prefix search via LIKE
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matches = self.db.execute(
            "SELECT * FROM nodes WHERE node_id LIKE ? COLLATE NOCASE ESCAPE '\\'",
            (f"{escaped}%",),
        )
        if not matches:
            return None
        if len(matches) > 1:
            raise AmbiguousIDError(
                f"Node ID prefix '{prefix}' is ambiguous ({len(matches)} matches)",
                matches=matches,
            )
        return matches[0]

    # ── Override create ────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a node with optional pre-assigned node_id."""
        node_id_val = (
            sanitize_node_id(data.get("node_id"))
            if data.get("node_id")
            else str(_uuid.uuid4())
        )
        ts = now()

        raw = {
            "node_id": node_id_val,
            "labels": json.dumps(data.get("labels", {})),
            "label_text": extract_label_text(data.get("labels", {})),
            "definitions": json.dumps(data.get("definitions", {})),
            "definition_text": extract_definition_text(data.get("definitions", {})),
            "created_at": ts,
            "updated_at": ts,
        }
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO nodes (node_id, labels, label_text, definitions, "
                    "definition_text, created_at, updated_at) "
                    "VALUES (:node_id, :labels, :label_text, :definitions, "
                    ":definition_text, :created_at, :updated_at)",
                    raw,
                )
                self._index_fts(node_id_val)
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"Node with ID '{node_id_val}' already exists."
            ) from e

        return dict(raw)

    # ── Override get ────────────────────────────────────────────────────

    def get(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by exact node_id (case-insensitive)."""
        return self.db.execute_one(
            "SELECT * FROM nodes WHERE node_id = ? COLLATE NOCASE", (node_id,)
        )

    # ── Override update ────────────────────────────────────────────────

    def update(self, node_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a node, re-denormalizing labels/definitions if changed."""
        old = self.get(node_id)
        if not old:
            raise ValueError(f"Node not found: {node_id}")

        updates = dict(data)
        ts = now()

        if "labels" in updates:
            labels = updates["labels"]
            if isinstance(labels, dict):
                labels = json.dumps(labels)
            updates["labels"] = labels
            updates["label_text"] = extract_label_text(labels)

        if "definitions" in updates:
            defns = updates["definitions"]
            if isinstance(defns, dict):
                defns = json.dumps(defns)
            updates["definitions"] = defns
            updates["definition_text"] = extract_definition_text(defns)

        updates["updated_at"] = ts

        set_parts = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [node_id]
        sql = f"UPDATE nodes SET {', '.join(set_parts)} WHERE node_id = ?"

        with self.db.transaction() as conn:
            self._remove_from_fts(node_id)
            conn.execute(sql, params)
            self._index_fts(node_id)

        return self.get(node_id)

    # ── Override delete ────────────────────────────────────────────────

    def delete(self, node_id: str, soft: bool = True) -> bool:
        """Delete a node.

        If soft=True, moves to trash table. If False, permanent delete.
        """
        old_data = self.get(node_id)
        if not old_data:
            return False

        if soft and self._trash_table:
            self._move_to_trash(node_id)
        else:
            saved_rowid = None
            row = self.db.execute_one(
                f"SELECT rowid FROM {self.table} WHERE node_id = ?", (node_id,)
            )
            if row:
                saved_rowid = row["rowid"]

            with self.db.transaction() as conn:
                conn.execute(
                    f"DELETE FROM {self.table} WHERE node_id = ?", (node_id,)
                )

            if saved_rowid is not None:
                self._remove_fts_by_rowid(node_id, saved_rowid)

        self._post_delete(node_id, old_data)
        return True

    # ── Move to trash ─────────────────────────────────────────────────

    def _move_to_trash(self, node_id: str) -> None:
        """Move a node to the trash table, removing related triples first."""
        entry = self.db.execute_one(
            f"SELECT * FROM nodes WHERE node_id = ?", (node_id,)
        )
        if not entry:
            return

        entry["deleted_at"] = now()
        entry.setdefault("updated_at", entry["deleted_at"])

        columns = list(entry.keys())
        values = [entry[k] for k in columns]
        placeholders = ", ".join(["?"] * len(columns))

        with self.db.transaction() as conn:
            self._remove_from_fts(node_id)
            # Remove triples referencing this node (FK constraint)
            conn.execute(
                "DELETE FROM triples WHERE subject_id = ? OR (object_type = 'uri' AND object_value = ?)",
                (node_id, node_id),
            )
            conn.execute(
                f"INSERT OR REPLACE INTO nodes_trash ({', '.join(columns)}) "
                f"VALUES ({placeholders})", values,
            )
            conn.execute(
                f"DELETE FROM nodes WHERE node_id = ?", (node_id,)
            )

    # ── FTS5 Management ────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search on nodes via FTS5, falling back to LIKE."""
        if not query or not query.strip():
            return self.list(limit=limit)

        safe_tokens = []
        for word in query.strip().split():
            cleaned = "".join(c for c in word if c.isalnum() or c == "_")
            if not cleaned:
                continue
            if cleaned.upper() in FTS5_KEYWORDS:
                cleaned = cleaned.lower()
            safe_tokens.append(f"{cleaned}*")
        if not safe_tokens:
            return self.list(limit=limit)

        fts_query = " OR ".join(safe_tokens)
        # BM25 ranking with column weights:
        #   label_text (-5.0): most important — matches here ranked highest
        #   definition_text (-1.0): moderately important
        #   node_id (0.0): unindexed, zero weight
        # bm25() returns lower scores for better matches.
        fts_sql = """
            SELECT n.*, bm25(nodes_fts, 1.2, 0.75, 0.0, -5.0, -1.0) AS _rank
            FROM nodes n
            JOIN nodes_fts f ON n.node_id = f.node_id
            WHERE nodes_fts MATCH ?
            ORDER BY _rank
            LIMIT ?
        """
        try:
            results = self.db.execute(fts_sql, (fts_query, limit))
        except sqlite3.DatabaseError:
            logger.warning("FTS search failed — rebuilding and retrying")
            try:
                self._rebuild_fts()
                results = self.db.execute(fts_sql, (fts_query, limit))
            except sqlite3.DatabaseError:
                logger.error("FTS rebuild failed — using LIKE fallback")
                results = []

        if results:
            return results

        # Fallback: LIKE on label_text (no BM25 rank — set _rank to 0)
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return self.db.execute(
            "SELECT *, 0 AS _rank FROM nodes WHERE label_text LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT ?",
            (f"%{escaped}%", limit),
        )

    def _ensure_fts(self) -> None:
        """Ensure FTS5 virtual table exists and is populated."""
        self.db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
            "  node_id UNINDEXED,"
            "  label_text,"
            "  definition_text,"
            "  content=nodes,"
            "  content_rowid=rowid,"
            "  tokenize='unicode61'"
            ")"
        )
        count = self.db.execute_one("SELECT COUNT(*) AS cnt FROM nodes_fts")
        if count and count["cnt"] == 0:
            self._populate_fts()

    def _populate_fts(self) -> None:
        """Populate FTS from content table."""
        try:
            self.db.execute(
                "INSERT INTO nodes_fts (rowid, node_id, label_text, definition_text)"
                " SELECT rowid, node_id, label_text, definition_text FROM nodes"
            )
        except sqlite3.DatabaseError:
            logger.warning("FTS population failed — using LIKE fallback")

    def _index_fts(self, node_id: str) -> None:
        """Index a single node in FTS5."""
        entry = self.db.execute_one(
            "SELECT rowid, node_id, label_text, definition_text "
            "FROM nodes WHERE node_id = ?",
            (node_id,),
        )
        if not entry:
            return
        try:
            self.db.execute(
                "INSERT INTO nodes_fts (rowid, node_id, label_text, definition_text) "
                "VALUES (?, ?, ?, ?)",
                (entry["rowid"], node_id, entry["label_text"] or "", entry["definition_text"] or ""),
            )
        except sqlite3.DatabaseError as exc:
            logger.warning("FTS index insert failed for node %s: %s", node_id, exc)

    def _remove_from_fts(self, node_id: str) -> None:
        """Remove a node from FTS index."""
        row = self.db.execute_one(
            f"SELECT rowid FROM {self.table} WHERE node_id = ?", (node_id,)
        )
        if not row or row.get("rowid") is None:
            return
        self._remove_fts_by_rowid(node_id, row["rowid"])

    def _remove_fts_by_rowid(self, node_id: str, rowid: int) -> None:
        """Remove a rowid from the FTS index after node deletion."""
        try:
            self.db.execute(
                "INSERT INTO nodes_fts(nodes_fts, rowid) VALUES('delete', ?)",
                (rowid,),
            )
        except sqlite3.DatabaseError as exc:
            logger.warning(
                "FTS 'delete' failed for %s (rowid=%s): %s",
                node_id, rowid, exc,
            )

    def _rebuild_fts(self) -> None:
        """Rebuild the nodes FTS index from the content table.

        Handles corruption by dropping and recreating the FTS table
        if the FTS5 'rebuild' command fails.
        """
        try:
            self.db.execute(
                "INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')"
            )
        except sqlite3.DatabaseError:
            logger.warning("Nodes FTS rebuild failed — recreating table")
            # Drop shadow tables
            for suffix in ("_data", "_idx", "_docsize", "_config", "_content"):
                try:
                    self.db.execute(f"DROP TABLE IF EXISTS nodes_fts{suffix}")
                except sqlite3.DatabaseError:
                    pass
            try:
                self.db.execute("DROP TABLE IF EXISTS nodes_fts")
            except sqlite3.DatabaseError:
                pass
            # Recreate
            self._ensure_fts()
            self._populate_fts()

    # ── Node ID Rename ───────────────────────────────────────────────

    def update_node_id(self, old_id: str, new_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rename a node's node_id, cascading to all referencing triples.

        Manual SQL UPDATEs in a single transaction to handle FK
        constraints through generated columns.

        Args:
            old_id: Current node_id.
            new_id: New node_id.
            data: Optional additional field updates (labels, definitions, etc.).

        Returns:
            Updated node dict.

        Raises:
            ValueError: If old_id not found, new_id already exists, or
                PK collision would occur on triples.
        """
        old = self.get(old_id)
        if not old:
            raise ValueError(f"Node not found: {old_id}")

        existing = self.db.execute_one(
            "SELECT node_id FROM nodes WHERE node_id = ?", (new_id,)
        )
        if existing:
            raise ValueError(f"New node ID '{new_id}' already exists")

        # Check triple PK collisions
        old_triples = self.db.execute(
            "SELECT predicate_id, object_value, object_type FROM triples "
            "WHERE subject_id = ?", (old_id,),
        )
        for t in old_triples:
            coll = self.db.execute_one(
                "SELECT 1 FROM triples WHERE subject_id = ? AND predicate_id = ? "
                "AND object_value = ? AND object_type = ?",
                (new_id, t["predicate_id"], t["object_value"], t["object_type"]),
            )
            if coll:
                raise ValueError(
                    f"Rename would cause triple PK collision: "
                    f"({new_id}, {t['predicate_id']}, {t['object_value']}, {t['object_type']})"
                )

        old_obj_triples = self.db.execute(
            "SELECT subject_id, predicate_id, object_type FROM triples "
            "WHERE object_type = 'uri' AND object_value = ?", (old_id,),
        )
        for t in old_obj_triples:
            coll = self.db.execute_one(
                "SELECT 1 FROM triples WHERE subject_id = ? AND predicate_id = ? "
                "AND object_value = ? AND object_type = ?",
                (t["subject_id"], t["predicate_id"], new_id, t["object_type"]),
            )
            if coll:
                raise ValueError(
                    f"Rename would cause triple PK collision: "
                    f"({t['subject_id']}, {t['predicate_id']}, {new_id}, {t['object_type']})"
                )

        new_id = sanitize_node_id(new_id)
        updates = dict(data or {})
        ts = now()

        if "labels" in updates:
            labels = updates["labels"]
            if isinstance(labels, dict):
                labels = json.dumps(labels)
            updates["labels"] = labels
            updates["label_text"] = extract_label_text(labels)
        if "definitions" in updates:
            defns = updates["definitions"]
            if isinstance(defns, dict):
                defns = json.dumps(defns)
            updates["definitions"] = defns
            updates["definition_text"] = extract_definition_text(defns)

        updates["node_id"] = new_id
        updates["updated_at"] = ts

        # Save rowid before transaction for FTS cleanup
        old_rowid = None
        row = self.db.execute_one(
            f"SELECT rowid FROM {self.table} WHERE node_id = ?", (old_id,)
        )
        if row:
            old_rowid = row["rowid"]

        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            # Delete old FTS entry
            if old_rowid is not None:
                conn.execute(
                    f"INSERT INTO nodes_fts(nodes_fts, rowid) VALUES('delete', ?)",
                    (old_rowid,),
                )

            # Update node PK + fields
            set_parts = [f"{k} = ?" for k in updates]
            params = list(updates.values()) + [old_id]
            conn.execute(
                f"UPDATE nodes SET {', '.join(set_parts)} WHERE node_id = ?",
                params,
            )

            # Cascade to triples (subject)
            conn.execute(
                "UPDATE triples SET subject_id = ? WHERE subject_id = ?",
                (new_id, old_id),
            )

            # Cascade to triples (URI object)
            conn.execute(
                "UPDATE triples SET object_value = ? "
                "WHERE object_type = 'uri' AND object_value = ?",
                (new_id, old_id),
            )

            # Re-index FTS
            self._index_fts(new_id)

        return self.get(new_id)

    # ── Node Merge ────────────────────────────────────────────────────

    def merge_nodes(self, source_id: str, target_id: str) -> dict[str, Any]:
        """Merge source node INTO target node.

        All triples referencing *source* (as subject or URI object) are
        reassigned to *target*.  Triple PK conflicts (where *target* already
        has the same subject-predicate-object-type combination) are silently
        skipped — target wins.

        Labels and definitions are merged with target-first precedence:
        source languages that do not exist in target are added; target
        values are kept on collision.

        The source node is deleted after reassignment.  ALL operations
        happen in a single transaction with deferred FK checks.

        Args:
            source_id: Node ID of the source (will be deleted).
            target_id: Node ID of the target (survives).

        Returns:
            Updated target node dict.

        Raises:
            ValueError: If either node is not found, or source equals target.
        """
        if source_id == target_id:
            raise ValueError("Source and target must be different nodes")

        source = self.get(source_id)
        if not source:
            raise ValueError(f"Source node not found: {source_id}")

        target = self.get(target_id)
        if not target:
            raise ValueError(f"Target node not found: {target_id}")

        # Parse JSON column values
        try:
            source_labels = json.loads(source["labels"]) if isinstance(source["labels"], str) else source.get("labels", {})
        except (json.JSONDecodeError, TypeError):
            source_labels = {}
        try:
            target_labels = json.loads(target["labels"]) if isinstance(target["labels"], str) else target.get("labels", {})
        except (json.JSONDecodeError, TypeError):
            target_labels = {}
        try:
            source_defns = json.loads(source["definitions"]) if isinstance(source["definitions"], str) else source.get("definitions", {})
        except (json.JSONDecodeError, TypeError):
            source_defns = {}
        try:
            target_defns = json.loads(target["definitions"]) if isinstance(target["definitions"], str) else target.get("definitions", {})
        except (json.JSONDecodeError, TypeError):
            target_defns = {}

        merged_labels = {**source_labels, **target_labels}  # target wins
        merged_defns = {**source_defns, **target_defns}

        ts = now()

        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            # 1. Remove old FTS entries
            self._remove_from_fts(source_id)
            self._remove_from_fts(target_id)

            # 2. Update target with merged labels/definitions
            conn.execute(
                "UPDATE nodes SET labels = ?, label_text = ?, definitions = ?, "
                "definition_text = ?, updated_at = ? WHERE node_id = ?",
                (
                    json.dumps(merged_labels),
                    extract_label_text(merged_labels),
                    json.dumps(merged_defns),
                    extract_definition_text(merged_defns),
                    ts,
                    target_id,
                ),
            )

            # 3. Reassign triples where source is subject → target
            #    Skip collisions with target's existing triples
            conn.execute(
                """UPDATE triples SET subject_id = ?
                   WHERE subject_id = ?
                     AND (predicate_id, object_value, object_type) NOT IN (
                       SELECT predicate_id, object_value, object_type
                       FROM triples WHERE subject_id = ?
                     )""",
                (target_id, source_id, target_id),
            )

            # 4. Reassign triples where source is URI object → target
            conn.execute(
                """UPDATE triples SET object_value = ?
                   WHERE object_type = 'uri' AND object_value = ?
                     AND (subject_id, predicate_id, object_type) NOT IN (
                       SELECT subject_id, predicate_id, object_type
                       FROM triples WHERE object_type = 'uri' AND object_value = ?
                     )""",
                (target_id, source_id, target_id),
            )

            # 5. Clean up skipped collision triples still referencing source
            conn.execute(
                "DELETE FROM triples WHERE subject_id = ? "
                "OR (object_type = 'uri' AND object_value = ?)",
                (source_id, source_id),
            )

            # 6. Delete source node
            conn.execute("DELETE FROM nodes WHERE node_id = ?", (source_id,))

            # 7. Re-index target FTS
            self._index_fts(target_id)

        return self.get(target_id)

    # ── Batch operations ─────────────────────────────────────────────

    def get_by_nodes(self, node_ids: list[str]) -> list[dict]:
        """Fetch multiple nodes in one query (O(1) vs O(N) loop)."""
        if not node_ids:
            return []
        placeholders = ", ".join(["?"] * len(node_ids))
        return self.db.execute(
            f"SELECT * FROM nodes WHERE node_id IN ({placeholders})",
            tuple(node_ids),
        )

    def empty_all_trash(self) -> int:
        """Permanently delete all trashed nodes. Returns count deleted."""
        items = self.db.execute("SELECT * FROM nodes_trash")
        count = len(items)
        if count > 0:
            self.db.execute("DELETE FROM nodes_trash")
        return count

    def get_trash_older_than(self, days: int, limit: int = 1000) -> list[dict]:
        """Get trash entries older than *days*."""
        import datetime as _dt
        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
        return self.db.execute(
            "SELECT * FROM nodes_trash WHERE deleted_at < ? LIMIT ?",
            (cutoff.isoformat(), limit),
        )
