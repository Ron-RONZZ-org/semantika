"""API routes for file-based prompt commands (/ prefix).

Endpoints:
- GET  /api/v1/prompt-commands/list      — autocomplete source
- POST /api/v1/prompt-commands/expand    — preview expanded template
- POST /api/v1/prompt-commands/execute   — expand + multi-round tool loop
- POST /api/v1/prompt-commands/execute/stream — SSE streaming
- POST /api/v1/prompt-commands/execute/resume — resume after HITL confirm

The execute endpoint uses lightercore's unified ``execute_prompt_command()``
for the full pipeline.  The ``/template`` special case redirects to the
semantika-specific two-turn template flow.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lighterllm.llm.base import defs_to_tools
from lighterllm.prompt_commands import (
    execute_prompt_command,
    expand_prompt_template,
    list_prompt_commands,
    load_prompt_command,
    prompt_command_event_stream,
)

from semantika.server.command.registry import (
    dispatch_path,
    get_command_definitions,
    get_command_level,
    get_handler_metadata,
)
from semantika.server.llm.provider import get_provider
from semantika.server.llm.system_prompt import load_system_prompt
from semantika.server.routes.prompt_commands_helpers import (
    _commands_dir,
    _render_markdown,
    execute_template_flow,
    resume_execution,
)
from semantika.server.routes.prompt_commands_text_to_triple import (
    execute_text_to_triple_flow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prompt-commands", tags=["prompt-commands"])


# ── GET /list ─────────────────────────────────────────────────────────


@router.get("/list")
async def list_commands_endpoint() -> list[dict[str, Any]]:
    """Return all available prompt commands (name + description).
    Used by the frontend for autocomplete.
    """
    cmds = list_prompt_commands(Path(_commands_dir()))
    return [
        {"name": c.name, "description": c.description, "param_count": c.param_count}
        for c in cmds
    ]


# ── POST /expand ───────────────────────────────────────────────────────


@router.post("/expand")
async def expand_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand a prompt command template with positional args.
    Returns 404 if the command file does not exist.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    cmd = load_prompt_command(Path(_commands_dir()), name)
    if cmd is None:
        available = [c.name for c in list_prompt_commands(Path(_commands_dir()))]
        raise HTTPException(
            status_code=404,
            detail=(
                f"Prompt command '{name}' not found. "
                f"Available: {', '.join(available) or '(none)'}"
            ),
        )

    expanded = expand_prompt_template(cmd.template, args)

    return {
        "name": cmd.name,
        "description": cmd.description,
        "template": cmd.template,
        "expanded": expanded,
        "param_count": cmd.param_count,
    }


# ── POST /execute ──────────────────────────────────────────────────────


@router.post("/execute")
async def execute_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand a prompt command and execute with multi-round tool-calling.

    Delegates to :func:`~lightercore.prompt_commands.execute_prompt_command`
    for the standard pipeline.  The ``/template`` command has its own
    two-turn flow.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    # Special cases: built-in multi-turn flows
    if name.lower() == "template":
        return await execute_template_flow(data)
    if name.lower() in ("text-to-triples", "text_to_triples", "ttt"):
        return await execute_text_to_triple_flow(data)

    # Dispatch wrapper that catches CommandError and extracts suggestion
    def _dispatch_path(path: str, flags: dict) -> dict:
        try:
            return dispatch_path(path, flags)
        except Exception as exc:
            from semantika.server.command.errors import CommandError
            if isinstance(exc, CommandError):
                return {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}
            return {"error": str(exc)}

    result = await execute_prompt_command(
        name=name,
        args=args,
        commands_dir=Path(_commands_dir()),
        provider=get_provider(),
        system_prompt_loader=load_system_prompt,
        definitions_loader=get_command_definitions,
        dispatch_fn=_dispatch_path,
        get_handler_metadata_fn=get_handler_metadata,
        get_command_level_fn=get_command_level,
        title_prefix="/",
    )

    if result.get("status_code"):
        raise HTTPException(
            status_code=result["status_code"],
            detail=result.get("detail", ""),
        )
    return result


# ── POST /execute/resume ───────────────────────────────────────────────


@router.post("/execute/resume", status_code=200)
async def resume_execution_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Resume a paused prompt command execution after user confirmation.

    Request body:
        session_id (str): The session UUID from ``confirm_tool`` response.
        confirmed (bool, optional): Apply this decision to ALL tools in
            the batch. ``true`` = approve all, ``false`` = reject all.
        decisions (dict[int, bool], optional): Per-tool-index approval.
        feedback (dict[int, str] | str, optional): User feedback for
            rejected tools. A dict maps tool index to feedback string;
            a string is applied to all rejected tools.
    """
    session_id = data.get("session_id", "")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required.")

    return await resume_execution(
        session_id=session_id,
        decisions=data.get("decisions"),
        confirmed=data.get("confirmed"),
        feedback=data.get("feedback"),
    )


# ── POST /execute/stream (SSE) ──────────────────────────────────────────


@router.post("/execute/stream")
async def execute_stream_endpoint(data: dict[str, Any]) -> StreamingResponse:
    """Streaming variant of ``/execute`` — SSE without tool-calling.

    Delegates to :func:`~lightercore.prompt_commands.prompt_command_event_stream`
    for the shared SSE generation.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    return StreamingResponse(
        prompt_command_event_stream(
            name=name,
            args=args,
            commands_dir=Path(_commands_dir()),
            provider=get_provider(),
            system_prompt_loader=load_system_prompt,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
