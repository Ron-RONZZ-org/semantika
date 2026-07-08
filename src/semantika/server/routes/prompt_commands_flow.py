"""Tool-calling flow and template execution for prompt commands.

Extracted from ``prompt_commands.py`` to keep each file under 500 lines
(per AGENTS.md convention).

Provides:
- ``_execute_template_flow`` — Two-turn LLM interaction for /template YAML generation.
- ``execute_with_tools`` — Run an expanded prompt through the multi-round tool loop.
- ``run_tool_loop`` — Inner loop: chat-with-tools → dispatch → repeat.
- ``resume_execution`` — Resume a paused prompt command after user confirmation.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import HTTPException
from lightercore.llm.base import ToolCall, defs_to_tools
from lightercore.permissions import PermissionLevel

from semantika.server.command.errors import CommandError
from semantika.server.command.registry import (
    dispatch_path,
    get_command_definitions,
    get_command_level,
)
from semantika.server.llm.provider import get_provider
from semantika.server.llm.system_prompt import SEMANTIKA_SYSTEM_PROMPT
from semantika.server.routes.prompt_commands_helpers import (
    build_prompt_messages,
    extract_yaml,
    get_predicate_label,
    is_registered,
    parse_search_plan,
    render_markdown,
    resolve_command_desc,
    sanitize_tool_result,
)

logger = logging.getLogger(__name__)


# ── In-memory store for paused executions (TTL-based eviction) ─────────────

# Keys are session UUIDs, values are state dicts with a ``created_at`` field.
# Expired entries are cleaned up on every resume attempt or lookup (TTL).
# Sessions are still lost on server restart; persist to disk for production.
_PENDING_TTL_SECONDS: int = 600  # 10 minutes
_pending_executions: dict[str, dict] = {}


def _cleanup_expired_sessions() -> int:
    """Remove expired sessions from the pending store.

    Returns:
        Number of removed sessions.
    """
    now = time.time()
    expired = [
        sid for sid, state in _pending_executions.items()
        if now - state.get("created_at", 0) > _PENDING_TTL_SECONDS
    ]
    for sid in expired:
        _pending_executions.pop(sid, None)
    if expired:
        logger.info("Cleaned up %d expired pending session(s)", len(expired))
    return len(expired)


# ── /template two-turn flow ────────────────────────────────────────────────


async def execute_template_flow(data: dict[str, Any]) -> dict[str, Any]:
    """Two-turn flow for /template: search_plan → LLM YAML generation."""
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

    # ── Turn 1: Ask LLM for predicate search keywords ──────────────────
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
            [{"role": "system", "content": SEMANTIKA_SYSTEM_PROMPT},
             {"role": "user", "content": turn1_prompt}],
        )
    except Exception as exc:
        logger.exception("/template turn 1 failed")
        return {"type": "status", "title": "/template", "data": {"message": f"LLM call failed: {exc}"}}

    # Parse search plan from LLM response
    keywords = parse_search_plan(turn1_result)
    if not keywords:
        # LLM didn't produce a search plan — try treating response as direct YAML
        yaml_content = extract_yaml(turn1_result)
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
            "data": {"html": render_markdown(turn1_result or "")},
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
                    "label": get_predicate_label(m),
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
            [{"role": "system", "content": SEMANTIKA_SYSTEM_PROMPT},
             {"role": "user", "content": turn2_prompt}],
        )
    except Exception as exc:
        logger.exception("/template turn 2 failed")
        return {"type": "status", "title": "/template", "data": {"message": f"LLM call failed: {exc}"}}

    yaml_content = extract_yaml(turn2_result) or turn2_result or ""
    return {
        "type": "template_yaml",
        "title": "/template",
        "data": {
            "yaml": yaml_content,
            "description": user_description,
        },
    }


# ── Tool-calling helpers ──────────────────────────────────────────────────


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


async def run_tool_loop(
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
            level = get_command_level(path) if is_registered(path) else None

            # Collect write+ tools for user review.  READ tools execute
            # immediately without confirmation.
            if level is not None and level >= PermissionLevel.WRITE:
                write_batch.append({
                    "index": idx,
                    "tokens": path.split("."),
                    "flags": flags,
                    "description": resolve_command_desc(path),
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
                "content": json.dumps(sanitize_tool_result(cmd_result)),
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
                "created_at": time.time(),
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


async def execute_with_tools(
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
        defs = [
            d for d in defs
            if d["path"][0] in allowed_domains
            and not (
                not d.get("params") and not d.get("flags")
                and not d.get("description", "").strip()
            )
        ]
    tools = defs_to_tools(defs) if defs else []
    messages = build_prompt_messages(expanded)

    return await run_tool_loop(messages, tools, name, max_rounds)


async def resume_execution(data: dict[str, Any]) -> dict[str, Any]:
    """Resume a paused prompt command execution after user confirmation.

    Called by the ``POST /execute/resume`` endpoint after the user reviews
    the pending tool batch in the confirmation modal.

    Args:
        data: Request body with ``session_id``, ``confirmed``, ``decisions``.

    Returns:
        Either a final ``{"type": "chat", ...}`` response, or another
        ``{"type": "confirm_tool", ...}`` if further tools need approval.
    """
    # Prune expired sessions before looking up
    _cleanup_expired_sessions()

    session_id = data.get("session_id", "")

    if session_id not in _pending_executions:
        from fastapi import HTTPException
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
            # READ tool already executed in run_tool_loop — skip
            continue

        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(sanitize_tool_result(cmd_result)),
        })

    # Continue the loop with the updated messages
    final = await run_tool_loop(messages, tools, name)

    if isinstance(final, dict) and final.get("type") == "confirm_tool":
        return final

    reply = final if isinstance(final, str) and final.strip() else None
    if reply:
        return {
            "type": "chat",
            "title": f"/{name}",
            "data": {"html": render_markdown(reply), "actions": []},
        }

    return {
        "type": "chat",
        "title": f"/{name}",
        "data": {"html": "<p><em>(command completed)</em></p>", "actions": []},
    }
