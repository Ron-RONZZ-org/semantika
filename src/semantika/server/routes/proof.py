"""Proof API routes — evidence attached to triples."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from semantika.graph.db import get_services

router = APIRouter()


class ProofCreate(BaseModel):
    subject_id: str
    predicate_id: str
    object_value: str
    object_type: str = "uri"
    proof_type: str = "observation"
    source: str = ""
    notes: str = ""


@router.post("/proofs")
def create_proof(data: ProofCreate):
    """Create a proof for a triple."""
    proof = get_services()["proof"].create(data.model_dump())
    return {"proof": proof}


@router.get("/proofs/by-triple")
def get_proofs_by_triple(subject_id: str, predicate_id: str, object_value: str):
    """Get proofs for a specific triple."""
    proofs = get_services()["proof"].get_by_triple(subject_id, predicate_id, object_value)
    return {"proofs": proofs}


@router.get("/proofs/by-subject/{subject_id}")
def get_proofs_by_subject(subject_id: str):
    """Get proofs for a subject's triples."""
    proofs = get_services()["proof"].get_by_subject(subject_id)
    return {"proofs": proofs}


@router.delete("/proofs/{proof_uuid}")
def delete_proof(proof_uuid: str):
    """Delete a proof."""
    get_services()["proof"].delete(proof_uuid)
    return {"deleted": True}
