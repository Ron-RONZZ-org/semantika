"""NodeMergeMixin — merge and rename operations for NodeService.

Extracted from ``NodeService`` to keep ``node_service.py`` under 500 lines.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from semantika.graph.node_helpers import (
    extract_definition_text,
    extract_label_text,
    sanitize_node_id,
)

logger = logging.getLogger(__name__)


class NodeMergeMixin:
    """Mixin that provides node merge and rename operations.

    Requires the host class to provide:
    - ``self.db`` (SemantikaDB)
    - ``self.get(node_id)`` (from CRUDService)
    - ``self._remove_from_fts(node_id)`` (from NodeFtsMixin)
    - ``self._index_fts(node_id)`` (from NodeFtsMixin)
    - ``self.table`` (from CRUDService)
    """

    # ── Node ID Rename ───────────────────────────────────────────────

    def update_node_id(self, old_id: str, new_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rename a node's node_id, cascading to all referencing triples."""
        from semantika.core.crud import now

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
            "WHERE object_type = 'node' AND object_value = ?", (old_id,),
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
            try:
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
                    "WHERE object_type = 'node' AND object_value = ?",
                    (new_id, old_id),
                )

                self._index_fts(new_id)
            finally:
                conn.execute("PRAGMA defer_foreign_keys=OFF")

        return self.get(new_id)

    # ── Node Merge ────────────────────────────────────────────────────

    def merge_nodes(self, source_id: str, target_id: str) -> dict[str, Any]:
        """Merge source node INTO target node.

        All triples referencing *source* (as subject or URI object) are
        reassigned to *target*.  Triple PK conflicts are silently skipped.
        Labels and definitions are merged with target-first precedence.
        The source node is deleted after reassignment.
        """
        from semantika.core.crud import now

        if source_id == target_id:
            raise ValueError("Source and target must be different nodes")

        source = self.get(source_id)
        if not source:
            raise ValueError(f"Source node not found: {source_id}")

        target = self.get(target_id)
        if not target:
            raise ValueError(f"Target node not found: {target_id}")

        try:
            raw = source["labels"]
            source_labels = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            source_labels = {}
        try:
            raw = target["labels"]
            target_labels = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            target_labels = {}
        try:
            raw = source["definitions"]
            source_defns = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            source_defns = {}
        try:
            raw = target["definitions"]
            target_defns = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            target_defns = {}

        merged_labels = {**source_labels, **target_labels}
        merged_defns = {**source_defns, **target_defns}

        ts = now()

        with self.db.transaction() as conn:
            try:
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
                       WHERE object_type = 'node' AND object_value = ?
                         AND NOT EXISTS (
                           SELECT 1 FROM triples AS t2
                           WHERE t2.object_type = 'node'
                             AND t2.object_value = ?
                             AND t2.subject_id = triples.subject_id
                             AND t2.predicate_id = triples.predicate_id
                             AND t2.object_type = triples.object_type
                         )""",
                    (target_id, source_id, target_id),
                )

                conn.execute(
                    "DELETE FROM triples WHERE subject_id = ? "
                    "OR (object_type = 'node' AND object_value = ?)",
                    (source_id, source_id),
                )

                conn.execute("DELETE FROM nodes WHERE node_id = ?", (source_id,))

                self._index_fts(target_id)
            finally:
                conn.execute("PRAGMA defer_foreign_keys=OFF")

        return self.get(target_id)
