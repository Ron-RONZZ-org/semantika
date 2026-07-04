"""Graph CRUD API routes — nodes, predicates, triples."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from semantika.graph.db import get_services

router = APIRouter()


def _svc() -> Any:
    """Get service singletons."""
    return get_services()


# ── Pydantic models ────────────────────────────────────────────────────

class NodeCreate(BaseModel):
    node_id: str | None = None
    labels: dict[str, str] = {}
    definitions: dict[str, str] = {}


class NodeUpdate(BaseModel):
    labels: dict[str, str] | None = None
    definitions: dict[str, str] | None = None


class TripleCreate(BaseModel):
    subject_id: str
    predicate_id: str
    object_value: str
    object_type: str = "uri"
    object_lang: str | None = None
    object_datatype: str | None = None


class PredicateCreate(BaseModel):
    predicate_id: str
    source: str = "manual"
    labels: dict[str, str] = {}
    descriptions: dict[str, str] = {}


# ── Nodes (static routes BEFORE dynamic {node_id}) ─────────────────────

@router.get("/nodes")
async def list_nodes(limit: int = 100, offset: int = 0):
    """List all nodes."""
    svc = _svc()["node"]
    return {"nodes": svc.list(limit=limit, offset=offset), "total": svc.count()}


@router.get("/nodes/search")
async def search_nodes(q: str, limit: int = 50):
    """Search nodes by label text."""
    results = _svc()["node"].search(q, limit=limit)
    return {"results": results}


@router.get("/nodes/stats")
async def node_stats():
    """Get graph statistics."""
    return _svc()["triple"].get_stats()


@router.post("/nodes")
async def create_node(data: NodeCreate):
    """Create a node."""
    svc = _svc()["node"]
    try:
        node = svc.create(data.model_dump())
        return {"node": node}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    """Get a single node by ID."""
    node = _svc()["node"].resolve_node_id_prefix(node_id)
    if not node:
        raise HTTPException(404, f"Node not found: {node_id}")
    triples = _svc()["triple"].get_by_subject(node_id)
    return {"node": node, "triples": triples}


@router.patch("/nodes/{node_id}")
async def update_node(node_id: str, data: NodeUpdate):
    """Update a node."""
    svc = _svc()["node"]
    try:
        node = svc.update(node_id, data.model_dump(exclude_none=True))
        return {"node": node}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str, soft: bool = True):
    """Delete a node."""
    svc = _svc()["node"]
    deleted = svc.delete(node_id, soft=soft)
    if not deleted:
        raise HTTPException(404, f"Node not found: {node_id}")
    return {"deleted": True}


# ── Predicates ─────────────────────────────────────────────────────────

@router.get("/predicates")
async def list_predicates(limit: int = 100, offset: int = 0):
    """List all predicates."""
    svc = _svc()["predicate"]
    return {"predicates": svc.list(limit=limit, offset=offset), "total": svc.count()}


@router.get("/predicates/search")
async def search_predicates(q: str, limit: int = 50):
    """Search predicates by ID/label."""
    results = _svc()["predicate"].search(q, limit=limit)
    return {"results": results}


@router.post("/predicates")
async def create_predicate(data: PredicateCreate):
    """Create a predicate."""
    svc = _svc()["predicate"]
    try:
        pred = svc.create(data.model_dump())
        return {"predicate": pred}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Triples ────────────────────────────────────────────────────────────

@router.get("/triples")
async def list_triples(limit: int = 100, offset: int = 0):
    """List all triples."""
    svc = _svc()["triple"]
    all_t = svc.db.execute(
        "SELECT * FROM triples ORDER BY subject_id, predicate_id LIMIT ? OFFSET ?", (limit, offset)
    )
    return {"triples": all_t, "total": svc.count()}


@router.get("/triples/by-subject/{subject_id}")
async def get_triples_by_subject(subject_id: str):
    """Get triples for a subject."""
    triples = _svc()["triple"].get_by_subject(subject_id)
    return {"triples": triples}


@router.post("/triples")
async def create_triple(data: TripleCreate):
    """Add a triple."""
    svc = _svc()["triple"]
    try:
        triple = svc.add(**data.model_dump())
        return {"triple": triple}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/triples")
async def delete_triple(
    subject_id: str | None = None,
    predicate_id: str | None = None,
    object_value: str | None = None,
    object_type: str | None = None,
):
    """Delete matching triples."""
    count = _svc()["triple"].remove(subject_id, predicate_id, object_value, object_type)
    return {"deleted": count}
