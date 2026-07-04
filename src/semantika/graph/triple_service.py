"""TripleService — subject-predicate-object arc management.

Ported from A-semantika's ``_triple_service.py`` with EO→EN migration.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from semantika.core import SemantikaDB
from semantika.core.crud import now


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
    ) -> dict:
        """Add a triple."""
        ts = now()
        row = {
            "subject_id": subject_id,
            "predicate_id": predicate_id,
            "object_value": object_value,
            "object_type": object_type,
            "object_lang": object_lang,
            "object_datatype": object_datatype,
            "created_at": ts,
        }
        try:
            self.db.execute(
                "INSERT INTO triples (subject_id, predicate_id, object_value, "
                "object_type, object_lang, object_datatype, created_at) "
                "VALUES (:subject_id, :predicate_id, :object_value, "
                ":object_type, :object_lang, :object_datatype, :created_at)",
                row,
            )
        except sqlite3.IntegrityError:
            raise ValueError(
                f"Triple already exists: {subject_id} → {predicate_id} → {object_value}"
            )
        return dict(row)

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

    def export_turtle(self, base_uri: str = "https://example.org/") -> str:
        """Export the entire triple store to standard Turtle (.ttl) format.

        Delegates to :func:`semantika.graph.triple_turtle.export_turtle`.
        """
        from semantika.graph.triple_turtle import export_turtle as _export
        return _export(self.db, base_uri)
