"""Graph CRUD API routes — nodes, predicates, triples."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
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


class NodeRename(BaseModel):
    new_id: str
    labels: dict[str, str] | None = None
    definitions: dict[str, str] | None = None


class TripleCreate(BaseModel):
    subject_id: str
    predicate_id: str
    object_value: str
    object_type: str = "uri"
    object_lang: str | None = None
    object_datatype: str | None = None
    object_unit: str | None = None


class TripleUpdate(BaseModel):
    object_lang: str | None = None
    object_datatype: str | None = None
    object_unit: str | None = None


class PredicateCreate(BaseModel):
    predicate_id: str
    source: str = "manual"
    labels: dict[str, str] = {}
    descriptions: dict[str, str] = {}


class PredicateUpdate(BaseModel):
    labels: dict[str, str] | None = None
    descriptions: dict[str, str] | None = None


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
    triples = _svc()["triple"].get_by_subject(node["node_id"])
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


@router.patch("/nodes/{node_id}/rename")
async def rename_node(node_id: str, data: NodeRename):
    """Rename a node's node_id, cascading to all referencing triples."""
    svc = _svc()["node"]
    try:
        node = svc.update_node_id(
            node_id, data.new_id,
            data={"labels": data.labels, "definitions": data.definitions} if data.labels or data.definitions else None,
        )
        return {"node": node}
    except ValueError as e:
        raise HTTPException(400, str(e))


class PredicateRename(BaseModel):
    new_id: str


@router.patch("/predicates/{predicate_id}/rename")
async def rename_predicate(predicate_id: str, data: PredicateRename):
    """Rename a predicate's predicate_id, cascading to all references."""
    svc = _svc()["predicate"]
    try:
        pred = svc.update_predicate_id(predicate_id, data.new_id)
        return {"predicate": pred}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/nodes/merge")
async def merge_nodes(source_id: str, target_id: str):
    """Merge source node INTO target node.

    Source is deleted after all triples and metadata are reassigned.
    """
    svc = _svc()["node"]
    try:
        merged = svc.merge_nodes(source_id, target_id)
        return {"node": merged}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/nodes/{node_id}")
async def delete_node(
    node_id: str,
    soft: bool = Query(default=True, alias="soft"),
    force: bool = Query(default=False, alias="force"),
):
    """Delete a node.

    If the node is referenced by triples, returns 409 with dependency
    info unless ``force=true`` is set.
    """
    svc = _svc()["node"]
    if not force:
        warning = svc.get_delete_warning(node_id)
        if warning:
            raise HTTPException(409, warning)
    deleted = svc.delete(node_id, soft=soft)
    if not deleted:
        raise HTTPException(404, f"Node not found: {node_id}")
    return {"deleted": True}


# ── Trash (soft-deleted nodes) ─────────────────────────────────────────

@router.get("/trash")
async def list_trash(limit: int = 50, offset: int = 0):
    """List soft-deleted nodes in the trash."""
    items = _svc()["node"].list_trash(limit=limit, offset=offset)
    return {"items": items, "total": len(items)}


@router.post("/trash/{node_id}/restore")
async def restore_node(node_id: str):
    """Restore a soft-deleted node from trash."""
    restored = _svc()["node"].restore_from_trash(node_id)
    if not restored:
        raise HTTPException(404, f"Node not found in trash: {node_id}")
    return {"node": restored}


@router.delete("/trash/purge")
async def purge_trash(days: int = 30):
    """Permanently delete trash entries older than *days*.

    If *days* is 0, empties the entire trash.
    """
    svc = _svc()["node"]
    if days <= 0:
        count = svc.empty_all_trash()
    else:
        items = svc.get_trash_older_than(days)
        count = len(items)
        for item in items:
            node_id = item.get("node_id")
            if node_id:
                svc.db.execute("DELETE FROM nodes_trash WHERE node_id = ?", (node_id,))
    return {"deleted": count}


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


@router.patch("/predicates/{predicate_id}")
async def update_predicate(predicate_id: str, data: PredicateUpdate):
    """Update a predicate's labels/descriptions."""
    svc = _svc()["predicate"]
    try:
        pred = svc.update(predicate_id, data.model_dump(exclude_none=True))
        return {"predicate": pred}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/predicates/{predicate_id}")
async def delete_predicate(predicate_id: str):
    """Delete a predicate (moves to trash if supported)."""
    svc = _svc()
    deleted = svc["predicate"].delete(predicate_id, soft=True)
    if not deleted:
        raise HTTPException(404, f"Predicate not found: {predicate_id}")
    return {"deleted": True}


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


@router.patch("/triples")
async def update_triple_metadata(
    subject_id: str,
    predicate_id: str,
    object_value: str,
    object_type: str = "uri",
    data: TripleUpdate | None = None,
):
    """Update metadata on an existing triple (object_lang, object_datatype)."""
    if data is None:
        raise HTTPException(400, "No update data provided")
    svc = _svc()["triple"]
    try:
        triple = svc.update_metadata(
            subject_id, predicate_id, object_value, object_type,
            object_lang=data.object_lang,
            object_datatype=data.object_datatype,
            object_unit=data.object_unit,
        )
        if triple is None:
            raise HTTPException(404, "Triple not found")
        return {"triple": triple}
    except ValueError as e:
        raise HTTPException(400, str(e))


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
