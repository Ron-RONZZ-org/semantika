"""Command dispatch API route.

``POST /api/v1/command`` — Execute a parsed command token list.
``GET /api/v1/command/tree`` — Return the auto-generated command tree.
``GET /api/v1/command/help`` — Flat help text.

Command handlers are registered via ``@command()`` decorators in
``semantika.server.command.handlers.*`` and dispatched by
``semantika.server.command.registry``.

Replaces the monolithic 1987-line command.py with a thin route layer.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

# Side-effect: trigger @command decorator registration
from semantika.server.command import handlers  # noqa: F401

from semantika.server.command.errors import CommandError, CommandNotFound, CommandValidationError
from semantika.server.command.models import CommandRequest, CommandResponse
from semantika.server.command.registry import (
    dispatch,
    get_command_tree,
    resolve_form_type,
)

router = APIRouter(tags=["command"])


@router.post("", response_model=CommandResponse)
def execute_command(req: CommandRequest) -> dict:
    """Execute a parsed command and return structured output."""
    try:
        if "form" in req.flags:
            form_type = resolve_form_type(req.tokens)
            if form_type:
                return {
                    "type": "form-required",
                    "title": f"Complete {form_type.replace('-', ' ').title()}",
                    "data": {"form": form_type, "initialData": req.flags},
                }

        result = dispatch(req.tokens, req.flags)
        return {
            "type": result.get("type", "status"),
            "title": result.get("title", ""),
            "data": result.get("data", result),
        }
    except CommandNotFound as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CommandValidationError as e:
        form_type = resolve_form_type(req.tokens)
        if form_type:
            return {
                "type": "form-required",
                "title": f"Complete {form_type.replace('-', ' ').title()}",
                "data": {"form": form_type, "initialData": req.flags, "message": str(e)},
            }
        raise HTTPException(status_code=400, detail={"error": str(e), "suggestion": getattr(e, "suggestion", "")})
    except CommandError as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "suggestion": getattr(e, "suggestion", "")})


@router.get("/tree")
def command_tree() -> list[dict]:
    """Return the auto-generated command tree for autocomplete.

    Built dynamically from ``@command()`` decorator registrations.
    Never goes out of sync with available commands.
    """
    return get_command_tree()


@router.get("/help")
def help_text() -> dict:
    """Return flat help text."""
    return {
        "commands": [
            {"cmd": "!node list/search/view/add/update/delete/merge/rename", "desc": "Manage nodes"},
            {"cmd": "!predicate list/search/view/add/update/delete/rename", "desc": "Manage predicates"},
            {"cmd": "!predicate-group list/view/add/rename/delete/search", "desc": "Manage predicate groups"},
            {"cmd": "!triple list/add/delete/modify/view", "desc": "Manage triples"},
            {"cmd": "!unit list/view/resolve/decompose/add", "desc": "Unit ontology"},
            {"cmd": "!search <q> [--date-from] [--date-to]", "desc": "Full-text search with optional date filter"},
            {"cmd": "!view <id>", "desc": "View all triples for a node"},
            {"cmd": "!export [--output FILE] [--base-uri URI]", "desc": "Export as Turtle"},
            {"cmd": "!import <data>", "desc": "Import Turtle data"},
            {"cmd": "!stats", "desc": "Graph statistics"},
            {"cmd": "!proof add/view/delete", "desc": "Manage proofs"},
            {"cmd": "!review start/sessions/view/delete", "desc": "Flashcard review"},
            {"cmd": "!trash list/restore/delete/purge", "desc": "Trash management"},
            {"cmd": "!llm show/new/set/clear", "desc": "LLM provider configuration"},
            {"cmd": "!llm profile list/show/load/delete", "desc": "LLM profile management"},
            {"cmd": "!backup now/list/restore/prune", "desc": "Database backup"},
            {"cmd": "!backup config list/add/modify/delete", "desc": "Backup strategies"},
            {"cmd": "!backup export/import", "desc": "Portable data export/import"},
            {"cmd": "!reset [path] [--no-backup]", "desc": "Reset to fresh state (with optional backup)"},
            {"cmd": "!ask <question>", "desc": "Ask the LLM about the graph"},
        ]
    }
