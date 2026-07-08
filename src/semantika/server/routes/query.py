"""Query API routes — search, export, ask."""

from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from semantika.graph.db import get_db_path, get_services

MAX_RAW_RESULTS = 1000

router = APIRouter()


@router.get("/search")
def search_all(q: str, limit: int = 50):
    """Full-text search across nodes and predicates."""
    svc = get_services()
    nodes = svc["node"].search(q, limit=limit)
    predicates = svc["predicate"].search(q, limit=limit)
    return {"results": {"nodes": nodes, "predicates": predicates}}


@router.get("/triples/search")
def search_triples(
    subject: str | None = None,
    predicate: str | None = None,
    object: str | None = None,
    limit: int = 100,
    created_after: str | None = None,
    created_before: str | None = None,
):
    """Search triples by resolving partial labels/IDs to exact IDs.

    Accepts partial node IDs, predicate IDs, or label text for each
    of the three SPO components.  Returns triples that match all
    provided criteria (logical AND).

    Optional date filtering via *created_after* and *created_before*
    (ISO 8601 format, e.g. ``2026-01-01T00:00:00``).
    """
    triples = get_services()["triple"].search_by_labels(
        subject=subject, predicate=predicate, object=object,
        limit=limit,
        created_after=created_after, created_before=created_before,
    )
    return {"triples": triples}


@router.get("/export")
def export_turtle():
    """Export the graph in Turtle (.ttl) format."""
    ttl = get_services()["triple"].export_turtle()
    return {"data": ttl, "format": "turtle"}


@router.get("/stats")
def graph_stats():
    """Return graph statistics."""
    stats = get_services()["triple"].get_stats()
    return stats


class ImportRequest(BaseModel):
    data: str


@router.post("/import")
def import_turtle(req: ImportRequest):
    """Import Turtle (.ttl) content into the triple store."""
    from semantika.graph.triple_turtle import import_turtle as _import
    stats = _import(req.data)
    return stats


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comments to prevent comment-based bypass of statement checks.

    Applies block-comment removal iteratively to defeat nested comments
    like ``/*/*/ SELECT 1 */`` which would otherwise survive a single pass.
    """
    prev = None
    while prev != sql:
        prev = sql
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    return sql.strip()


class RawQuery(BaseModel):
    query: str


def _readonly_conn() -> sqlite3.Connection:
    """Open a read-only connection to the SQLite database.

    This is the primary security boundary — even if an attacker crafts
    a malicious query, they **cannot** modify any data. The SQLite
    engine enforces this at the storage level.
    """
    db_path = get_db_path()
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@router.post("/raw")
def raw_query(req: RawQuery):
    """Execute a read-only SQL SELECT query against the triple store.

    This is **not** SPARQL — it runs raw SQL against the internal
    SQLite schema (``nodes``, ``predicates``, ``triples``, etc.).

    The connection is opened in read-only mode (``mode=ro``), so no
    modifications are possible regardless of query content.  Only
    ``SELECT`` statements are accepted.
    """
    stripped = _strip_sql_comments(req.query)
    if not stripped.upper().startswith("SELECT"):
        raise HTTPException(400, "Only SELECT queries are allowed")
    try:
        conn = _readonly_conn()
        cursor = conn.execute(stripped)
        rows = [dict(r) for r in cursor.fetchmany(MAX_RAW_RESULTS + 1)]
        truncated = len(rows) > MAX_RAW_RESULTS
        rows = rows[:MAX_RAW_RESULTS]
        conn.close()
        return {"results": rows, "count": len(rows), "truncated": truncated}
    except Exception as e:
        raise HTTPException(400, f"Query failed: {e}")
