"""LLM tools for SPARQL query operations.

Provides the ability to execute SPARQL queries and check engine status.
"""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_sparql_engine
from semantika.server.llm.tools import llm_tool

logger = logging.getLogger(__name__)


@llm_tool(
    name="sparql.query",
    description="Execute a SPARQL query against the knowledge graph.  "
    "Use this for complex graph traversals, multi-hop "
    "relationships, or aggregations that are hard to express "
    "as simple searches.  Returns the raw SPARQL result set.",
    params=[
        {"name": "query", "type": "string", "description": "SPARQL query string", "required": True},
        {"name": "limit", "type": "integer", "description": "Maximum results (default 100)", "default": 100},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_sparql_query(query: str = "", limit: int = 100, **kwargs) -> dict:
    """Execute a SPARQL query and return results."""
    if not query:
        return {"success": False, "error": "SPARQL query is required"}

    engine = get_sparql_engine()
    if not engine:
        return {"success": False, "error": "SPARQL engine is not available"}

    try:
        results = engine.query(query)
        if results is None:
            return {"success": False, "error": "SPARQL query returned no results"}

        # Convert results to a serializable format
        if hasattr(results, "fetchmany"):
            rows = results.fetchmany(limit)
        elif isinstance(results, list):
            rows = results[:limit]
        else:
            rows = [results]

        return {
            "success": True,
            "data": {
                "results": rows,
                "count": len(rows),
            },
        }
    except Exception as exc:
        logger.exception("sparql.query failed")
        return {"success": False, "error": str(exc)}


@llm_tool(
    name="sparql.status",
    description="Check if the SPARQL engine is available and "
    "synchronised with the SQLite database.",
    permission_level=PermissionLevel.READ,
)
def llm_sparql_status(**kwargs) -> dict:
    """Check SPARQL engine availability."""
    engine = get_sparql_engine()
    if not engine:
        return {"success": True, "data": {"available": False, "synced": False}}

    try:
        synced = getattr(engine, "is_synced", lambda: False)()
        return {
            "success": True,
            "data": {
                "available": True,
                "synced": synced,
            },
        }
    except Exception as exc:
        logger.exception("sparql.status failed")
        return {"success": False, "error": str(exc)}
