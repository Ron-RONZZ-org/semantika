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

    # Parse tool domain declaration from template (``# +tools: node, predicate``)
    # so the LLM only sees relevant tools instead of all 91.
    allowed_domains = _parse_tool_domains(cmd.template)

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
    allowed_domains: set[str] | None = None,
) -> str | dict | None:
    """Run the expanded prompt through a multi-round tool-calling loop.

    The LLM sees the expanded template plus tool definitions for all
    registered ``!commands`` (or a subset filtered by *allowed_domains*).
    It can call tools, get real results via ``dispatch``, and iterate
    until it produces a final text answer.

    Args:
        expanded: The expanded prompt command template.
        name: The command name (for error messages).
        max_rounds: Maximum tool-calling iterations before giving up.
        allowed_domains: If set, only include tools whose first path
            segment is in this set (e.g. ``{"node", "predicate"}``).
            ``None`` means include all tools.

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
    if allowed_domains is not None:
        # Only include tools from declared domains, excluding bare group nodes
        # (no params, no flags, empty description — pure tree scaffolding).
        defs = [
            d for d in defs
            if d["path"][0] in allowed_domains
            and not (
                not d.get("params") and not d.get("flags")
                and not d.get("description", "").strip()
            )
        ]
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

        # ── Append the assistant message with tool_calls ──────────────
        # Required by the OpenAI/DeepSeek protocol: every ``role: "tool"``
        # message must be preceded by a ``role: "assistant"`` message
        # whose ``tool_calls`` array contains a matching ``id``.
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": result.content,
        }
        if result.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.get("name", ""),
                        "arguments": tc.function.get("arguments", "{}"),
                    },
                }
                for tc in result.tool_calls
            ]
        messages.append(assistant_msg)

        # Process tool calls in this batch
        write_batch: list[dict] = []
        for idx, tc in enumerate(result.tool_calls):
            path, flags = _tc_path(tc)
            level = get_command_level(path) if _is_registered(path) else None

            # Collect write+ tools for user review.  READ tools execute
            # immediately without confirmation.
            if level is not None and level >= PermissionLevel.WRITE:
                write_batch.append({
                    "index": idx,
                    "tokens": path.split("."),
                    "flags": flags,
                    "description": _resolve_command_desc(path),
                })
                continue

            # READ-level tool: execute immediately
            try:
                cmd_result = dispatch_path(path, flags)
            except CommandError as exc:
                cmd_result = {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(_sanitize_tool_result(cmd_result)),
            })

        # If there are pending write+ tools, gate them behind user review
        if write_batch:
            session_id = str(uuid.uuid4())
            _pending_executions[session_id] = {
                "messages": list(messages),
                "tool_calls": result.tool_calls,
                "tools": tools,
                "name": name,
                "write_indices": {w["index"] for w in write_batch},
            }

            first = write_batch[0]
            total = len(write_batch)
            return {
                "type": "confirm_tool",
                "session_id": session_id,
                "tokens": first["tokens"],
                "flags": first["flags"],
                "batch": write_batch,
                "message": (
                    f"The LLM wants to perform **{total}** operation(s). "
                    f"Review and approve individually below.\n\n"
                    f"First: `!{' '.join(first['tokens'])}`\n"
                    f"{first['description']}"
                ),
            }

    logger.warning("Tool-calling loop exhausted for /%s (max %d rounds)", name, max_rounds)
    return None


@router.post("/execute/resume", status_code=200)
async def resume_execution(data: dict[str, Any]) -> dict[str, Any]:
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
    session_id = data.get("session_id", "")

    if session_id not in _pending_executions:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    state = _pending_executions.pop(session_id)
    messages: list[dict] = state["messages"]
    tool_calls: list[ToolCall] = state["tool_calls"]
    tools: list[dict] = state["tools"]
    name: str = state["name"]
    write_indices: set[int] = state["write_indices"]

    # Resolve decisions: per-index map takes precedence, fall back to
    # blanket ``confirmed`` flag.
    raw_decisions: dict = data.get("decisions", {})
    if raw_decisions:
        decisions = {int(k): bool(v) for k, v in raw_decisions.items()}
    else:
        blanket = data.get("confirmed", False)
        decisions = {idx: blanket for idx in write_indices}

    # Process ALL tools in the batch, executing approved ones and
    # recording rejections for declined ones.
    for idx, tc in enumerate(tool_calls):
        path, flags = _tc_path(tc)

        if idx in write_indices:
            # Write+ tool: gate behind user decision
            approved = decisions.get(idx, False)
            if approved:
                try:
                    cmd_result = dispatch_path(path, flags)
                except CommandError as exc:
                    cmd_result = {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}
            else:
                cmd_result = {"error": f"User rejected !{' '.join(path.split('.'))}"}
        else:
            # READ tool already executed in _run_tool_loop — skip
            continue

        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(_sanitize_tool_result(cmd_result)),
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
    "call tools to create, read, and update graph data.\n\n"
    "## What Semantika Is\n"
    "Semantika stores structured knowledge as:\n"
    "- **Nodes** \u2014 entities or concepts (e.g. a book, a person, an idea)\n"
    "- **Predicates** \u2014 relationship types between nodes (e.g. author, theme)\n"
    "- **Triples** \u2014 subject-predicate-object statements\n\n"
    "## How to Use Tools\n"
    "- **Batch operations**: You can return MULTIPLE tool calls in a "
    "single response. If you need to create 3 nodes, call ``node_add`` "
    "three times in one response \u2014 do NOT create them one at a time.\n"
    "- **Plan first**: Decide everything you need before calling tools, "
    "then batch all independent calls in a single round.\n"
    "- **Prefer update over delete+recreate**: If a node needs a different "
    "label, use ``node_update`` instead of deleting and re-creating.\n"
    "- **Stop when done**: Once you have created/fetched all the data the "
    "user asked for, produce a final text answer. Do NOT keep calling "
    "tools after the task is complete \u2014 just write your response.\n\n"
    "## How to Respond\n"
    "- Keep responses concise and helpful. Use Markdown formatting.\n"
    "- Never invent data. If you truly have no data, say so clearly.\n"
    "- When you have completed the user's request, output a plain text "
    "answer summarizing what you did. That signals the task is done."
)

# ── User AGENTS.md (additional context loaded from config) ──────────────────


def _load_user_prompt() -> str:
    """Load the user's ``~/.config/semantika/AGENTS.md`` file.

    This file provides additional context / instructions that the user
    wants injected into every prompt command.  It is **appended** to the
    base ``_SEMANTIKA_SYSTEM_PROMPT``, so the user does not need to
    duplicate the base prompt.

    The file is auto-seeded on first run with a template explaining its
    purpose.  The user can edit it freely.
    """
    from pathlib import Path
    from lightercore.system_prompt import SystemPromptManager

    default_agents = (
        "# AGENTS.md \u2014 Additional context for Semantika AI\n\n"
        "This file is loaded automatically and appended to the system prompt "
        "for all prompt commands (``/``).  Use it to add your personal "
        "naming conventions, style preferences, or workflow rules.\n\n"
        "## Example\n"
        "```\n"
        "When creating nodes:\n"
        "- Always provide labels in eo, fr, en\n"
        "- Node ID from Esperanto label, uppercased, ASCII-normalised\n"
        "- Predicate IDs: rs:xxx with Esperanto word\n"
        "```\n"
    )
    mgr = SystemPromptManager(
        Path(str(config_dir())),
        filename="AGENTS.md",
    )
    return mgr.load(default_agents)


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


def _is_registered(path: str) -> bool:
    """Check whether a dot-separated command path is registered."""
    return get_handler_metadata(path) is not None


def _sanitize_tool_result(result: dict) -> dict:
    """Recursively parse JSON-encoded strings inside dispatch results.

    The dispatch result often contains DB rows where JSON fields like
    ``labels``, ``definitions``, ``descriptions``, ``aliases`` are stored
    as JSON-encoded strings (e.g. ``'{"en": "Alice"}'``).  When the tool
    loop sends this back to the LLM via ``json.dumps(result)``, the inner
    JSON gets double-escaped and becomes unreadable.

    This function walks the result dict and converts any parseable JSON
    string values into their parsed form so the LLM sees clean objects.
    """
    import json as _json

    def _walk(value):
        if isinstance(value, dict):
            return {k: _walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(v) for v in value]
        if isinstance(value, str) and len(value) > 1:
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    parsed = _json.loads(stripped)
                    return _walk(parsed)
                except (_json.JSONDecodeError, ValueError):
                    pass
        return value

    return _walk(result)


def _parse_tool_domains(template: str) -> set[str] | None:
    """Parse tool domain declaration from a prompt command template.

    Looks for lines matching ``# +tools: domain1, domain2`` in the
    template body.  The domains are the first segment of command paths
    (e.g. ``node``, ``predicate``, ``triple``, ``graph``).

    Returns:
        A set of domain strings, or ``None`` if no declaration is found
        (meaning include all tools).
    """
    import re
    for line in template.split("\n"):
        stripped = line.strip()
        match = re.match(r"^#\s*\+tools:\s*(.+)$", stripped, re.IGNORECASE)
        if match:
            domains = {d.strip().lower() for d in match.group(1).split(",") if d.strip()}
            return domains if domains else None
    return None


def _render_markdown(text: str) -> str:
    """Render markdown text to HTML using mistune."""
    import mistune

    return mistune.html(text)


def _build_prompt_messages(expanded: str) -> list[dict]:
    """Build messages with Semantika system context for prompt commands.

    Combines the base system prompt with the user's ``AGENTS.md``
    (if present), then appends the expanded prompt command template
    as the user message.
    """
    user_prompt = _load_user_prompt()
    if user_prompt:
        full_system = _SEMANTIKA_SYSTEM_PROMPT + "\n\n" + user_prompt
    else:
        full_system = _SEMANTIKA_SYSTEM_PROMPT

    return [
        {"role": "system", "content": full_system},
        {"role": "user", "content": expanded},
    ]
