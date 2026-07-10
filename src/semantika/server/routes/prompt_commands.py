"""API routes for file-based prompt commands (/ prefix).

Provides four endpoints:
- GET  /api/v1/prompt-commands/list      — autocomplete source
- POST /api/v1/prompt-commands/expand    — preview expanded template
- POST /api/v1/prompt-commands/execute   — expand + send to LLM (sync JSON)
- POST /api/v1/prompt-commands/execute/stream — SSE streaming
- POST /api/v1/prompt-commands/execute/resume — resume after HITL confirm

All heavy logic is in ``prompt_commands_helpers.py``.
"""

from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lightercore.prompt_commands import (
    expand_prompt_template,
    list_prompt_commands,
    load_prompt_command,
)

from semantika.server.llm.provider import get_provider
from semantika.server.routes.prompt_commands_helpers import (
    _build_prompt_messages,
    _commands_dir,
    _execute_with_tools,
    _parse_tool_domains,
    _render_markdown,
    execute_template_flow,
    resume_execution,
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
    """Expand a prompt command and execute with multi-round tool-calling."""
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    # Special case: /template uses its own flow
    if name.lower() == "template":
        return await execute_template_flow(data)

    # Standard flow: expand template + multi-round tool-calling
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

    # Parse tool domain declaration
    allowed_domains = _parse_tool_domains(cmd.template, frontmatter_tools=cmd.tools)

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

    result = await _execute_with_tools(expanded, name, allowed_domains=allowed_domains)

    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        html = _render_markdown(reply)
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
    """Streaming variant of ``/execute`` — returns SSE.

    Streams tokens as ``data: {"token": "..."}`` events, terminated by
    ``data: [DONE]``.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    cmd = load_prompt_command(Path(_commands_dir()), name)

    async def event_stream():
        if cmd is None:
            available = [c.name for c in list_prompt_commands(Path(_commands_dir()))]
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
            messages = _build_prompt_messages(expanded)
            result = await provider.chat(messages, stream=True)
            if inspect.isasyncgen(result):
                # Wrap in timeout to prevent hanging LLM connections
                import asyncio
                try:
                    async with asyncio.timeout(120):
                        async for token in result:
                            yield f"data: {json.dumps({'token': token})}\n\n"
                except TimeoutError:
                    yield f"data: {json.dumps({'token': 'Error: LLM streaming timed out after 120s'})}\n\n"
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
