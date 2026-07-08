"""API routes for file-based prompt commands (/ prefix).

Provides three endpoints:
- GET  /api/v1/prompt-commands/list      — autocomplete source
- POST /api/v1/prompt-commands/expand    — preview expanded template
- POST /api/v1/prompt-commands/execute   — expand + send to LLM (sync JSON)
- POST /api/v1/prompt-commands/execute/stream — SSE streaming

Port of lighterbird's ``routes/prompt_commands.py``.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lightercore.llm.base import ToolCall, defs_to_tools
from lightercore.paths import config_dir
from lightercore.permissions import PermissionLevel
from lightercore.prompt_commands import (
    expand_prompt_template,
    list_prompt_commands,
    load_prompt_command,
)

from semantika.server.command.errors import CommandError
from semantika.server.command.registry import (
    dispatch_path,
    get_command_definitions,
    get_command_level,
    get_handler_metadata,
)
from semantika.server.llm.provider import get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prompt-commands", tags=["prompt-commands"])


def _commands_dir() -> str:
    """Return the commands directory path (config_dir / 'commands')."""
    return str(config_dir() / "commands")


# ── GET /list ────────────────────────────────────────────────────────────────


@router.get("/list")
async def list_commands_endpoint() -> list[dict[str, Any]]:
    """Return all available prompt commands (name + description).

    Used by the frontend for autocomplete.
    """
    from pathlib import Path
    cmds = list_prompt_commands(Path(_commands_dir()))
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


# ── POST /execute ────────────────────────────────────────────────────────────


@router.post("/execute")
async def execute_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand a prompt command and execute with multi-round tool-calling.

    The LLM receives the expanded template plus tool definitions for all
    registered ``!commands``.  It can call tools (search nodes, create
    predicates, add triples, etc.), get real results, and iterate until
    it produces a final text answer.

    Destructive tool calls (delete, merge, reset) are gated behind user
    confirmation via ``/execute/resume`` (human-in-the-loop).  Write-level
    operations (add, update) are allowed because the user explicitly chose
    to run this prompt command.

    Special case ``/template`` has its own two-turn flow.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    # Special case: /template uses its own flow
    if name.lower() == "template":
        return await _execute_template_flow(data)

    # Standard flow: expand template + multi-round tool-calling
    from pathlib import Path
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

    result = await _execute_with_tools(expanded, name)

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


# ── /template two-turn flow ─────────────────────────────────────────────────


async def _execute_template_flow(data: dict[str, Any]) -> dict[str, Any]:
    """Two-turn flow for /template: search_plan → LLM YAML generation."""
    import json
    import re

    args = data.get("args", [])
    user_description = " ".join(args) if args else ""

    if not user_description:
        return {
            "type": "status",
            "title": "/template",
            "data": {"message": "Describe the template you want to create."},
        }

    provider = get_provider()
    if not provider.available:
        return {
            "type": "status",
            "title": "/template",
            "data": {
                "message": (
                    "LLM not configured. "
                    "Use !llm configure or set up a provider in Settings."
                ),
            },
        }

    # ── Turn 1: Ask LLM for predicate search keywords ──────────────────────
    turn1_prompt = (
        "You are a template generator for the Semantika knowledge graph. "
        "The user wants to create a reusable triple template.\n\n"
        "First, determine what predicates you need to search for. "
        "Respond with a JSON object listing search keywords:\n"
        '{"type": "search_plan", "keywords": ["keyword1", "keyword2", ...]}\n\n'
        "User description:\n" + user_description
    )

    try:
        turn1_result = await provider.chat(
            [{"role": "system", "content": _SEMANTIKA_SYSTEM_PROMPT},
             {"role": "user", "content": turn1_prompt}],
        )
    except Exception as exc:
        logger.exception("/template turn 1 failed")
        return {"type": "status", "title": "/template", "data": {"message": f"LLM call failed: {exc}"}}

    # Parse search plan from LLM response
    keywords = _parse_search_plan(turn1_result)
    if not keywords:
        # LLM didn't produce a search plan — try treating response as direct YAML
        yaml_content = _extract_yaml(turn1_result)
        if yaml_content:
            return {
                "type": "template_yaml",
                "title": "/template",
                "data": {
                    "yaml": yaml_content,
                    "description": user_description,
                },
            }
        return {
            "type": "chat",
            "title": "/template",
            "data": {"html": _render_markdown(turn1_result or "")},
        }

    # Execute predicate searches
    from semantika.graph.db import get_services
    svc = get_services()
    search_results: list[dict[str, str]] = []
    for kw in keywords:
        try:
            matches = svc["predicate"].search(kw, limit=5)
            for m in matches:
                search_results.append({
                    "keyword": kw,
                    "predicate_id": m.get("predicate_id", ""),
                    "label": _get_predicate_label(m),
                })
        except Exception:
            logger.debug("Predicate search failed for: %s", kw, exc_info=True)

    # ── Turn 2: Send search results + user description for YAML generation ─
    if search_results:
        found_summary = "Existing predicates found:\n"
        for r in search_results:
            found_summary += f"  - {r['predicate_id']} (matched keyword: {r['keyword']})\n"
    else:
        found_summary = "(No existing predicates matched — you may need to create new ones.)\n"

    turn2_prompt = (
        "You are a YAML template generator for the Semantika knowledge graph.\n\n"
        "Generate a triple template YAML from the user's description.\n\n"
        "## Schema\n"
        "```yaml\n"
        "name: <short-name>\n"
        "description: <short-description>\n"
        "params:\n"
        "  - name: <variable-name>\n"
        "    label: <human-label>\n"
        "    type: node | string | number\n"
        "    required: true\n"
        "triples:\n"
        '  - "{var1} {predicate1} {var2}"           # URI (node ref) — no flag\n'
        '  - "{var1} {predicate2} {var3} --str"     # string literal\n'
        '  - "{var1} {predicate3} {var4} --int"     # number literal\n'
        "```\n\n"
        "## Rules\n"
        "- No flag = URI reference (object is another node)\n"
        "- `--str` = string literal, `--int` = number literal\n"
        "- Optional params: if not filled, the triple is auto-skipped\n"
        "- Use PREDICATE IDs that ALREADY EXIST in your graph\n\n"
        "## " + found_summary + "\n"
        "## User description\n" + user_description + "\n\n"
        "Output ONLY the YAML code block — no explanation, no surrounding text."
    )

    try:
        turn2_result = await provider.chat(
            [{"role": "system", "content": _SEMANTIKA_SYSTEM_PROMPT},
             {"role": "user", "content": turn2_prompt}],
        )
    except Exception as exc:
        logger.exception("/template turn 2 failed")
        return {"type": "status", "title": "/template", "data": {"message": f"LLM call failed: {exc}"}}

    yaml_content = _extract_yaml(turn2_result) or turn2_result or ""
    return {
        "type": "template_yaml",
        "title": "/template",
        "data": {
            "yaml": yaml_content,
            "description": user_description,
        },
    }


# ── Multi-round tool-calling ─────────────────────────────────────────────────


# In-memory store for paused executions awaiting user confirmation.
# Keys are session UUIDs, values are the state dicts.
_pending_executions: dict[str, dict] = {}


async def _execute_with_tools(
    expanded: str,
    name: str,
    max_rounds: int = 20,
) -> str | dict | None:
    """Run the expanded prompt through a multi-round tool-calling loop.

    The LLM sees the expanded template plus tool definitions for all
    registered ``!commands``.  It can call tools, get real results via
    ``dispatch``, and iterate until it produces a final text answer.

    Args:
        expanded: The expanded prompt command template.
        name: The command name (for error messages).
        max_rounds: Maximum tool-calling iterations before giving up.

    Returns:
        - A ``str`` with the final answer on success.
        - A ``dict`` with ``{"type": "confirm_tool", ...}`` if a write or
          destructive tool needs human approval (see :func:`resume_execution`).
        - ``None`` if the LLM is unavailable or the loop exhausted.
    """
    provider = get_provider()
    if not provider.available:
        return None

    defs = get_command_definitions()
    tools = defs_to_tools(defs) if defs else []
    messages = _build_prompt_messages(expanded)

    return await _run_tool_loop(messages, tools, name, max_rounds)


def _tc_path(tc: ToolCall) -> tuple[str, dict[str, str]]:
    """Extract command path and flags from a tool call.

    Replaces the unnecessary tokenisation roundtrip
    (``split("_") → dispatch → join(".")``) with a direct
    ``replace("_", ".")`` conversion.

    Returns:
        ``(path, flags)`` — e.g. ``("node.search", {"q": "nostalgia"})``
    """
    name = tc.function.get("name", "")
    path = name.replace("_", ".")  # e.g. "node_search" → "node.search"
    raw_args = tc.function.get("arguments", "{}")
    try:
        flags = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except (json.JSONDecodeError, TypeError):
        flags = {}
    return path, flags


async def _run_tool_loop(
    messages: list[dict],
    tools: list[dict],
    name: str,
    max_rounds: int = 20,
) -> str | dict | None:
    """Inner tool loop — may be called from both the initial execution and
    after a resumption (see :func:`resume_execution`)."""
    provider = get_provider()

    for _round in range(max_rounds):
        try:
            result = await provider.chat_with_tools(messages, tools)
        except Exception:
            logger.exception("Tool-calling round failed for /%s", name)
            return None

        if result.tool_calls is None or not result.tool_calls:
            # Text response — final answer
            return result.content

        # Process tool calls in this batch
        for idx, tc in enumerate(result.tool_calls):
            path, flags = _tc_path(tc)

            # Check permission — gate destructive commands behind human approval.
            # Write-level operations (add, update, search) are allowed because
            # the user explicitly chose to run this prompt command.
            level = get_command_level(path) if _is_registered(path) else None
            if level is not None and level >= PermissionLevel.DESTRUCTIVE:
                session_id = str(uuid.uuid4())
                desc = _resolve_command_desc(path)
                tokens = path.split(".")

                _pending_executions[session_id] = {
                    "messages": list(messages),
                    "tool_calls": result.tool_calls,
                    "current_index": idx,
                    "tools": tools,
                    "name": name,
                }

                return {
                    "type": "confirm_tool",
                    "session_id": session_id,
                    "tokens": tokens,
                    "flags": flags,
                    "message": (
                        f"The LLM wants to run `!{' '.join(tokens)}`.\n\n"
                        f"{desc}\n\n"
                        "Approve this operation?"
                    ),
                }

            # READ-level tool: execute immediately via direct path dispatch
            try:
                cmd_result = dispatch_path(path, flags)
            except CommandError as exc:
                cmd_result = {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(cmd_result),
            })

    logger.warning("Tool-calling loop exhausted for /%s (max %d rounds)", name, max_rounds)
    return None


def _is_registered(path: str) -> bool:
    """Check whether a dot-separated command path is registered."""
    return get_handler_metadata(path) is not None


@router.post("/execute/resume", status_code=200)
async def resume_execution(data: dict[str, Any]) -> dict[str, Any]:
    """Resume a paused prompt command execution after user confirmation.

    Called by the frontend after the user approves or rejects a tool call
    in the confirmation modal.

    Request body:
        session_id (str): The session UUID from ``confirm_tool`` response.
        confirmed (bool): Whether the user approved the operation.

    Returns:
        Either a final ``{"type": "chat", ...}`` response, or another
        ``{"type": "confirm_tool", ...}`` if further tools need approval.
    """
    session_id = data.get("session_id", "")
    confirmed = data.get("confirmed", False)

    if session_id not in _pending_executions:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    state = _pending_executions.pop(session_id)
    messages: list[dict] = state["messages"]
    tool_calls: list[ToolCall] = state["tool_calls"]
    current_index: int = state["current_index"]
    tools: list[dict] = state["tools"]
    name: str = state["name"]

    # Process the current tool call based on user's choice
    tc = tool_calls[current_index]
    path, flags = _tc_path(tc)

    if confirmed:
        try:
            cmd_result = dispatch_path(path, flags)
        except CommandError as exc:
            cmd_result = {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}
    else:
        cmd_result = {"error": f"User rejected command !{'/'.join(path.split('.'))}"}

    messages.append({
        "role": "tool",
        "tool_call_id": tc.id,
        "content": json.dumps(cmd_result),
    })

    # Process any remaining tool calls from the same batch
    for remaining_tc in tool_calls[current_index + 1:]:
        r_path, r_flags = _tc_path(remaining_tc)
        r_level = get_command_level(r_path) if _is_registered(r_path) else None

        if r_level is not None and r_level >= PermissionLevel.DESTRUCTIVE:
            # Another confirmation needed before we can continue
            new_session_id = str(uuid.uuid4())
            desc = _resolve_command_desc(r_path)
            r_tokens = r_path.split(".")

            _pending_executions[new_session_id] = {
                "messages": list(messages),
                "tool_calls": tool_calls,
                "current_index": tool_calls.index(remaining_tc),
                "tools": tools,
                "name": name,
            }
            return {
                "type": "confirm_tool",
                "session_id": new_session_id,
                "tokens": r_tokens,
                "flags": r_flags,
                "message": (
                    f"The LLM wants to run `!{' '.join(r_tokens)}`.\n\n"
                    f"{desc}\n\n"
                    "Approve this operation?"
                ),
            }

        try:
            cmd_result = dispatch_path(r_path, r_flags)
        except CommandError as exc:
            cmd_result = {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}

        messages.append({
            "role": "tool",
            "tool_call_id": remaining_tc.id,
            "content": json.dumps(cmd_result),
        })

    # Continue the loop with the updated messages
    final = await _run_tool_loop(messages, tools, name)

    if isinstance(final, dict) and final.get("type") == "confirm_tool":
        return final

    reply = final if isinstance(final, str) and final.strip() else None
    if reply:
        return {
            "type": "chat",
            "title": f"/{name}",
            "data": {"html": _render_markdown(reply), "actions": []},
        }

    return {
        "type": "chat",
        "title": f"/{name}",
        "data": {"html": "<p><em>(command completed)</em></p>", "actions": []},
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_search_plan(text: str | None) -> list[str]:
    """Parse LLM response for a search_plan JSON object."""
    if not text:
        return []

    import re
    text = text.strip()
    # Try to find JSON block
    json_match = re.search(r'\{[^{}]*"type"\s*:\s*"search_plan"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            import json
            obj = json.loads(json_match.group())
            return obj.get("keywords", [])
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _extract_yaml(text: str | None) -> str | None:
    """Extract YAML content from a code-fenced block."""
    if not text:
        return None
    import re
    # Match ```yaml ... ``` or ```yml ... ``` or just ``` ... ```
    match = re.search(
        r"```(?:yaml|yml)?\s*\n(.*?)```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def _get_predicate_label(pred: dict) -> str:
    """Get the best human-readable label for a predicate."""
    labels = pred.get("labels", {}) or {}
    return labels.get("en", labels.get("eo", pred.get("predicate_id", "")))


def _resolve_command_desc(path: str) -> str:
    """Return the description of the command at *path*, or empty string."""
    meta = get_handler_metadata(path)
    if meta is None:
        return ""
    return meta.get("description", "")


_SEMANTIKA_SYSTEM_PROMPT = (
    "You are Semantika AI, the built-in assistant of the **Semantika "
    "knowledge graph** application. You run INSIDE the app and can "
    "execute commands to look up data the user asks about.\n\n"
    "## What Semantika Is\n"
    "Semantika stores structured knowledge as:\n"
    "- **Nodes** — entities or concepts\n"
    "- **Predicates** — relationship types between nodes\n"
    "- **Triples** — subject-predicate-object statements\n\n"
    "## Available Commands\n"
    "- `!node` — list, add, search, show, edit, delete, merge nodes\n"
    "- `!predicate` — list, add, search, show, edit, delete predicates\n"
    "- `!triple` — list, add, search, show, edit, delete triples\n"
    "- `!search` — full-text search\n"
    "- `!stats` — show graph statistics\n"
    "- `!export` — export as Turtle (.ttl)\n"
    "- `!unit` — manage units/ontology\n"
    "- `!backup` — backup management\n"
    "## How to Respond\n"
    "- Keep responses concise and helpful. Use Markdown formatting.\n"
    "- Never invent data. If you truly have no data, say so clearly."
)


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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _render_markdown(text: str) -> str:
    """Render markdown text to HTML using mistune."""
    import mistune

    return mistune.html(text)


def _build_prompt_messages(expanded: str) -> list[dict]:
    """Build messages with Semantika system context for prompt commands.

    All ``/`` commands now inherit the same system context as the chat
    endpoint, so the LLM understands what Semantika is and can
    reference graph concepts correctly.
    """
    return [
        {"role": "system", "content": _SEMANTIKA_SYSTEM_PROMPT},
        {"role": "user", "content": expanded},
    ]
