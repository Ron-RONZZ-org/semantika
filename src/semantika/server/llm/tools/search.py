"""LLM tools for cross-domain search.

Provides full-text search across nodes and predicates simultaneously.
"""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.llm.tools import llm_tool

logger = logging.getLogger(__name__)


@llm_tool(
    name="search.fts",
    description="Full-text search across all graph content — nodes "
    "(labels, definitions) and predicates (labels, "
    "descriptions).  Use this when you need to find anything "
    "in the knowledge graph by keyword.",
    params=[
        {"name": "q", "type": "string", "description": "Search query", "required": True},
        {"name": "limit", "type": "integer", "description": "Maximum results per domain (default 10)", "default": 10},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_search_fts(q: str = "", limit: int = 10, **kwargs) -> dict:
    """Full-text search across nodes and predicates."""
    if not q:
        return {"success": False, "error": "Search query is required"}

    svc = get_services()
    results: dict[str, list] = {}

    # Search nodes
    node_svc = svc.get("node")
    if node_svc:
        try:
            nodes = node_svc.search(q)
            results["nodes"] = [
                {"id": n.get("node_id", ""), "label_text": n.get("label_text", "")}
                for n in nodes[:limit]
            ]
        except Exception as exc:
            logger.warning("Node search failed in search.fts: %s", exc)
            results["nodes"] = []

    # Search predicates
    pred_svc = svc.get("predicate")
    if pred_svc:
        try:
            preds = pred_svc.search(q)
            results["predicates"] = [
                {"id": p.get("predicate_id", ""), "label_text": p.get("labels", "")}
                for p in preds[:limit]
            ]
        except Exception as exc:
            logger.warning("Predicate search failed in search.fts: %s", exc)
            results["predicates"] = []

    return {"success": True, "data": results}
