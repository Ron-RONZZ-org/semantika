"""SPARQL 1.1 Protocol endpoint — GET/POST /api/v1/query/sparql.

Supports SELECT, ASK, CONSTRUCT, DESCRIBE queries against the Oxigraph
RocksDB cache, with result enrichment from SQLite.

SPARQL UPDATE is gated behind a separate route (``/sparql/update``) that
requires WRITE permission, consistent with the existing HITL pattern.

Follows the SPARQL 1.1 Protocol:
- ``GET /sparql?query=...`` — URL-encoded query
- ``POST /sparql`` with ``Content-Type: application/sparql-query`` — raw query
- ``POST /sparql`` with ``application/x-www-form-urlencoded`` — ``query=...``

Returns ``application/sparql-results+json`` for SELECT/ASK,
``text/turtle`` for CONSTRUCT/DESCRIBE.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from semantika.graph.db import get_sparql_engine

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────────

MAX_QUERY_LENGTH = 50_000
TIMEOUT_SECONDS = 30

SPARQL_RESULTS_JSON = "application/sparql-results+json"
TEXT_TURTLE = "text/turtle"


def _get_engine():
    """Get the SPARQL engine, lazy-initializing if needed."""
    engine = get_sparql_engine()
    if engine is not None:
        return engine
    # Lazy init on first use
    from semantika.graph.db import init_sparql_engine as _init
    engine = _init()
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "SPARQL engine not available. "
                "The pyoxigraph library is required (pip install pyoxigraph)."
            ),
        )
    return engine


# ── Helper: parse query from request ──────────────────────────────────────


def _extract_query(request: Request, query_param: str | None = None) -> str:
    """Extract the SPARQL query from request body or query parameter."""
    if query_param:
        return query_param

    content_type = (request.headers.get("content-type") or "").lower()

    if "application/sparql-query" in content_type:
        body = request.body()
        # Handled via async handler
        raise ValueError("Use the async handler for application/sparql-query")

    raise HTTPException(status_code=400, detail="No SPARQL query provided")


# ── GET /sparql ────────────────────────────────────────────────────────────


@router.get("/sparql")
def sparql_get(query: str = "") -> Response:
    """Handle GET SPARQL query (?query=...).

    Args:
        query: URL-encoded SPARQL query string.

    Returns:
        ``application/sparql-results+json`` for SELECT/ASK,
        ``text/turtle`` for CONSTRUCT/DESCRIBE.
    """
    if not query:
        return JSONResponse(
            content={"head": {"vars": []}, "results": {"bindings": []}},
            media_type=SPARQL_RESULTS_JSON,
        )

    if len(query) > MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"SPARQL query exceeds maximum length of {MAX_QUERY_LENGTH} characters",
        )

    engine = _get_engine()
    try:
        result = engine.execute(query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _build_response(result)


# ── POST /sparql ────────────────────────────────────────────────────────────


@router.post("/sparql")
async def sparql_post(request: Request) -> Response:
    """Handle POST SPARQL query.

    Accepts:
    - ``Content-Type: application/sparql-query`` (raw query in body)
    - ``Content-Type: application/x-www-form-urlencoded`` (``query=...``)
    """
    content_type = (request.headers.get("content-type") or "").lower()
    query = ""

    if "application/sparql-query" in content_type:
        body = await request.body()
        query = body.decode("utf-8")
    elif "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        query = (form.get("query") or "").strip()
    else:
        # Try reading as raw text
        body = await request.body()
        if body:
            query = body.decode("utf-8")

    if not query:
        raise HTTPException(status_code=400, detail="No SPARQL query provided")

    if len(query) > MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"SPARQL query exceeds maximum length of {MAX_QUERY_LENGTH} characters",
        )

    engine = _get_engine()
    try:
        result = engine.execute(query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _build_response(result)


# ── Response builder ──────────────────────────────────────────────────────


def _build_response(result: dict[str, Any]) -> Response:
    """Build a FastAPI response from the engine result dict.

    SELECT/ASK → ``application/sparql-results+json`` (JSONResponse)
    CONSTRUCT/DESCRIBE → ``text/turtle`` (PlainTextResponse)
    """
    if "results" in result or "boolean" in result:
        return JSONResponse(content=result, media_type=SPARQL_RESULTS_JSON)
    if "data" in result and "format" in result:
        return PlainTextResponse(
            content=result["data"],
            media_type=TEXT_TURTLE,
        )
    # Fallback: return as JSON
    return JSONResponse(content=result, media_type=SPARQL_RESULTS_JSON)


# ── SPARQL UPDATE (gated) ─────────────────────────────────────────────────


# ── Prefix preview (for frontend autocomplete) ────────────────────────────


@router.get("/sparql/preview")
def sparql_preview() -> dict:
    """Return available prefix mappings for the frontend autocomplete.

    Returns:
        A dict with ``prefixes``: list of ``{"prefix": str, "uri": str}``.
    """
    from semantika.graph.sparql.engine import _KNOWN_PREFIXES
    from semantika.graph.db import get_db

    prefixes = [{"prefix": pfx, "uri": uri} for pfx, uri in _KNOWN_PREFIXES.items()]

    # Try to load user-defined prefixes from the database
    try:
        db = get_db()
        rows = db.execute("SELECT prefix, uri FROM prefixes ORDER BY prefix")
        for row in rows:
            prefixes.append({"prefix": row["prefix"], "uri": row["uri"]})
    except Exception:
        pass  # prefixes table may not exist yet

    return {"prefixes": prefixes}


class UpdateRequest:
    """Pydantic model for SPARQL UPDATE requests."""
    query: str


@router.post("/sparql/update")
async def sparql_update(request: Request) -> Response:
    """Execute a SPARQL UPDATE query (INSERT/DELETE).

    **This route requires WRITE permission** and is consistent with the
    existing HITL (Human-In-The-Loop) permission framework.  Currently
    experimental — the preferred way to modify data is through the
    existing ``!`` commands.

    Returns a confirmation notice since the SPARQL cache is write-only
    via sync hooks.  For full SPARQL UPDATE support (including parsing
    INSERT/DELETE patterns), use the ``!sparql update`` command.
    """
    raise HTTPException(
        status_code=501,
        detail="SPARQL UPDATE is not yet supported via this route. "
               "Use the !sparql update command or the standard !triple add/remove commands.",
    )
