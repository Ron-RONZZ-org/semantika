"""Graph CRUD API routes — nodes, predicates, triples."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from semantika.graph.db import get_services

router = APIRouter()


def _svc() -> Any:
    """Get service singletons."""
    return get_services()


def _annotate_triples_with_labels(triples: list[dict]) -> list[dict]:
    """Annotate raw triples with ``_subject_label``, ``_predicate_label``,
    ``_object_label`` by bulk-fetching referenced nodes and predicates.

    Mutates triples in place and returns the same list.
    """
    if not triples:
        return triples
    svc = _svc()
    node_svc = svc["node"]
    pred_svc = svc["predicate"]

    all_node_ids: set[str] = set()
    all_pred_ids: set[str] = set()
    for t in triples:
        all_node_ids.add(t["subject_id"])
        all_pred_ids.add(t["predicate_id"])
        if t.get("object_type") == "uri":
            all_node_ids.add(t["object_value"])

    node_map: dict[str, dict] = {}
    if all_node_ids:
        for n in node_svc.get_by_nodes(list(all_node_ids)):
            node_map[n["node_id"]] = n

    pred_map: dict[str, dict] = {}
    if all_pred_ids:
        for p in pred_svc.get_by_ids(list(all_pred_ids)):
            pred_map[p["predicate_id"]] = p

    for t in triples:
        subj = node_map.get(t["subject_id"])
        t["_subject_label"] = _get_label(subj) if subj else t["subject_id"]

        pred = pred_map.get(t["predicate_id"])
        t["_predicate_label"] = _get_label(pred) if pred else t["predicate_id"]

        if t.get("object_type") == "uri":
            obj = node_map.get(t["object_value"])
            t["_object_label"] = _get_label(obj) if obj else t["object_value"]
        else:
            t["_object_label"] = t["object_value"]

    return triples


def _get_label(entity: dict) -> str:
    """Extract display label from a node or predicate dict."""
    labels_raw = entity.get("labels", "{}")
    try:
        labels = json.loads(labels_raw) if isinstance(labels_raw, str) else labels_raw
    except (json.JSONDecodeError, TypeError):
        return entity.get("node_id") or entity.get("predicate_id", "")
    if not isinstance(labels, dict):
        return entity.get("node_id") or entity.get("predicate_id", "")
    for val in labels.values():
        if val and isinstance(val, str):
            return val
    return entity.get("node_id") or entity.get("predicate_id", "")


# ── Pydantic models ────────────────────────────────────────────────────

class NodeCreate(BaseModel):
    node_id: str | None = None
    labels: dict[str, str] = {}
    definitions: dict[str, str] = {}
    iri: str = ""


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
    iri: str = ""


class PredicateUpdate(BaseModel):
    labels: dict[str, str] | None = None
    descriptions: dict[str, str] | None = None


# ── Nodes (static routes BEFORE dynamic {node_id}) ─────────────────────

@router.get("/nodes")
def list_nodes(
    limit: int = 100,
    offset: int = 0,
    order_by: str = "node_id",
    direction: str = "asc",
):
    """List all nodes with optional sorting and pagination.

    Args:
        limit: Max rows to return.
        offset: Row offset for pagination.
        order_by: Sort column (``node_id``, ``created_at``, ``updated_at``, ``label_text``).
        direction: Sort direction (``asc`` or ``desc``).
    """
    svc = _svc()["node"]
    allowed_columns = {"node_id", "created_at", "updated_at", "label_text"}
    if order_by not in allowed_columns:
        order_by = "node_id"
    direction = "ASC" if direction.lower() == "asc" else "DESC"
    nodes = svc.list(limit=limit, offset=offset, order_by=order_by, direction=direction)
    return {"nodes": nodes, "total": svc.count()}


@router.get("/nodes/search")
def search_nodes(q: str, limit: int = 50):
    """Search nodes by label text."""
    results = _svc()["node"].search(q, limit=limit)
    return {"results": results}


@router.get("/nodes/stats")
def node_stats():
    """Get graph statistics."""
    return _svc()["triple"].get_stats()


@router.post("/nodes")
def create_node(data: NodeCreate):
    """Create a node."""
    svc = _svc()["node"]
    try:
        node = svc.create(data.model_dump())
        return {"node": node}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/nodes/{node_id}")
def get_node(node_id: str):
    """Get a single node by ID."""
    node = _svc()["node"].resolve_node_id_prefix(node_id)
    if not node:
        raise HTTPException(404, f"Node not found: {node_id}")
    triples = _svc()["triple"].get_by_subject(node["node_id"])
    _annotate_triples_with_labels(triples)
    return {"node": node, "triples": triples}


@router.patch("/nodes/{node_id}")
def update_node(node_id: str, data: NodeUpdate):
    """Update a node."""
    svc = _svc()["node"]
    try:
        node = svc.update(node_id, data.model_dump(exclude_none=True))
        return {"node": node}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.patch("/nodes/{node_id}/rename")
def rename_node(node_id: str, data: NodeRename):
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
def rename_predicate(predicate_id: str, data: PredicateRename):
    """Rename a predicate's predicate_id, cascading to all references."""
    svc = _svc()["predicate"]
    try:
        pred = svc.update_predicate_id(predicate_id, data.new_id)
        return {"predicate": pred}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/nodes/merge")
def merge_nodes(source_id: str, target_id: str):
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
def delete_node(
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
def list_trash(limit: int = 50, offset: int = 0):
    """List soft-deleted nodes in the trash."""
    items = _svc()["node"].list_trash(limit=limit, offset=offset)
    total_row = _svc()["node"].db.execute_one("SELECT COUNT(*) AS cnt FROM nodes_trash")
    total = total_row["cnt"] if total_row else 0
    return {"items": items, "total": total}


@router.post("/trash/{node_id}/restore")
def restore_node(node_id: str):
    """Restore a soft-deleted node from trash."""
    restored = _svc()["node"].restore_from_trash(node_id)
    if not restored:
        raise HTTPException(404, f"Node not found in trash: {node_id}")
    return {"node": restored}


@router.delete("/trash/purge")
def purge_trash(days: int = 30):
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
def list_predicates(
    limit: int = 100,
    offset: int = 0,
    order_by: str = "predicate_id",
    direction: str = "asc",
):
    """List all predicates with optional sorting and pagination.

    Args:
        limit: Max rows to return.
        offset: Row offset for pagination.
        order_by: Sort column (``predicate_id``, ``created_at``, ``updated_at``).
        direction: Sort direction (``asc`` or ``desc``).
    """
    svc = _svc()["predicate"]
    allowed_columns = {"predicate_id", "created_at", "updated_at"}
    if order_by not in allowed_columns:
        order_by = "predicate_id"
    direction = "ASC" if direction.lower() == "asc" else "DESC"
    preds = svc.list(limit=limit, offset=offset, order_by=order_by, direction=direction)
    return {"predicates": preds, "total": svc.count()}


@router.get("/predicates/search")
def search_predicates(q: str, limit: int = 50):
    """Search predicates by ID/label."""
    results = _svc()["predicate"].search(q, limit=limit)
    return {"results": results}


@router.get("/predicates/{predicate_id}")
def get_predicate(predicate_id: str):
    """Get a single predicate by ID."""
    pred = _svc()["predicate"].get(predicate_id)
    if not pred:
        raise HTTPException(404, f"Predicate not found: {predicate_id}")
    triples = _svc()["triple"].get_by_predicate(predicate_id)
    _annotate_triples_with_labels(triples)
    return {"predicate": pred, "triples": triples}


@router.post("/predicates")
def create_predicate(data: PredicateCreate):
    """Create a predicate."""
    svc = _svc()["predicate"]
    try:
        pred = svc.create(data.model_dump())
        return {"predicate": pred}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/predicates/{predicate_id}")
def update_predicate(predicate_id: str, data: PredicateUpdate):
    """Update a predicate's labels/descriptions."""
    svc = _svc()["predicate"]
    try:
        pred = svc.update(predicate_id, data.model_dump(exclude_none=True))
        return {"predicate": pred}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/predicates/{predicate_id}")
def delete_predicate(predicate_id: str):
    """Delete a predicate (moves to trash if supported)."""
    svc = _svc()
    deleted = svc["predicate"].delete(predicate_id, soft=True)
    if not deleted:
        raise HTTPException(404, f"Predicate not found: {predicate_id}")
    return {"deleted": True}


# ── Triples ────────────────────────────────────────────────────────────

@router.get("/triples")
def list_triples(limit: int = 100, offset: int = 0):
    """List all triples."""
    svc = _svc()["triple"]
    all_t = svc.db.execute(
        "SELECT * FROM triples ORDER BY subject_id, predicate_id LIMIT ? OFFSET ?", (limit, offset)
    )
    _annotate_triples_with_labels(all_t)
    return {"triples": all_t, "total": svc.count()}


@router.get("/triples/by-subject/{subject_id}")
def get_triples_by_subject(subject_id: str):
    """Get triples for a subject."""
    triples = _svc()["triple"].get_by_subject(subject_id)
    _annotate_triples_with_labels(triples)
    return {"triples": triples}


@router.patch("/triples")
def update_triple_metadata(
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
def create_triple(data: TripleCreate):
    """Add a triple."""
    svc = _svc()["triple"]
    try:
        triple = svc.add(**data.model_dump())
        return {"triple": triple}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/triples")
def delete_triple(
    subject_id: str | None = None,
    predicate_id: str | None = None,
    object_value: str | None = None,
    object_type: str | None = None,
):
    """Delete matching triples."""
    count = _svc()["triple"].remove(subject_id, predicate_id, object_value, object_type)
    return {"deleted": count}
