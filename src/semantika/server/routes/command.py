"""Command bar API — command metadata and dispatch."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# ── Command tree metadata ──────────────────────────────────────────────

COMMAND_TREE = {
    "commands": [
        {
            "path": "node add",
            "description": "Create a new node",
            "interactive": True,
            "params": [
                {"name": "labels", "type": "dict", "required": False},
                {"name": "definitions", "type": "dict", "required": False},
            ],
        },
        {
            "path": "node list",
            "description": "List all nodes",
            "interactive": False,
            "params": [{"name": "limit", "type": "int", "default": 100}],
        },
        {
            "path": "node view",
            "description": "View a node and its triples",
            "interactive": False,
            "params": [{"name": "id", "type": "str", "required": True}],
        },
        {
            "path": "node delete",
            "description": "Delete a node",
            "interactive": False,
            "params": [{"name": "id", "type": "str", "required": True}],
        },
        {
            "path": "node search",
            "description": "Search nodes by label",
            "interactive": False,
            "params": [{"name": "q", "type": "str", "required": True}],
        },
        {
            "path": "predicate add",
            "description": "Create a new predicate",
            "interactive": True,
            "params": [
                {"name": "predicate_id", "type": "str", "required": True},
                {"name": "labels", "type": "dict", "required": False},
            ],
        },
        {
            "path": "predicate list",
            "description": "List all predicates",
            "interactive": False,
        },
        {
            "path": "predicate search",
            "description": "Search predicates",
            "interactive": False,
            "params": [{"name": "q", "type": "str", "required": True}],
        },
        {
            "path": "triple add",
            "description": "Add a triple (subject predicate object)",
            "interactive": True,
            "params": [
                {"name": "subject_id", "type": "str", "required": True},
                {"name": "predicate_id", "type": "str", "required": True},
                {"name": "object_value", "type": "str", "required": True},
                {"name": "object_type", "type": "str", "default": "uri"},
            ],
        },
        {
            "path": "triple list",
            "description": "List triples",
            "interactive": False,
            "params": [{"name": "limit", "type": "int", "default": 100}],
        },
        {
            "path": "search",
            "description": "Full-text search across the graph",
            "interactive": False,
            "params": [{"name": "q", "type": "str", "required": True}],
        },
        {
            "path": "export",
            "description": "Export graph in Turtle format",
            "interactive": False,
        },
        {
            "path": "stats",
            "description": "Show graph statistics",
            "interactive": False,
        },
        {
            "path": "review start",
            "description": "Start a review session",
            "interactive": False,
        },
        {
            "path": "review next",
            "description": "Get next review question",
            "interactive": False,
        },
        {
            "path": "review sessions",
            "description": "List review sessions",
            "interactive": False,
        },
    ]
}


@router.get("/tree")
async def command_tree():
    """Return command metadata for frontend autocomplete."""
    return COMMAND_TREE


class ExecuteRequest(BaseModel):
    command: str = ""


@router.post("/execute")
async def execute_command(req: ExecuteRequest):
    """Parse and execute a !command.

    Returns a typed response: status, form-required, table, or error.
    """
    cmd = req.command.strip()
    parts = cmd.split()
    if not parts:
        return {"type": "error", "message": "Empty command"}

    prefix = parts[0].lower()

    try:
        if prefix == "stats":
            from semantika.graph.db import get_services
            stats = get_services()["triple"].get_stats()
            return {"type": "status", "data": stats}

        if prefix == "export":
            from semantika.graph.db import get_services
            ttl = get_services()["triple"].export_turtle()
            return {"type": "status", "data": {"ttl": ttl[:500] + "..." if len(ttl) > 500 else ttl}}

        if prefix in ("search", "s"):
            q = " ".join(parts[1:]) if len(parts) > 1 else ""
            if not q:
                return {"type": "form-required", "form": "search", "message": "Enter search query"}
            from semantika.graph.db import get_services
            nodes = get_services()["node"].search(q)
            return {"type": "table", "data": nodes, "label": f"Search results for '{q}'"}

        if prefix == "review":
            from semantika.graph.db import get_services
            if len(parts) > 1 and parts[1] == "sessions":
                sessions = get_services()["review"].list_sessions()
                return {"type": "table", "data": sessions, "label": "Review sessions"}
            session = get_services()["review"].create_session()
            return {"type": "status", "data": session}

        return {
            "type": "error",
            "message": f"Unknown command: {cmd}. Type !help to see available commands.",
        }
    except Exception as e:
        return {"type": "error", "message": str(e)}


@router.get("/help")
async def help_text():
    """Return help text for all commands."""
    return {
        "commands": [
            {"cmd": "!node add", "desc": "Create a node"},
            {"cmd": "!node list", "desc": "List nodes"},
            {"cmd": "!node view <id>", "desc": "View a node"},
            {"cmd": "!node delete <id>", "desc": "Delete a node"},
            {"cmd": "!node search <q>", "desc": "Search nodes"},
            {"cmd": "!predicate add", "desc": "Create a predicate"},
            {"cmd": "!predicate list", "desc": "List predicates"},
            {"cmd": "!predicate search <q>", "desc": "Search predicates"},
            {"cmd": "!triple add <s> <p> <o>", "desc": "Add a triple"},
            {"cmd": "!triple list", "desc": "List triples"},
            {"cmd": "!search <q>", "desc": "Full-text search"},
            {"cmd": "!export", "desc": "Export as Turtle"},
            {"cmd": "!stats", "desc": "Graph statistics"},
            {"cmd": "!review start", "desc": "Start review session"},
            {"cmd": "!review sessions", "desc": "List review sessions"},
            {"cmd": "!ask <question>", "desc": "Ask the LLM about the graph"},
        ]
    }
