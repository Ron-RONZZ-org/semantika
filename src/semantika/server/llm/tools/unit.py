"""LLM tools for unit ontology operations.

Provides unit search capabilities using the unit ontology service.
Note: actual unit conversion is not supported as a service method;
the ontology stores unit metadata for semantic annotation.
"""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.llm.tools import llm_tool

logger = logging.getLogger(__name__)


@llm_tool(
    name="unit.search",
    description="Search the unit ontology by name or symbol.  Returns "
    "matching units with their ID, label, and symbol.  "
    "Examples: 'meter', 'kg', 'Celsius', 'foot'.",
    params=[
        {"name": "q", "type": "string", "description": "Unit name or symbol to search for", "required": True},
        {"name": "limit", "type": "integer", "description": "Maximum results (default 10)", "default": 10},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_unit_search(q: str = "", limit: int = 10, **kwargs) -> dict:
    """Search the unit ontology by name or symbol."""
    if not q:
        return {"success": False, "error": "Search query is required"}

    svc = get_services()
    unit_svc = svc.get("unit") or svc.get("builtin_type")
    if not unit_svc:
        return {"success": False, "error": "Unit service not available"}

    try:
        # List all units and filter by the query
        all_units = unit_svc.list_units() if hasattr(unit_svc, "list_units") else []
        q_lower = q.lower()
        results = [
            u for u in all_units
            if q_lower in u.get("node_id", "").lower()
            or q_lower in u.get("label_text", "").lower()
            or q_lower in u.get("symbol", "").lower()
        ]
        return {
            "success": True,
            "data": results[:limit],
            "total": len(results),
        }
    except Exception as exc:
        logger.exception("unit.search failed")
        return {"success": False, "error": str(exc)}


@llm_tool(
    name="unit.info",
    description="Get detailed information about a specific unit by its "
    "node ID or symbol.  Returns its type, symbol, and "
    "relationships in the unit hierarchy.",
    params=[
        {"name": "id", "type": "string", "description": "Unit node ID (e.g. 'unit_meter', 'unit_kg')", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_unit_info(id: str = "", **kwargs) -> dict:
    """Get detailed information about a specific unit."""
    if not id:
        return {"success": False, "error": "Unit ID is required"}

    svc = get_services()
    unit_svc = svc.get("unit") or svc.get("builtin_type")
    if not unit_svc:
        return {"success": False, "error": "Unit service not available"}

    try:
        info = unit_svc.get_unit_info(id) if hasattr(unit_svc, "get_unit_info") else None
        if not info:
            return {"success": False, "error": f"Unit not found: {id}"}
        return {"success": True, "data": info}
    except Exception as exc:
        logger.exception("unit.info failed for %s", id)
        return {"success": False, "error": str(exc)}
