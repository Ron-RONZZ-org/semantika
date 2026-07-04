"""Query API routes — search, export, ask."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from semantika.graph.db import get_services

router = APIRouter()


@router.get("/search")
async def search_all(q: str, limit: int = 50):
    """Full-text search across nodes and predicates."""
    svc = get_services()
    nodes = svc["node"].search(q, limit=limit)
    predicates = svc["predicate"].search(q, limit=limit)
    return {"results": {"nodes": nodes, "predicates": predicates}}


@router.get("/export")
async def export_turtle():
    """Export the graph in Turtle (.ttl) format."""
    ttl = get_services()["triple"].export_turtle()
    return {"data": ttl, "format": "turtle"}


@router.get("/stats")
async def graph_stats():
    """Return graph statistics."""
    stats = get_services()["triple"].get_stats()
    return stats


class ImportRequest(BaseModel):
    data: str


@router.post("/import")
async def import_turtle(req: ImportRequest):
    """Import Turtle (.ttl) content into the triple store."""
    from semantika.graph.triple_turtle import import_turtle as _import
    stats = _import(req.data)
    return stats


@router.get("/sparql")
async def sparql_query(query: str):
    """Execute a raw SQL query (limited SPARQL-like access).

    WARNING: Only SELECT queries allowed for safety.
    """
    query = query.strip()
    if not query.upper().startswith("SELECT"):
        from fastapi import HTTPException
        raise HTTPException(400, "Only SELECT queries are allowed")
    from semantika.graph.db import get_db
    try:
        results = get_db().execute(query)
        return {"results": results, "count": len(results)}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(400, f"Query failed: {e}")
