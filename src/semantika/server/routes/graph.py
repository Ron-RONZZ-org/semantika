"""Graph CRUD API routes."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/nodes")
async def list_nodes():
    """List all nodes in the graph."""
    return {"nodes": []}


@router.post("/nodes")
async def create_node():
    """Create a new node."""
    return {"node": {}}


@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    """Get a single node by ID."""
    return {"node": {}}


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str):
    """Delete a node."""
    return {"deleted": True}


@router.get("/triples")
async def list_triples():
    """Search/filter triples."""
    return {"triples": []}


@router.post("/triples")
async def create_triple():
    """Add a triple (subject-predicate-object)."""
    return {"triple": {}}


@router.get("/predicates")
async def list_predicates():
    """List all predicates."""
    return {"predicates": []}
