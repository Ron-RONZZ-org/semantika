"""LLM tools for predicate operations — search, view, and create.

Tools call :class:`~semantika.graph.predicate_service.PredicateService`
directly with clean keyword arguments.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.llm.tools import llm_tool

logger = logging.getLogger(__name__)


def _serialize_predicate(pred: dict[str, Any]) -> dict[str, Any]:
    """Serialize a predicate dict, parsing JSON fields."""
    result = dict(pred)
    for field in ("labels", "descriptions", "aliases"):
        if isinstance(result.get(field), str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


# ── Search ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="predicate.search",
    description="Search predicates by ID or label.  Returns matching "
    "predicates with their labels and descriptions.",
    params=[
        {"name": "q", "type": "string", "description": "Search query — matches against predicate ID and labels", "required": True},
        {"name": "limit", "type": "integer", "description": "Maximum results (default 20)", "default": 20},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_predicate_search(q: str = "", limit: int = 20, **kwargs) -> dict:
    """Search predicates by query text."""
    if not q:
        return {"success": False, "error": "Search query is required"}

    svc = get_services()
    pred_svc = svc.get("predicate")
    if not pred_svc:
        return {"success": False, "error": "Predicate service not available"}

    try:
        results = pred_svc.search(q)
        serialized = [_serialize_predicate(p) for p in results[:limit]]
        return {
            "success": True,
            "data": serialized,
            "total": len(results),
        }
    except Exception as exc:
        logger.exception("predicate.search failed")
        return {"success": False, "error": str(exc)}


# ── View ─────────────────────────────────────────────────────────────────────


@llm_tool(
    name="predicate.view",
    description="View a single predicate by its ID.  Returns the "
    "predicate's labels, description, aliases, and source.",
    params=[
        {"name": "id", "type": "string", "description": "Predicate ID to retrieve (e.g. 'rdf:type', 'sm:depicts')", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_predicate_view(id: str = "", **kwargs) -> dict:
    """Retrieve a single predicate by ID."""
    if not id:
        return {"success": False, "error": "Predicate ID is required"}

    svc = get_services()
    pred_svc = svc.get("predicate")
    if not pred_svc:
        return {"success": False, "error": "Predicate service not available"}

    try:
        pred = pred_svc.get(id)
        if not pred:
            return {"success": False, "error": f"Predicate not found: {id}"}
        return {"success": True, "data": _serialize_predicate(pred)}
    except Exception as exc:
        logger.exception("predicate.view failed for %s", id)
        return {"success": False, "error": str(exc)}


# ── Create ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="predicate.create",
    description="Create a new predicate (relationship type).  Labels "
    "should be a JSON object like {'en': 'is author of', "
    "'fr': 'est auteur de'}.  Use this when you need a "
    "relationship that doesn't exist yet.",
    params=[
        {"name": "id", "type": "string", "description": "Predicate ID (e.g. 'my:hasRelation')", "required": True},
        {"name": "labels", "type": "string", "description": "Labels as JSON dict, e.g. {'en':'is author of'}"},
        {"name": "descriptions", "type": "string", "description": "Descriptions as JSON dict"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_predicate_create(**kwargs) -> dict:
    """Create a new predicate."""
    pred_id = kwargs.get("id", "").strip()
    if not pred_id:
        return {"success": False, "error": "Predicate ID is required"}

    svc = get_services()
    pred_svc = svc.get("predicate")
    if not pred_svc:
        return {"success": False, "error": "Predicate service not available"}

    data: dict[str, Any] = {"predicate_id": pred_id}

    raw_labels = kwargs.get("labels", "")
    if raw_labels:
        try:
            data["labels"] = json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels
        except json.JSONDecodeError:
            data["labels"] = {"en": raw_labels}

    raw_descs = kwargs.get("descriptions", "")
    if raw_descs:
        try:
            data["descriptions"] = json.loads(raw_descs) if isinstance(raw_descs, str) else raw_descs
        except json.JSONDecodeError:
            data["descriptions"] = {"en": raw_descs}

    try:
        result = pred_svc.create(data)
        if result:
            return {"success": True, "data": _serialize_predicate(result)}
        return {"success": False, "error": "Failed to create predicate"}
    except Exception as exc:
        logger.exception("predicate.create failed")
        return {"success": False, "error": str(exc)}
