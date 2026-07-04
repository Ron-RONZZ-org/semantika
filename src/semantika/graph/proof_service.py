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
