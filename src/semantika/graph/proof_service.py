"""ProofService — RDF reification for attaching proofs to arcs.

Ported from A-semantika's ``_provo_service.py``.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from semantika.core import SemantikaDB
from semantika.core.crud import now


class ProofService:
    """Service for managing proofs (evidence attached to triples).

    A proof records the source, type, and notes for why a triple exists.
    """

    def __init__(self, db: SemantikaDB) -> None:
        self.db = db

    def create(self, data: dict[str, Any]) -> dict:
        """Create a proof for a triple."""
        row = {
            "uuid": str(_uuid.uuid4()),
            "subject_id": data["subject_id"],
            "predicate_id": data["predicate_id"],
            "object_value": data["object_value"],
            "object_type": data.get("object_type", "uri"),
            "proof_type": data.get("proof_type", "observation"),
            "source": data.get("source", ""),
            "notes": data.get("notes", ""),
            "created_at": now(),
            "updated_at": now(),
        }
        self.db.execute(
            "INSERT INTO proofs (uuid, subject_id, predicate_id, object_value, "
            "object_type, proof_type, source, notes, created_at, updated_at) "
            "VALUES (:uuid, :subject_id, :predicate_id, :object_value, "
            ":object_type, :proof_type, :source, :notes, :created_at, :updated_at)",
            row,
        )
        return dict(row)

    def get_by_triple(
        self, subject_id: str, predicate_id: str, object_value: str
    ) -> list[dict]:
        """Get all proofs for a specific triple."""
        return self.db.execute(
            "SELECT * FROM proofs WHERE subject_id = ? AND predicate_id = ? AND object_value = ? "
            "ORDER BY created_at DESC",
            (subject_id, predicate_id, object_value),
        )

    def get_by_subject(self, subject_id: str) -> list[dict]:
        """Get all proofs for triples with the given subject."""
        return self.db.execute(
            "SELECT * FROM proofs WHERE subject_id = ? ORDER BY created_at DESC",
            (subject_id,),
        )

    def delete(self, proof_uuid: str) -> bool:
        """Delete a proof."""
        self.db.execute("DELETE FROM proofs WHERE uuid = ?", (proof_uuid,))
        return True

    def cascade_delete_proofs(
        self,
        subject_id: str,
        predicate_id: str,
        object_value: str,
    ) -> int:
        """Delete all proofs for a specific triple (cascade on triple delete).

        Args:
            subject_id: Subject node ID of the triple.
            predicate_id: Predicate ID of the triple.
            object_value: Object value of the triple.

        Returns:
            Number of proofs deleted.
        """
        self.db.execute(
            "DELETE FROM proofs WHERE subject_id = ? AND predicate_id = ? AND object_value = ?",
            (subject_id, predicate_id, object_value),
        )
        result = self.db.execute_one("SELECT changes() AS cnt")
        return result["cnt"] if result else 0

    def get_proofs_for_arcs_batch(
        self,
        arc_keys: list[tuple[str, str, str]],
    ) -> dict[tuple[str, str, str], list[str]]:
        """Batch query: for each arc (s,p,o), return list of proof UUIDs.

        Args:
            arc_keys: List of ``(subject_id, predicate_id, object_value)`` tuples.

        Returns:
            Dict mapping each arc key to a list of proof UUIDs.
        """
        if not arc_keys:
            return {}
        # Build WHERE clause with OR of all arc keys
        clauses: list[str] = []
        params: list = []
        for subj, pred, obj in arc_keys:
            clauses.append(
                "(subject_id = ? AND predicate_id = ? AND object_value = ?)"
            )
            params.extend([subj, pred, obj])
        where = " OR ".join(clauses)
        rows = self.db.execute(
            f"SELECT subject_id, predicate_id, object_value, uuid FROM proofs WHERE {where}",
            tuple(params),
        )
        result: dict[tuple[str, str, str], list[str]] = {}
        for r in rows:
            key = (r["subject_id"], r["predicate_id"], r["object_value"])
            result.setdefault(key, []).append(r["uuid"])
        return result
