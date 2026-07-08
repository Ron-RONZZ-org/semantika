"""TripleService — subject-predicate-object arc management.

Ported from A-semantika's ``_triple_service.py`` with EO→EN migration.
"""

from __future__ import annotations

import logging
import sqlite3

from semantika.core import SemantikaDB
from semantika.core.crud import now
from semantika.graph.helpers import escape_like
from semantika.graph.node_helpers import get_label_from_node

logger = logging.getLogger(__name__)


class TripleService:
    """Service for managing triples (subject-predicate-object arcs)."""

    def __init__(self, db: SemantikaDB) -> None:
        self.db = db

    def add(
        self,
        subject_id: str,
        predicate_id: str,
        object_value: str,
        object_type: str = "uri",
        object_lang: str | None = None,
        object_datatype: str | None = None,
        object_unit: str | None = None,
    ) -> dict:
        """Add a triple.

        Args:
            subject_id: Subject node ID.
            predicate_id: Predicate ID.
            object_value: Object value (URI or literal).
            object_type: ``'uri'`` or ``'literal'``.
            object_lang: Language tag (for string literals).
            object_datatype: XSD datatype (for typed literals).
            object_unit: Unit node ID (for numeric literals with units).

        Raises:
            ValueError: If the triple already exists.
        """
        ts = now()
        row = {
            "subject_id": subject_id,
            "predicate_id": predicate_id,
            "object_value": object_value,
            "object_type": object_type,
            "object_lang": object_lang,
            "object_datatype": object_datatype,
            "object_unit": object_unit,
            "created_at": ts,
        }
        try:
            self.db.execute(
                "INSERT INTO triples (subject_id, predicate_id, object_value, "
                "object_type, object_lang, object_datatype, object_unit, created_at) "
                "VALUES (:subject_id, :predicate_id, :object_value, "
                ":object_type, :object_lang, :object_datatype, :object_unit, :created_at)",
                row,
            )
        except sqlite3.IntegrityError:
            raise ValueError(
                f"Triple already exists: {subject_id} → {predicate_id} → {object_value}"
            )
        return dict(row)

    def update_metadata(
        self,
        subject_id: str,
        predicate_id: str,
        object_value: str,
        object_type: str = "uri",
        object_lang: str | None = None,
        object_datatype: str | None = None,
        object_unit: str | None = None,
    ) -> dict | None:
        """Update mutable metadata on an existing triple.

        Only updates non-PK columns (object_lang, object_datatype, object_unit).
        PK columns (subject_id, predicate_id, object_value, object_type)
        cannot change — the SPO identity is fixed. Preserves created_at.

        Only columns explicitly provided (not None) are updated,
        so passing only ``object_lang`` does not overwrite existing
        ``object_datatype``.

        Returns:
            The updated triple dict, or ``None`` if no columns to update.

        Raises:
            ValueError: If no matching triple is found.
        """
        set_parts: list[str] = []
        params: list = []
        if object_lang is not None:
            set_parts.append("object_lang = ?")
            params.append(object_lang)
        if object_datatype is not None:
            set_parts.append("object_datatype = ?")
            params.append(object_datatype)
        if object_unit is not None:
            set_parts.append("object_unit = ?")
            params.append(object_unit)

        if not set_parts:
            return None  # no metadata columns to update

        params.extend([subject_id, predicate_id, object_value, object_type])
        sql = (
            f"UPDATE triples SET {', '.join(set_parts)}"
            " WHERE subject_id = ? AND predicate_id = ? AND object_value = ? AND object_type = ?"
        )
        with self.db.transaction() as conn:
            conn.execute(sql, params)
        return self.get_one(subject_id, predicate_id, object_value, object_type)

    def get_one(
        self,
        subject_id: str,
        predicate_id: str,
        object_value: str,
        object_type: str = "uri",
    ) -> dict | None:
        """Get a single triple by its compound key."""
        return self.db.execute_one(
            """SELECT * FROM triples
               WHERE subject_id = ? AND predicate_id = ? AND object_value = ? AND object_type = ?""",
            (subject_id, predicate_id, object_value, object_type),
        )

    def remove(
        self,
        subject_id: str | None = None,
        predicate_id: str | None = None,
        object_value: str | None = None,
        object_type: str | None = None,
    ) -> int:
        """Remove triples matching the given criteria. Returns count removed."""
        clauses = []
        params = []
        for col, val in [
            ("subject_id", subject_id),
            ("predicate_id", predicate_id),
            ("object_value", object_value),
            ("object_type", object_type),
        ]:
            if val is not None:
                clauses.append(f"{col} = ?")
                params.append(val)
        if not clauses:
            return 0
        sql = f"DELETE FROM triples WHERE {' AND '.join(clauses)}"
        self.db.execute(sql, tuple(params))
        # Return count from the number of affected rows
        result = self.db.execute_one("SELECT changes() AS cnt")
        return result["cnt"] if result else 0

    # ── Queries ────────────────────────────────────────────────────────

    def get_by_subject(self, subject_id: str) -> list[dict]:
        """Get all triples with the given subject."""
        return self.db.execute(
            "SELECT * FROM triples WHERE subject_id = ? ORDER BY predicate_id",
            (subject_id,),
        )

    def get_by_predicate(self, predicate_id: str, limit: int = 100) -> list[dict]:
        """Get all triples with the given predicate."""
        return self.db.execute(
            "SELECT * FROM triples WHERE predicate_id = ? LIMIT ?",
            (predicate_id, limit),
        )

    def get_by_object(self, object_value: str, object_type: str | None = None) -> list[dict]:
        """Get all triples with the given object."""
        if object_type:
            return self.db.execute(
                "SELECT * FROM triples WHERE object_value = ? AND object_type = ?",
                (object_value, object_type),
            )
        return self.db.execute(
            "SELECT * FROM triples WHERE object_value = ?", (object_value,)
        )

    def search_by_labels(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        limit: int = 100,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> list[dict]:
        """Search triples by resolving partial labels/IDs to exact IDs.

        Resolves *subject*, *predicate*, and *object* texts to exact
        node/predicate IDs via prefix matching and FTS5 label search,
        then queries triples matching all provided criteria.

        For the *object* parameter, if the text does not resolve to any
        node, it falls back to ``object_value LIKE '%text%'`` so that
        literal values (strings, numbers, etc.) can be searched directly.

        Args:
            subject: Partial subject node ID or label.
            predicate: Partial predicate ID or label.
            object: Partial object node ID, label, or literal value.
            limit: Maximum results.
            created_after: ISO 8601 start datetime (inclusive). Filters
                triples where ``created_at >= created_after``.
            created_before: ISO 8601 end datetime (inclusive). Filters
                triples where ``created_at <= created_before``.

        Returns:
            List of matching triple dicts.
        """
        from semantika.graph.db import get_services
        svc = get_services()
        node_svc = svc["node"]
        pred_svc = svc["predicate"]

        subject_ids: list[str] | None = None
        predicate_ids: list[str] | None = None
        object_ids: list[str] | None = None
        object_literals: list[str] | None = None

        # Resolve subject
        if subject:
            subj_node = node_svc.resolve_node_id_prefix(subject)
            if not subj_node:
                # Try FTS5 label search
                results = node_svc.search(subject, limit=5)
                if results:
                    subject_ids = [r["node_id"] for r in results]
                else:
                    return []
            else:
                subject_ids = [subj_node["node_id"]]

        # Resolve predicate
        if predicate:
            pred = pred_svc.resolve_predicate_id_prefix(predicate)
            if not pred:
                # Try LIKE label search
                results = pred_svc.search(predicate, limit=5)
                if results:
                    predicate_ids = [r["predicate_id"] for r in results]
                else:
                    return []
            else:
                predicate_ids = [pred["predicate_id"]]

        # Resolve object — try node resolution first, fall back to literal LIKE
        if object:
            obj_node = node_svc.resolve_node_id_prefix(object)
            if not obj_node:
                results = node_svc.search(object, limit=5)
                if results:
                    object_ids = [r["node_id"] for r in results]
                else:
                    # Fall back to literal value LIKE matching so that
                    # users can search for object text directly (e.g.
                    # ``!triple search --object "some phrase"``).
                    object_literals = [object]
            else:
                object_ids = [obj_node["node_id"]]

        # Build query
        clauses: list[str] = []
        params: list = []

        if subject_ids:
            placeholders = ", ".join(["?"] * len(subject_ids))
            clauses.append(f"subject_id IN ({placeholders})")
            params.extend(subject_ids)

        if predicate_ids:
            placeholders = ", ".join(["?"] * len(predicate_ids))
            clauses.append(f"predicate_id IN ({placeholders})")
            params.extend(predicate_ids)

        # Object clause: URI matches (exact node IDs) OR literal LIKE matches
        object_clauses: list[str] = []
        if object_ids:
            placeholders = ", ".join(["?"] * len(object_ids))
            object_clauses.append(
                f"object_value IN ({placeholders})"
            )
            params.extend(object_ids)
        if object_literals:
            for val in object_literals:
                escaped = escape_like(val)
                object_clauses.append("object_value LIKE ? ESCAPE '\\'")
                params.append(f"%{escaped}%")
        if object_clauses:
            clauses.append(f"({' OR '.join(object_clauses)})")

        if created_after is not None:
            clauses.append("created_at >= ?")
            params.append(created_after)

        if created_before is not None:
            clauses.append("created_at <= ?")
            params.append(created_before)

        if not clauses:
            # No filters — return all triples (capped by limit)
            sql = "SELECT * FROM triples ORDER BY subject_id, predicate_id LIMIT ?"
            params.append(limit)
        else:
            where = " AND ".join(clauses)
            sql = f"SELECT * FROM triples WHERE {where} ORDER BY subject_id, predicate_id LIMIT ?"
            params.append(limit)

        triples = self.db.execute(sql, tuple(params))
        if not triples:
            return []

        # Bulk-fetch all referenced nodes and predicates (avoids N+1)
        all_node_ids: set[str] = set()
        all_pred_ids: set[str] = set()
        for t in triples:
            all_node_ids.add(t["subject_id"])
            all_pred_ids.add(t["predicate_id"])
            if t["object_type"] == "uri":
                all_node_ids.add(t["object_value"])

        node_map: dict[str, dict] = {}
        if all_node_ids:
            for n in node_svc.get_by_nodes(list(all_node_ids)):
                node_map[n["node_id"]] = n

        pred_map: dict[str, dict] = {}
        if all_pred_ids:
            for p in pred_svc.get_by_ids(list(all_pred_ids)):
                pred_map[p["predicate_id"]] = p

        # Annotate with labels
        result = []
        for t in triples:
            subj = node_map.get(t["subject_id"])
            t["_subject_label"] = get_label_from_node(subj) if subj else t["subject_id"]

            pred = pred_map.get(t["predicate_id"])
            t["_predicate_label"] = get_label_from_node(pred) if pred else t["predicate_id"]

            if t["object_type"] == "uri":
                obj = node_map.get(t["object_value"])
                t["_object_label"] = get_label_from_node(obj) if obj else t["object_value"]
            else:
                t["_object_label"] = t["object_value"]

            result.append(t)

        return result

    def get_by_sp(self, subject_id: str, predicate_id: str) -> list[dict]:
        """Get triples matching subject + predicate."""
        return self.db.execute(
            "SELECT * FROM triples WHERE subject_id = ? AND predicate_id = ?",
            (subject_id, predicate_id),
        )

    def get_by_nodes(self, node_ids: list[str]) -> list[dict]:
        """Get triples for multiple nodes in one query (O(1) vs O(N))."""
        if not node_ids:
            return []
        placeholders = ", ".join(["?"] * len(node_ids))
        return self.db.execute(
            f"SELECT * FROM triples WHERE subject_id IN ({placeholders}) "
            f"OR (object_type = 'uri' AND object_value IN ({placeholders}))",
            tuple(node_ids) + tuple(node_ids),
        )

    def exists(
        self,
        subject_id: str,
        predicate_id: str,
        object_value: str,
        object_type: str = "uri",
    ) -> bool:
        """Check if a triple exists."""
        row = self.db.execute_one(
            "SELECT 1 AS e FROM triples WHERE subject_id = ? AND predicate_id = ? "
            "AND object_value = ? AND object_type = ?",
            (subject_id, predicate_id, object_value, object_type),
        )
        return row is not None

    def count(self) -> int:
        """Return the number of triples in the store."""
        row = self.db.execute_one("SELECT COUNT(*) AS cnt FROM triples")
        return row["cnt"] if row else 0

    def get_stats(self) -> dict:
        """Return graph statistics."""
        nodes = self.db.execute_one("SELECT COUNT(*) AS cnt FROM nodes") or {"cnt": 0}
        preds = self.db.execute_one("SELECT COUNT(*) AS cnt FROM predicates") or {"cnt": 0}
        triples = self.count()
        return {
            "nodes": nodes["cnt"],
            "predicates": preds["cnt"],
            "triples": triples,
        }

    # ── Turtle Export ──────────────────────────────────────────────────

    def export_turtle(self, base_uri: str | None = None) -> str:
        """Export the entire triple store to standard Turtle (.ttl) format.

        Delegates to :func:`semantika.graph.triple_turtle.export_turtle`.

        Args:
            base_uri: Base URI for un-prefixed node IDs. Falls back to
                      ``https://example.org/`` if not provided — callers
                      should supply a real URI for production use.
        """
        from semantika.graph.triple_turtle import export_turtle as _export
        if base_uri is None:
            logger.warning(
                "export_turtle called without base_uri — using "
                "https://example.org/ placeholder. Pass base_uri explicitly."
            )
            base_uri = "https://example.org/"
        return _export(self.db, base_uri)
