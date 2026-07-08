"""API routes for file-based prompt commands (/ prefix).

Provides three endpoints:
- GET  /api/v1/prompt-commands/list      — autocomplete source
- POST /api/v1/prompt-commands/expand    — preview expanded template
- POST /api/v1/prompt-commands/execute   — expand + send to LLM (sync JSON)
- POST /api/v1/prompt-commands/execute/stream — SSE streaming
- POST /api/v1/prompt-commands/execute/resume — resume paused execution

Port of lighterbird's ``routes/prompt_commands.py``.

Tool-calling flow and helper functions live in sibling modules
``prompt_commands_flow.py`` and ``prompt_commands_helpers.py``
to keep each file under 500 lines (per AGENTS.md convention).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lightercore.paths import config_dir
from lightercore.prompt_commands import (
    expand_prompt_template,
    list_prompt_commands,
    load_prompt_command,
)

from semantika.server.llm.provider import get_provider
from semantika.server.routes.prompt_commands_flow import (
    execute_template_flow,
    execute_with_tools,
    resume_execution,
)
from semantika.server.routes.prompt_commands_helpers import (
    build_prompt_messages,
    commands_dir,
    parse_tool_domains,
    render_markdown,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prompt-commands", tags=["prompt-commands"])


# ── GET /list ────────────────────────────────────────────────────────────────


@router.get("/list")
async def list_commands_endpoint() -> list[dict[str, Any]]:
    """Return all available prompt commands (name + description).

    Used by the frontend for autocomplete.
    """
    from pathlib import Path
    cmds = list_prompt_commands(Path(commands_dir()))
    return [
        {"name": c.name, "description": c.description, "param_count": c.param_count}
        for c in cmds
    ]


# ── POST /expand ─────────────────────────────────────────────────────────────


@router.post("/expand")
async def expand_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand a prompt command template with positional args.

    Returns 404 if the command file does not exist.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    from pathlib import Path
    cmd = load_prompt_command(Path(commands_dir()), name)
    if cmd is None:
        available = [c.name for c in list_prompt_commands(Path(commands_dir()))]
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


# ── POST /execute ────────────────────────────────────────────────────────────


@router.post("/execute")
async def execute_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand a prompt command and execute with multi-round tool-calling.

    The LLM receives the expanded template plus tool definitions for all
    registered ``!commands``.  It can call tools (search nodes, create
    predicates, add triples, etc.), get real results, and iterate until
    it produces a final text answer.

    Write and destructive tool calls (add, update, delete, merge, reset) are
    gated behind user confirmation via ``/execute/resume`` (human-in-the-loop).
    READ-level commands (search, list, view, stats) pass through without
    confirmation.

    Special case ``/template`` has its own two-turn flow.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    # Special case: /template uses its own flow
    if name.lower() == "template":
        return await execute_template_flow(data)

    # Standard flow: expand template + multi-round tool-calling
    from pathlib import Path
    cmd = load_prompt_command(Path(commands_dir()), name)
    if cmd is None:
        available = [c.name for c in list_prompt_commands(Path(commands_dir()))]
        raise HTTPException(
            status_code=404,
            detail=(
                f"Prompt command '{name}' not found. "
                f"Available: {', '.join(available) or '(none)'}"
            ),
        )

    expanded = expand_prompt_template(cmd.template, args)

    # Parse tool domain declaration from YAML frontmatter first,
    # then fall back to ``# +tools:`` comment in template body.
    allowed_domains = parse_tool_domains(cmd.template, frontmatter_tools=cmd.tools)

    provider = get_provider()
    if not provider.available:
        return {
            "type": "status",
            "title": f"/{name}",
            "data": {
                "message": (
                    "LLM not configured. "
                    "Use !llm configure or set up a provider in Settings."
                ),
            },
        }

    result = await execute_with_tools(expanded, name, allowed_domains=allowed_domains)

    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        html = render_markdown(reply)
        return {
            "type": "chat",
            "title": f"/{name}",
            "data": {"html": html, "actions": []},
        }

    return {
        "type": "chat",
        "title": f"/{name}",
        "data": {"html": "<p><em>(empty response)</em></p>", "actions": []},
    }


# ── POST /execute/resume ─────────────────────────────────────────────────────


@router.post("/execute/resume", status_code=200)
async def resume_execution_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Resume a paused prompt command execution after user confirmation.

    Called by the frontend after the user reviews the pending tool batch
    in the confirmation modal.

    Request body:
        session_id (str): The session UUID from ``confirm_tool`` response.
        confirmed (bool, optional): Apply this decision to ALL tools in
            the batch. ``true`` = approve all, ``false`` = reject all.
        decisions (dict[int, bool], optional): Per-tool-index approval,
            e.g. ``{0: true, 1: false, 2: true}``.  Overrides
            ``confirmed`` when present.

    Returns:
        Either a final ``{"type": "chat", ...}`` response, or another
        ``{"type": "confirm_tool", ...}`` if further tools need approval.
    """
    return await resume_execution(data)


# ── POST /execute/stream (SSE) ───────────────────────────────────────────────


@router.post("/execute/stream")
async def execute_stream_endpoint(data: dict[str, Any]) -> StreamingResponse:
    """Streaming variant of ``/execute`` — returns SSE.

    Streams tokens as ``data: {"token": "..."}`` events, terminated by
    ``data: [DONE]``.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    from pathlib import Path
    cmd = load_prompt_command(Path(commands_dir()), name)

    async def event_stream():
        if cmd is None:
            available = [c.name for c in list_prompt_commands(Path(commands_dir()))]
            msg = (
                f"Prompt command '{name}' not found. "
                f"Available: {', '.join(available) or '(none)'}"
            )
            yield f"data: {json.dumps({'token': msg})}\n\n"
            yield "data: [DONE]\n\n"
            return

        expanded = expand_prompt_template(cmd.template, args)

        provider = get_provider()
        if not provider.available:
            yield f"data: {json.dumps({'token': 'LLM not configured. Use !llm configure or set up a provider in Settings.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            messages = build_prompt_messages(expanded)
            result = await provider.chat(messages, stream=True)
            if hasattr(result, "__aiter__"):
                async for token in result:
                    yield f"data: {json.dumps({'token': token})}\n\n"
            else:
                yield f"data: {json.dumps({'token': str(result)})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'token': f'Error: {exc}'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
