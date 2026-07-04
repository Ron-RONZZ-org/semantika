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
        """Move a node to the trash table."""
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
        fts_sql = """
            SELECT n.*
            FROM nodes n
            JOIN nodes_fts f ON n.node_id = f.node_id
            WHERE nodes_fts MATCH ?
            LIMIT ?
        """
        try:
            results = self.db.execute(fts_sql, (fts_query, limit))
        except sqlite3.DatabaseError:
            logger.warning("FTS search failed — falling back to LIKE")
            results = []

        if results:
            return results

        # Fallback: LIKE on label_text
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return self.db.execute(
            "SELECT * FROM nodes WHERE label_text LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT ?",
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
        except sqlite3.DatabaseError:
            pass

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
