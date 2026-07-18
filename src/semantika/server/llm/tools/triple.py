"""LLM tools for triple operations — search, add, and delete.

Tools call :class:`~semantika.graph.triple_service.TripleService`
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


# ── Search ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="triple.search",
    description="Search triples by subject, predicate, or object.  "
    "At least one search parameter is required.  Returns "
    "matching triples with their components and creation time.",
    params=[
        {"name": "subject", "type": "string", "description": "Subject node ID to match"},
        {"name": "predicate", "type": "string", "description": "Predicate ID to match"},
        {"name": "object", "type": "string", "description": "Object node ID or literal value to match"},
        {"name": "limit", "type": "integer", "description": "Maximum results (default 50)", "default": 50},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_triple_search(**kwargs) -> dict:
    """Search triples by subject, predicate, or object pattern.

    Uses the service's ``get_by_*`` methods individually since there
    is no single ``search()`` that accepts all three.
    """
    svc = get_services()
    triple_svc = svc.get("triple")
    if not triple_svc:
        return {"success": False, "error": "Triple service not available"}

    subject = kwargs.get("subject", "").strip()
    predicate = kwargs.get("predicate", "").strip()
    obj = kwargs.get("object", "").strip()
    limit = int(kwargs.get("limit", 50))

    if not any([subject, predicate, obj]):
        return {"success": False, "error": "At least one of subject, predicate, or object is required"}

    try:
        # Use the most specific lookup available
        results: list[dict] = []
        if subject and predicate:
            results = triple_svc.get_by_sp(subject, predicate)
        elif subject:
            results = triple_svc.get_by_subject(subject)
        elif predicate:
            results = triple_svc.get_by_predicate(predicate, limit=limit)
        else:
            results = triple_svc.get_by_object(obj)

        return {
            "success": True,
            "data": results[:limit],
            "total": len(results),
        }
    except Exception as exc:
        logger.exception("triple.search failed")
        return {"success": False, "error": str(exc)}


# ── Add ──────────────────────────────────────────────────────────────────────


@llm_tool(
    name="triple.add",
    description="Add one or more triples (subject-predicate-object "
    "statements).  Each triple is a dict with 'subject', "
    "'predicate', and 'object' keys.  Pass a JSON array "
    "for batch creation.  All subjects and objects must "
    "already exist as nodes.",
    params=[
        {"name": "subject", "type": "string", "description": "Subject node ID (for a single triple)"},
        {"name": "predicate", "type": "string", "description": "Predicate ID (for a single triple)"},
        {"name": "object", "type": "string", "description": "Object node ID or literal value (for a single triple)"},
        {"name": "triples", "type": "string", "description": "JSON array of triple dicts [{'subject':'S1','predicate':'P1','object':'O1'}, ...].  Use this for batch creation."},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_triple_add(**kwargs) -> dict:
    """Add one or more triples."""
    svc = get_services()
    triple_svc = svc.get("triple")
    if not triple_svc:
        return {"success": False, "error": "Triple service not available"}

    # Parse triples from kwargs
    triples_to_add: list[dict[str, Any]] = []

    raw_triples = kwargs.get("triples", "")
    if raw_triples:
        try:
            parsed = json.loads(raw_triples) if isinstance(raw_triples, str) else raw_triples
            if isinstance(parsed, list):
                triples_to_add.extend(parsed)
            else:
                triples_to_add.append(parsed)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid JSON in 'triples' parameter"}

    # Single triple via direct params
    subject = kwargs.get("subject", "").strip()
    predicate = kwargs.get("predicate", "").strip()
    obj = kwargs.get("object", "").strip()
    if subject and predicate and obj:
        triples_to_add.append({
            "subject": subject,
            "predicate": predicate,
            "object": obj,
        })

    if not triples_to_add:
        return {"success": False, "error": "No triples to add — provide subject+predicate+object or a triples JSON array"}

    results: list[dict] = []
    errors: list[str] = []

    for t in triples_to_add:
        try:
            triple_svc.add(
                subject=t.get("subject", ""),
                predicate_id=t.get("predicate", ""),
                object_value=t.get("object", ""),
                object_type=t.get("object_type", "node"),
            )
            results.append(t)
        except Exception as exc:
            errors.append(f"{t}: {exc}")

    return {
        "success": len(errors) == 0,
        "data": {"added": len(results), "failed": len(errors)},
        "errors": errors if errors else None,
    }


# ── Delete ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="triple.delete",
    description="Delete triples matching a subject, predicate, or object "
    "pattern.  At least one parameter is required.  Removing "
    "triples cannot be undone without a backup.",
    params=[
        {"name": "subject", "type": "string", "description": "Subject node ID to match"},
        {"name": "predicate", "type": "string", "description": "Predicate ID to match"},
        {"name": "object", "type": "string", "description": "Object value to match"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_triple_delete(**kwargs) -> dict:
    """Delete triples matching the given pattern."""
    svc = get_services()
    triple_svc = svc.get("triple")
    if not triple_svc:
        return {"success": False, "error": "Triple service not available"}

    subject = kwargs.get("subject", "").strip()
    predicate = kwargs.get("predicate", "").strip()
    obj = kwargs.get("object", "").strip()

    if not any([subject, predicate, obj]):
        return {"success": False, "error": "At least one of subject, predicate, or object is required"}

    try:
        removed = triple_svc.remove(
            subject=subject or None,
            predicate=predicate or None,
            object_value=obj or None,
        )
        return {"success": True, "data": {"removed": removed}}
    except Exception as exc:
        logger.exception("triple.delete failed")
        return {"success": False, "error": str(exc)}
