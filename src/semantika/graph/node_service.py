"""NodeService — knowledge graph entity management.

Ported from A-semantika's ``_node_service.py``, ``_node_search.py``, ``_node_merge_mixin.py``
with Esperanto-to-English migration.

FTS5 management is in ``node_fts.py`` (NodeFtsMixin).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sqlite3
import uuid as _uuid
from typing import Any

from semantika.core import SemantikaDB, AmbiguousIDError
from semantika.core.crud import CRUDService, now
from semantika.core.fts import FTSConfig
from semantika.graph.node_helpers import (
    extract_definition_text,
    extract_label_text,
    get_label_from_node,
    normalize_label_to_id,
    sanitize_node_id,
)
from semantika.graph.node_fts import NodeFtsMixin

logger = logging.getLogger(__name__)

FTS_CONFIG = FTSConfig(
    table="nodes",
    fts_columns=["label_text", "definition_text"],
    fts_table="nodes_fts",
)


class NodeService(NodeFtsMixin, CRUDService):
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

        node = self.db.execute_one(
            "SELECT * FROM nodes WHERE node_id = ? COLLATE NOCASE", (prefix,)
        )
        if node:
            return node

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

    # ── Collision avoidance ────────────────────────────────────────────

    _COLLISION_MAX = 99

    def _generate_unique_node_id(self, base: str) -> str:
        """Return *base* if available, otherwise ``base_2``, ``base_3``, etc.

        Caps retries at ``_COLLISION_MAX`` (99) then falls back to a UUID.
        """
        if not self.get(base):
            return base
        for counter in range(2, self._COLLISION_MAX + 1):
            candidate = f"{base}_{counter}"
            if not self.get(candidate):
                return candidate
        return str(_uuid.uuid4())

    # ── Override create ────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a node with optional pre-assigned node_id.

        If no ``node_id`` is given, derives one from the first English label
        (or first available label) via ``normalize_label_to_id``, with
        collision avoidance (``_2``, ``_3``, … suffix). Falls back to UUID
        if no labels are provided.
        """
        node_id_raw = data.get("node_id")
        if node_id_raw:
            node_id_val = sanitize_node_id(node_id_raw)
        else:
            labels = data.get("labels", {})
            if isinstance(labels, str):
                try:
                    labels = json.loads(labels)
                except (json.JSONDecodeError, TypeError):
                    labels = {}
            first_label = None
            if isinstance(labels, dict):
                # Try English first, then first available
                first_label = labels.get("en") or next(
                    (v for v in labels.values() if v and isinstance(v, str)), None
                )
            if first_label:
                base_id = normalize_label_to_id(first_label)
                node_id_val = self._generate_unique_node_id(base_id)
            else:
                node_id_val = str(_uuid.uuid4())
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

    # ── Delete warning ─────────────────────────────────────────────────

    def get_delete_warning(self, node_id: str) -> str | None:
        """Check if deleting this node would cascade-delete triples.

        Returns a warning message with triple counts, or None if safe.
        """
        subject_count = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM triples WHERE subject_id = ?",
            (node_id,),
        )["cnt"]
        object_count = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM triples "
            "WHERE object_type = 'uri' AND object_value = ?",
            (node_id,),
        )["cnt"]
        total = subject_count + object_count
        if total == 0:
            return None
        parts = []
        if subject_count:
            parts.append(f"{subject_count} as subject")
        if object_count:
            parts.append(f"{object_count} as URI object")
        return (
            f"Deleting '{node_id}' will also remove {total} triple(s) "
            f"({', '.join(parts)}). Use --force to confirm."
        )

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
            "SELECT node_id, labels, label_text, definitions, definition_text, "
            "created_at, updated_at FROM nodes WHERE node_id = ?", (node_id,)
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

    # ── Node ID Rename ───────────────────────────────────────────────

    def update_node_id(self, old_id: str, new_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rename a node's node_id, cascading to all referencing triples."""
        old = self.get(old_id)
        if not old:
            raise ValueError(f"Node not found: {old_id}")

        existing = self.db.execute_one(
            "SELECT node_id FROM nodes WHERE node_id = ?", (new_id,)
        )
        if existing:
            raise ValueError(f"New node ID '{new_id}' already exists")

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

        old_rowid = None
        row = self.db.execute_one(
            f"SELECT rowid FROM {self.table} WHERE node_id = ?", (old_id,)
        )
        if row:
            old_rowid = row["rowid"]

        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            if old_rowid is not None:
                conn.execute(
                    "INSERT INTO nodes_fts(nodes_fts, rowid) VALUES('delete', ?)",
                    (old_rowid,),
                )

            set_parts = [f"{k} = ?" for k in updates]
            params = list(updates.values()) + [old_id]
            conn.execute(
                f"UPDATE nodes SET {', '.join(set_parts)} WHERE node_id = ?",
                params,
            )

            conn.execute(
                "UPDATE triples SET subject_id = ? WHERE subject_id = ?",
                (new_id, old_id),
            )
            conn.execute(
                "UPDATE triples SET object_value = ? "
                "WHERE object_type = 'uri' AND object_value = ?",
                (new_id, old_id),
            )

            self._index_fts(new_id)

        return self.get(new_id)

    # ── Node Merge ────────────────────────────────────────────────────

    def merge_nodes(self, source_id: str, target_id: str) -> dict[str, Any]:
        """Merge source node INTO target node.

        All triples referencing *source* (as subject or URI object) are
        reassigned to *target*.  Triple PK conflicts are silently skipped.
        Labels and definitions are merged with target-first precedence.
        The source node is deleted after reassignment.
        """
        if source_id == target_id:
            raise ValueError("Source and target must be different nodes")

        source = self.get(source_id)
        if not source:
            raise ValueError(f"Source node not found: {source_id}")

        target = self.get(target_id)
        if not target:
            raise ValueError(f"Target node not found: {target_id}")

        try:
            source_labels: dict = json.loads(source["labels"]) if isinstance(source["labels"], str) else source.get("labels", {})
        except (json.JSONDecodeError, TypeError):
            source_labels = {}
        try:
            target_labels: dict = json.loads(target["labels"]) if isinstance(target["labels"], str) else target.get("labels", {})
        except (json.JSONDecodeError, TypeError):
            target_labels = {}
        try:
            source_defns: dict = json.loads(source["definitions"]) if isinstance(source["definitions"], str) else source.get("definitions", {})
        except (json.JSONDecodeError, TypeError):
            source_defns = {}
        try:
            target_defns: dict = json.loads(target["definitions"]) if isinstance(target["definitions"], str) else target.get("definitions", {})
        except (json.JSONDecodeError, TypeError):
            target_defns = {}

        merged_labels = {**source_labels, **target_labels}
        merged_defns = {**source_defns, **target_defns}

        ts = now()

        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            self._remove_from_fts(source_id)
            self._remove_from_fts(target_id)

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

            conn.execute(
                """UPDATE triples SET subject_id = ?
                   WHERE subject_id = ?
                     AND NOT EXISTS (
                       SELECT 1 FROM triples AS t2
                       WHERE t2.subject_id = ?
                         AND t2.predicate_id = triples.predicate_id
                         AND t2.object_value = triples.object_value
                         AND t2.object_type = triples.object_type
                     )""",
                (target_id, source_id, target_id),
            )

            conn.execute(
                """UPDATE triples SET object_value = ?
                   WHERE object_type = 'uri' AND object_value = ?
                     AND NOT EXISTS (
                       SELECT 1 FROM triples AS t2
                       WHERE t2.object_type = 'uri'
                         AND t2.object_value = ?
                         AND t2.subject_id = triples.subject_id
                         AND t2.predicate_id = triples.predicate_id
                         AND t2.object_type = triples.object_type
                     )""",
                (target_id, source_id, target_id),
            )

            conn.execute(
                "DELETE FROM triples WHERE subject_id = ? "
                "OR (object_type = 'uri' AND object_value = ?)",
                (source_id, source_id),
            )

            conn.execute("DELETE FROM nodes WHERE node_id = ?", (source_id,))

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
        with self.db.transaction():
            items = self.db.execute("SELECT * FROM nodes_trash")
            count = len(items)
            if count > 0:
                self.db.execute("DELETE FROM nodes_trash")
        return count

    def get_trash_older_than(self, days: int, limit: int = 1000) -> list[dict]:
        """Get trash entries older than *days*."""
        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
        return self.db.execute(
            "SELECT * FROM nodes_trash WHERE deleted_at < ? LIMIT ?",
            (cutoff.isoformat(), limit),
        )
