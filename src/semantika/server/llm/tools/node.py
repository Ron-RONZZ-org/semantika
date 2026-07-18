"""LLM tools for node operations — CRUD and search.

Tools call :class:`~semantika.graph.node_service.NodeService` directly
with clean keyword arguments — no CLI flag parsing overhead.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.llm.tools import llm_tool

logger = logging.getLogger(__name__)


def _serialize_node(node: dict[str, Any]) -> dict[str, Any]:
    """Serialize a node dict, parsing JSON fields for readability."""
    result = dict(node)
    for field in ("labels", "definitions"):
        if isinstance(result.get(field), str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


# ── Search ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="node.search",
    description="Search nodes by ID prefix or full-text query.  Returns "
    "matching nodes with their labels and definitions.  Use "
    "this when you need to find nodes by name or content.",
    params=[
        {"name": "q", "type": "string", "description": "Search query — matches against node ID, labels, and definitions", "required": True},
        {"name": "limit", "type": "integer", "description": "Maximum number of results to return (default 20)", "default": 20},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_node_search(q: str = "", limit: int = 20, **kwargs) -> dict:
    """Search nodes by query text using FTS and ID prefix matching."""
    svc = get_services()
    node_svc = svc.get("node")
    if not node_svc:
        return {"success": False, "error": "Node service not available"}

    try:
        results = node_svc.search(q)
        serialized = [_serialize_node(n) for n in results[:limit]]
        return {
            "success": True,
            "data": serialized,
            "total": len(results),
        }
    except Exception as exc:
        logger.exception("node.search failed")
        return {"success": False, "error": str(exc)}


# ── View ─────────────────────────────────────────────────────────────────────


@llm_tool(
    name="node.view",
    description="View a single node by its ID.  Returns labels, "
    "definitions, and all triples where this node is "
    "subject or object.",
    params=[
        {"name": "id", "type": "string", "description": "Node ID to retrieve", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_node_view(id: str = "", **kwargs) -> dict:
    """Retrieve a single node with its labels, definitions, and triples."""
    if not id:
        return {"success": False, "error": "Node ID is required"}

    svc = get_services()
    node_svc = svc.get("node")
    if not node_svc:
        return {"success": False, "error": "Node service not available"}

    try:
        node = node_svc.get(id)
        if not node:
            return {"success": False, "error": f"Node not found: {id}"}

        data = _serialize_node(node)

        # Gather triples where this node is subject or object
        triple_svc = svc.get("triple")
        if triple_svc:
            try:
                subj_triples = triple_svc.search(subject=id) or []
                obj_triples = triple_svc.search(object=id) or []
                data["triples_as_subject"] = subj_triples
                data["triples_as_object"] = obj_triples
            except Exception:
                pass

        return {"success": True, "data": data}
    except Exception as exc:
        logger.exception("node.view failed for %s", id)
        return {"success": False, "error": str(exc)}


# ── Create ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="node.create",
    description="Create a new node.  Supports concept nodes and typed "
    "nodes (book, film, song, game, podcast, paper, patent, "
    "conference, photo, video, file, code).  Labels and "
    "definitions should be JSON objects like "
    "{'en': 'Name', 'fr': 'Nom'}.",
    params=[
        {"name": "id", "type": "string", "description": "Node ID (auto-generated from label if omitted)"},
        {"name": "type", "type": "string", "description": "Node type: concept, book, film, song, game, podcast, paper, patent, conference, photo, video, file, code", "required": True},
        {"name": "labels", "type": "string", "description": "Labels as JSON dict, e.g. {'en':'Alice','fr':'Alice'}"},
        {"name": "definitions", "type": "string", "description": "Definitions as JSON dict, e.g. {'en':'A person'}"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_node_create(**kwargs) -> dict:
    """Create a new node with the given parameters."""
    node_type = kwargs.get("type", "").strip()
    if not node_type:
        return {"success": False, "error": "Node type is required"}

    svc = get_services()
    node_svc = svc.get("node")
    if not node_svc:
        return {"success": False, "error": "Node service not available"}

    data: dict[str, Any] = {"type": node_type}

    node_id = kwargs.get("id", "").strip()
    if node_id:
        data["node_id"] = node_id

    raw_labels = kwargs.get("labels", "")
    if raw_labels:
        try:
            data["labels"] = json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels
        except json.JSONDecodeError:
            # Treat as plain text label
            data["labels"] = {"en": raw_labels}

    raw_defs = kwargs.get("definitions", "")
    if raw_defs:
        try:
            data["definitions"] = json.loads(raw_defs) if isinstance(raw_defs, str) else raw_defs
        except json.JSONDecodeError:
            data["definitions"] = {"en": raw_defs}

    try:
        result = node_svc.create(data)
        if result:
            return {"success": True, "data": _serialize_node(result)}
        return {"success": False, "error": "Failed to create node"}
    except Exception as exc:
        logger.exception("node.create failed")
        return {"success": False, "error": str(exc)}


# ── Update ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="node.update",
    description="Update a node's labels, definitions, or metadata.  Only "
    "provided fields are changed; omitted fields stay as-is.",
    params=[
        {"name": "id", "type": "string", "description": "Node ID to update", "required": True},
        {"name": "labels", "type": "string", "description": "New labels as JSON dict, e.g. {'en':'New Name'}"},
        {"name": "definitions", "type": "string", "description": "New definitions as JSON dict"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_node_update(**kwargs) -> dict:
    """Update an existing node's fields."""
    node_id = kwargs.get("id", "").strip()
    if not node_id:
        return {"success": False, "error": "Node ID is required"}

    svc = get_services()
    node_svc = svc.get("node")
    if not node_svc:
        return {"success": False, "error": "Node service not available"}

    data: dict[str, Any] = {}

    raw_labels = kwargs.get("labels", "")
    if raw_labels:
        try:
            data["labels"] = json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels
        except json.JSONDecodeError:
            data["labels"] = {"en": raw_labels}

    raw_defs = kwargs.get("definitions", "")
    if raw_defs:
        try:
            data["definitions"] = json.loads(raw_defs) if isinstance(raw_defs, str) else raw_defs
        except json.JSONDecodeError:
            data["definitions"] = {"en": raw_defs}

    if not data:
        return {"success": False, "error": "No fields to update — specify at least one of labels or definitions"}

    try:
        result = node_svc.update(node_id, data)
        if result:
            return {"success": True, "data": _serialize_node(result)}
        return {"success": False, "error": f"Node not found: {node_id}"}
    except Exception as exc:
        logger.exception("node.update failed for %s", node_id)
        return {"success": False, "error": str(exc)}


# ── Delete ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="node.delete",
    description="Delete a node.  This also removes all triples involving "
    "this node.  Use with caution — this operation cannot be "
    "undone without a backup.",
    params=[
        {"name": "id", "type": "string", "description": "Node ID to delete", "required": True},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_node_delete(**kwargs) -> dict:
    """Delete a node by ID (soft delete)."""
    node_id = kwargs.get("id", "").strip()
    if not node_id:
        return {"success": False, "error": "Node ID is required"}

    svc = get_services()
    node_svc = svc.get("node")
    if not node_svc:
        return {"success": False, "error": "Node service not available"}

    try:
        success = node_svc.delete(node_id)
        if success:
            return {"success": True, "data": {"deleted": node_id}}
        return {"success": False, "error": f"Node not found: {node_id}"}
    except Exception as exc:
        logger.exception("node.delete failed for %s", node_id)
        return {"success": False, "error": str(exc)}
