"""Command dispatch API route.

``POST /api/v1/command`` — Execute a parsed command token list.
``GET /api/v1/command/tree`` — Return the command tree for autocomplete.
``GET /api/v1/command/help`` — Flat help text.

Ported from lighterbird's command dispatch pattern.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from semantika.server.command.errors import CommandError, CommandNotFound, CommandValidationError
from semantika.server.command.models import CommandRequest, CommandResponse

router = APIRouter(tags=["command"])

# ── Interactive command form mapping ──────────────────────────────────────
_INTERACTIVE_FORMS: dict[str, str] = {
    "node.add": "node-add",
    "predicate.add": "predicate-add",
    "triple.add": "triple-add",
    "unit.add": "unit-add",
}


def _resolve_form_type(tokens: list[str]) -> str | None:
    for i in range(len(tokens), 1, -1):
        key = ".".join(tokens[:i])
        if key in _INTERACTIVE_FORMS:
            return _INTERACTIVE_FORMS[key]
    return None


# ── Command tree ─────────────────────────────────────────────────────────

def get_command_tree() -> list[dict]:
    """Return the full structured command tree for autocomplete."""
    return [
        {
            "name": "node",
            "description": "Manage knowledge graph nodes",
            "children": [
                {"name": "list", "description": "List all nodes", "params": [{"name": "limit", "type": "number", "default": 100}]},
                {"name": "search", "description": "Search nodes by label", "params": [{"name": "q", "type": "string", "required": True}]},
                {"name": "view", "description": "View a node and its triples", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a new node", "interactive": True, "params": [{"name": "labels", "type": "string"}]},
                {"name": "delete", "description": "Delete a node", "params": [{"name": "id", "type": "string", "required": True}]},
            ],
        },
        {
            "name": "predicate",
            "description": "Manage predicates (semantic properties)",
            "children": [
                {"name": "list", "description": "List all predicates"},
                {"name": "search", "description": "Search predicates", "params": [{"name": "q", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a predicate", "interactive": True, "params": [{"name": "predicate_id", "type": "string", "required": True}]},
                {"name": "update", "description": "Update a predicate", "params": [
                    {"name": "predicate_id", "type": "string", "required": True},
                    {"name": "labels", "type": "string"},
                ]},
                {"name": "delete", "description": "Delete a predicate", "params": [
                    {"name": "predicate_id", "type": "string", "required": True},
                ]},
            ],
        },
        {
            "name": "triple",
            "description": "Manage subject-predicate-object arcs",
            "children": [
                {"name": "list", "description": "List all triples"},
                {"name": "add", "description": "Add a triple", "interactive": True, "params": [
                    {"name": "subject_id", "type": "string", "required": True},
                    {"name": "predicate_id", "type": "string", "required": True},
                    {"name": "object_value", "type": "string", "required": True},
                ]},
            ],
        },
        {
            "name": "unit",
            "description": "Manage unit ontology",
            "children": [
                {"name": "list", "description": "List all units"},
                {"name": "view", "description": "View unit details", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "resolve", "description": "Resolve a unit expression", "params": [{"name": "expr", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a custom unit", "interactive": True},
            ],
        },
        {
            "name": "search",
            "description": "Full-text search across the graph",
            "params": [{"name": "q", "type": "string", "required": True}],
        },
        {"name": "export", "description": "Export graph in Turtle format"},
        {"name": "import", "description": "Import Turtle (.ttl) data", "params": [{"name": "data", "type": "string", "required": True}]},
        {"name": "stats", "description": "Show graph statistics"},
        {
            "name": "review",
            "description": "Spaced-repetition flashcard review",
            "children": [
                {"name": "start", "description": "Start a review session"},
                {"name": "sessions", "description": "List past review sessions"},
            ],
        },
    ]


# ── Tree-based command resolution ────────────────────────────────────────

def _resolve_command_path(
    tokens: list[str],
    tree: list[dict],
) -> tuple[list[str], list[str], dict] | None:
    """Walk the command tree to separate path tokens from positional params.

    Returns (cmd_tokens, remaining_tokens, merged_flags) or None if no match.
    Extra positional tokens are injected into *merged_flags* using param names
    defined on the leaf node.
    """
    cmd_tokens: list[str] = []
    remaining = list(tokens)
    current_level = tree
    leaf_node = None

    while remaining and current_level:
        token = remaining[0].lower()
        matched = None
        for child in current_level:
            if child["name"].lower() == token:
                matched = child
                break
        if not matched:
            break
        cmd_tokens.append(remaining.pop(0))
        if matched.get("children"):
            current_level = matched["children"]
        else:
            leaf_node = matched
            break

    if not cmd_tokens:
        return None

    # Remaining tokens become positional params
    params = leaf_node.get("params") if leaf_node else []
    merged = {}
    param_idx = 0
    for val in remaining:
        if param_idx < len(params):
            merged[params[param_idx]["name"]] = val
            param_idx += 1
        else:
            # Extra positional — store with numeric key
            merged[f"_{param_idx}"] = val
            param_idx += 1

    # Command flags override positional auto-fill
    return cmd_tokens, remaining, merged


# ── Dispatch ─────────────────────────────────────────────────────────────

def _dispatch(tokens: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """Dispatch a command to the appropriate handler."""
    from semantika.graph.db import get_services

    # Resolve command path using the tree
    resolved = _resolve_command_path(tokens, get_command_tree())
    if resolved is None:
        raise CommandNotFound(tokens)
    cmd_tokens, remaining, positional = resolved

    # Merge: explicitly provided flags override positional auto-detection
    merged = {**positional, **flags}
    path = ".".join(cmd_tokens).lower()
    svc = get_services()

    if path == "stats":
        return {"type": "status", "data": svc["triple"].get_stats()}

    if path == "export":
        ttl = svc["triple"].export_turtle()
        return {"type": "status", "data": {"ttl": ttl[:500] + "..." if len(ttl) > 500 else ttl}}

    if path == "import":
        ttl_content = merged.get("data") or (remaining and remaining[0]) or ""
        if not ttl_content:
            raise CommandValidationError("Provide TTL content via data= flag")
        from semantika.graph.triple_turtle import import_turtle as _import
        stats = _import(ttl_content)
        return {"type": "status", "data": stats}

    if path == "search":
        q = merged.get("q") or ""
        if not q:
            raise CommandValidationError("Enter a search query")
        nodes = svc["node"].search(q)
        return {"type": "table", "data": nodes, "label": f"Search: {q}"}

    if path == "node.list":
        nodes = svc["node"].list(limit=int(merged.get("limit", 100)))
        return {"type": "table", "data": nodes, "label": "Nodes"}

    if path == "node.search":
        q = merged.get("q", "")
        if not q:
            raise CommandValidationError("Enter a search term")
        nodes = svc["node"].search(q)
        return {"type": "table", "data": nodes, "label": f"Nodes matching '{q}'"}

    if path == "node.view":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        node = svc["node"].resolve_node_id_prefix(node_id)
        if not node:
            raise CommandValidationError(f"Node not found: {node_id}")
        triples = svc["triple"].get_by_subject(node["node_id"])
        node["triples"] = triples
        return {"type": "status", "data": node}

    if path == "node.add":
        labels_raw = merged.get("labels") or (remaining and remaining[0]) or ""
        payload = {"labels": {"en": labels_raw}} if labels_raw else {"labels": {}}
        try:
            node = svc["node"].create(payload)
            msg = f"Created node {node['node_id']}"
            if labels_raw:
                msg += f" with label \"{labels_raw}\""
            return {"type": "status", "data": {"message": msg, "node": node}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "node.delete":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        svc["node"].delete(node_id, soft=True)
        return {"type": "status", "data": {"message": f"Deleted {node_id}"}}

    if path == "predicate.list":
        preds = svc["predicate"].list()
        return {"type": "table", "data": preds, "label": "Predicates"}

    if path == "predicate.search":
        q = merged.get("q", "")
        results = svc["predicate"].search(q)
        return {"type": "table", "data": results, "label": f"Predicates matching '{q}'"}

    if path == "predicate.update":
        pred_id = merged.get("predicate_id") or ""
        labels_raw = merged.get("labels") or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        payload = {}
        if labels_raw:
            try:
                labels_dict = json.loads(labels_raw) if labels_raw.startswith("{") else {"en": labels_raw}
            except json.JSONDecodeError:
                labels_dict = {"en": labels_raw}
            payload["labels"] = labels_dict
        try:
            pred = svc["predicate"].update(pred_id, payload)
            return {"type": "status", "data": {"message": f"Updated {pred_id}"}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate.delete":
        pred_id = merged.get("predicate_id") or (remaining and remaining[0]) or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        svc["triple"].remove(predicate_id=pred_id)
        svc["predicate"].delete(pred_id, soft=True)
        return {"type": "status", "data": {"message": f"Deleted {pred_id}"}}

    if path == "predicate.add":
        pred_id = merged.get("predicate_id") or (remaining and remaining[0]) or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        try:
            pred = svc["predicate"].create({"predicate_id": pred_id, "labels": {"en": pred_id}})
            return {"type": "status", "data": {"message": f"Created predicate {pred['predicate_id']}", "predicate": pred}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "triple.list":
        triples = svc["triple"].db.execute("SELECT * FROM triples ORDER BY subject_id, predicate_id LIMIT ?", (100,))
        return {"type": "table", "data": triples, "label": "Triples"}

    if path == "triple.add":
        subject_id = merged.get("subject_id") or (remaining and remaining[0]) or ""
        predicate_id = merged.get("predicate_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        object_value = merged.get("object_value") or (remaining and remaining[2] if len(remaining) > 2 else "") or ""
        if not subject_id or not predicate_id or not object_value:
            raise CommandValidationError("Specify subject_id, predicate_id, and object_value")
        try:
            triple = svc["triple"].add(subject_id, predicate_id, object_value, object_type="uri")
            return {"type": "status", "data": {"message": f"Added triple: {subject_id} → {predicate_id} → {object_value}", "triple": triple}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "unit.list":
        from semantika.graph.unit_service import UnitService
        us = UnitService(svc["node"].db, svc["node"], svc["triple"])
        units = us.list_units()
        return {"type": "table", "data": units, "label": "Units"}

    if path == "unit.view":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        from semantika.graph.unit_service import UnitService
        us = UnitService(svc["node"].db, svc["node"], svc["triple"])
        info = us.get_unit_info(node_id)
        if not info:
            raise CommandValidationError(f"Unit not found: {node_id}")
        return {"type": "status", "data": info}

    if path == "unit.resolve":
        expr = merged.get("expr") or (remaining and remaining[0]) or ""
        from semantika.graph.unit_service import UnitService
        us = UnitService(svc["node"].db, svc["node"], svc["triple"])
        nid = us.resolve_unit(expr)
        info = us.get_unit_info(nid)
        return {"type": "status", "data": {"resolved": nid, "info": info}}

    if path == "review.start":
        session = svc["review"].create_session()
        return {"type": "status", "data": session}

    if path == "review.sessions":
        sessions = svc["review"].list_sessions()
        return {"type": "table", "data": sessions, "label": "Review Sessions"}

    raise CommandNotFound(tokens)


# ── Routes ───────────────────────────────────────────────────────────────

@router.post("", response_model=CommandResponse)
def execute_command(req: CommandRequest) -> dict[str, Any]:
    """Execute a parsed command and return structured output."""
    try:
        if "form" in req.flags:
            form_type = _resolve_form_type(req.tokens)
            if form_type:
                return {
                    "type": "form-required",
                    "title": f"Complete {form_type.replace('-', ' ').title()}",
                    "data": {"form": form_type, "initialData": req.flags},
                }

        result = _dispatch(req.tokens, req.flags)
        return {"type": result.get("type", "status"), "title": result.get("title", ""), "data": result.get("data", result)}
    except CommandNotFound as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CommandValidationError as e:
        form_type = _resolve_form_type(req.tokens)
        if form_type:
            return {"type": "form-required", "title": f"Complete {form_type.replace('-', ' ').title()}", "data": {"form": form_type, "initialData": req.flags, "message": str(e)}}
        raise HTTPException(status_code=400, detail={"error": str(e), "suggestion": getattr(e, "suggestion", "")})
    except CommandError as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "suggestion": getattr(e, "suggestion", "")})


@router.get("/tree")
def command_tree() -> list[dict]:
    """Return the full structured command tree for autocomplete."""
    return get_command_tree()


@router.get("/help")
def help_text() -> dict:
    """Return flat help text."""
    return {
        "commands": [
            {"cmd": "!node list/search/view/add/delete", "desc": "Manage nodes"},
            {"cmd": "!predicate list/search/add", "desc": "Manage predicates"},
            {"cmd": "!triple list/add", "desc": "Manage triples"},
            {"cmd": "!unit list/view/resolve/add", "desc": "Unit ontology"},
            {"cmd": "!search <q>", "desc": "Full-text search"},
            {"cmd": "!export", "desc": "Export as Turtle"},
            {"cmd": "!stats", "desc": "Graph statistics"},
            {"cmd": "!review start/sessions", "desc": "Flashcard review"},
            {"cmd": "!ask <question>", "desc": "Ask the LLM about the graph"},
        ]
    }
