"""Command dispatch API route.

``POST /api/v1/command`` — Execute a parsed command token list.
``GET /api/v1/command/tree`` — Return the auto-generated command tree.
``GET /api/v1/command/help`` — Auto-generated command reference (grouped, with optional ``?cmd=`` filter).

Command handlers are registered via ``@command()`` decorators in
``semantika.server.command.handlers.*`` and dispatched by
``semantika.server.command.registry``.

Replaces the monolithic 1987-line command.py with a thin route layer.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

# Side-effect: trigger @command decorator registration
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.errors import (
    CommandError,
    CommandNotFound,
    CommandValidationError,
)
from semantika.server.command.models import CommandRequest, CommandResponse
from semantika.server.command.registry import (
    dispatch,
    get_command_definitions,
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
def help_text(cmd: str | None = None) -> dict:
    """Return auto-generated command reference.

    Replaces the old hardcoded list with dynamic content sourced from
    ``@command()`` decorator metadata (via ``get_command_definitions()``).

    Args:
        cmd: Optional dot-separated command path (e.g. ``node.add``)
             to return details for a single command.
    """
    defs = get_command_definitions()

    if cmd:
        target = cmd.lower().split(".")
        for entry in defs:
            if [p.lower() for p in entry["path"]] == target:
                return {"type": "help", "command": entry}
        return {"type": "help", "error": f"Command '{cmd}' not found"}

    groups: dict[str, list[dict]] = {}
    for entry in defs:
        domain = entry["path"][0] if entry["path"] else "general"
        groups.setdefault(domain, []).append(entry)

    return {
        "type": "help",
        "groups": dict(sorted(groups.items())),
        "total": len(defs),
        "group_count": len(groups),
    }
