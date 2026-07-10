"""Shared helpers for file-based prompt command routes (/ prefix).

Extracted from prompt_commands.py to keep each file under 500 lines.
Provides the tool-calling loop, template flow, SSE streaming helpers,
and all internal utilities used by the route handlers.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from lightercore.llm.base import ToolCall, defs_to_tools
from lightercore.paths import config_dir
from lightercore.permissions import PermissionLevel

from semantika.server.command.errors import CommandError
from semantika.server.command.registry import (
    dispatch_path,
    get_command_definitions,
    get_command_level,
    get_handler_metadata,
)
from semantika.server.llm.provider import get_provider
from semantika.server.llm.system_prompt import load_system_prompt, system_prompt_path

logger = logging.getLogger(__name__)


def _commands_dir() -> str:
    """Return the commands directory path (config_dir / 'commands')."""
    return str(config_dir() / "commands")


# ── Helpers ───────────────────────────────────────────────────────────


def _extract_yaml(text: str | None) -> str | None:
    """Extract YAML content from a code-fenced block."""
    if not text:
        return None
    import re
    match = re.search(
        r"```(?:yaml|yml)?\s*\n(.*?)```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def _resolve_command_desc(path: str) -> str:
    """Return the description of the command at *path*, or empty string."""
    meta = get_handler_metadata(path)
    if meta is None:
        return ""
    return meta.get("description", "")


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

    def _walk(value):
        if isinstance(value, dict):
            return {k: _walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(v) for v in value]
        if isinstance(value, str) and len(value) > 1:
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    parsed = json.loads(stripped)
                    return _walk(parsed)
                except (json.JSONDecodeError, ValueError):
                    pass
        return value

    return _walk(result)


def _parse_tool_domains(
    template: str,
    frontmatter_tools: list[str] | None = None,
) -> set[str] | None:
    """Parse tool domain declaration from a prompt command template.

    Priority:
    1. ``frontmatter_tools`` (from YAML frontmatter, already parsed).
    2. ``# +tools: domain1, domain2`` comment in the template body.
    3. ``None`` — include all tools.

    Returns:
        A set of domain strings, or ``None`` to include all tools.
    """
    if frontmatter_tools:
        domains = {d.strip().lower() for d in frontmatter_tools if d.strip()}
        return domains if domains else None

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


def _load_user_prompt() -> str:
    """Load the user's ``~/.config/semantika/system_prompt.md`` file.

    This is the **full** system prompt (not an appendix) — the shipped
    default is auto-seeded on first run, and the user can edit the file
    freely.  The same file is used by the chat endpoint.

    .. deprecated::
        Kept for backward compat.  New code should call
        :func:`load_system_prompt` directly.
    """
    return load_system_prompt()


def _build_prompt_messages(expanded: str) -> list[dict]:
    """Build messages with Semantika system context for prompt commands.

    Uses the user-editable ``system_prompt.md`` (via :func:`load_system_prompt`)
    as the system message, then appends the expanded prompt command template
    as the user message.
    """
    return [
        {"role": "system", "content": load_system_prompt()},
        {"role": "user", "content": expanded},
    ]


# ── Tool loop ─────────────────────────────────────────────────────────


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


# In-memory store for paused executions awaiting user confirmation.
# Keys are session UUIDs, values are the state dicts.
_pending_executions: dict[str, dict] = {}


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

        # Append the assistant message with tool_calls
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

            # Collect write+ tools for user review
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

        # Gate write+ tools behind user review
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


async def _execute_with_tools(
    expanded: str,
    name: str,
    max_rounds: int = 20,
    allowed_domains: set[str] | None = None,
) -> str | dict | None:
    """Run the expanded prompt through a multi-round tool-calling loop.

    Args:
        expanded: The expanded prompt command template.
        name: The command name (for error messages).
        max_rounds: Maximum tool-calling iterations before giving up.
        allowed_domains: If set, only include tools whose first path
            segment is in this set. ``None`` means include all tools.

    Returns:
        - A ``str`` with the final answer on success.
        - A ``dict`` with ``{"type": "confirm_tool", ...}`` if a write or
          destructive tool needs human approval.
        - ``None`` if the LLM is unavailable or the loop exhausted.
    """
    provider = get_provider()
    if not provider.available:
        return None

    defs = get_command_definitions()
    if allowed_domains is not None:
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


def _format_command_str(tokens: list[str], flags: dict[str, str]) -> str:
    """Format a command with flags into a human-readable string.

    E.g. ``["node", "add"]`` + ``{"label": "Alice"}`` → ``!node add --label Alice``
    """
    cmd = "!" + " ".join(tokens)
    for k, v in flags.items():
        if v:
            cmd += f" --{k} {v}"
        else:
            cmd += f" --{k}"
    return cmd


def _resolve_feedback(
    idx: int,
    resolved: dict[int, bool],
    feedback: dict[int, str] | str | None,
) -> str | None:
    """Resolve user feedback for a specific tool index.

    Returns the feedback string if the tool was rejected and feedback
    was provided, otherwise ``None``.
    """
    if not feedback:
        return None
    if resolved.get(idx, False):
        return None  # approved — no feedback needed
    if isinstance(feedback, dict):
        return feedback.get(idx)
    return feedback  # global feedback string


def _inject_feedback_summary(
    messages: list[dict],
    tool_calls: list[ToolCall],
    resolved: dict[int, bool],
    feedback: dict[int, str] | str | None,
) -> None:
    """Inject a single summary user message for rejected tools.

    Creates one ``user`` message that summarises rejected tools
    + feedback, placed before the tool results so the LLM has context.
    """
    if not feedback:
        return

    parts: list[str] = []
    for idx, tc in enumerate(tool_calls):
        path, flags = _tc_path(tc)
        approved = resolved.get(idx, False)
        if approved:
            continue
        fb = _resolve_feedback(idx, resolved, feedback)
        if not fb:
            continue
        cmd_str = _format_command_str(path.split("."), flags)
        parts.append(f"- Rejected {cmd_str}: {fb}")

    if not parts:
        return

    summary = "The user reviewed the proposed operations and provided the following feedback:\n\n" + "\n".join(parts) + \
        "\n\nThe user is waiting for you to adjust your approach based on this feedback."
    messages.append({
        "role": "user",
        "content": summary,
    })


async def resume_execution(
    session_id: str,
    decisions: dict | None = None,
    confirmed: bool | None = None,
    feedback: dict | str | None = None,
) -> dict[str, Any]:
    """Resume a paused prompt command execution after user confirmation.

    Args:
        session_id: The session UUID from ``confirm_tool`` response.
        decisions: Per-tool-index approval dict (overrides confirmed).
        confirmed: Blanket approve/reject all tools.
        feedback: User feedback for rejected tools. A dict maps tool
            index to feedback string; a string is applied globally.

    Returns:
        Either a final ``{"type": "chat", ...}`` response, or another
        ``{"type": "confirm_tool", ...}`` if further tools need approval.
    """
    from fastapi import HTTPException

    if session_id not in _pending_executions:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    state = _pending_executions.pop(session_id)
    messages: list[dict] = state["messages"]
    tool_calls: list[ToolCall] = state["tool_calls"]
    tools: list[dict] = state["tools"]
    name: str = state["name"]
    write_indices: set[int] = state["write_indices"]

    # Resolve decisions: per-index map takes precedence, fall back to blanket
    raw_decisions: dict = decisions or {}
    if raw_decisions:
        resolved_decisions = {int(k): bool(v) for k, v in raw_decisions.items()}
    else:
        blanket = confirmed or False
        resolved_decisions = {idx: blanket for idx in write_indices}

    # Inject user feedback summary for rejected tools
    _inject_feedback_summary(messages, tool_calls, resolved_decisions, feedback)

    # Process ALL tools in the batch
    for idx, tc in enumerate(tool_calls):
        path, flags = _tc_path(tc)

        if idx in write_indices:
            approved = resolved_decisions.get(idx, False)
            if approved:
                try:
                    cmd_result = dispatch_path(path, flags)
                except CommandError as exc:
                    cmd_result = {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}
            else:
                fb = _resolve_feedback(idx, resolved_decisions, feedback)
                if fb:
                    cmd_str = _format_command_str(path.split("."), flags)
                    cmd_result = {"error": f"User rejected {cmd_str}, with the feedback: {fb}"}
                else:
                    cmd_result = {"error": f"User rejected !{' '.join(path.split('.'))}"}
        else:
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


# ── Turn prompts for /template two-turn flow ───────────────────────────────

_TEMPLATE_TURN_DIR = "commands/_template_turns"
"""Subdirectory within the config dir for template flow turn prompts."""


def _template_turns_dir() -> Path:
    """Return the template turns directory path."""
    return config_dir() / _TEMPLATE_TURN_DIR


def _load_turn_prompt(name: str) -> str | None:
    """Load a turn prompt file from the template turns directory.

    Reads ``~/.config/semantika/commands/_template_turns/{name}.md``
    and returns the full file content (including the ``# `` header line).
    Returns ``None`` if the file doesn't exist.
    """
    path = _template_turns_dir() / f"{name}.md"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("Failed to read turn prompt: %s", path)
        return None


def _expand_turn_prompt(template: str, args: list[str]) -> str:
    """Expand a turn prompt template with $1, $2, $ARGUMENTS substitution.

    Unlike prompt commands, turn prompts always use $1 for the first arg,
    $2 for the second, etc., and $ARGUMENTS for all remaining args joined.
    Fallback to ``expand_prompt_template`` for consistency.
    """
    from lightercore.prompt_commands import expand_prompt_template
    return expand_prompt_template(template, args)


def _load_and_expand_turn(name: str, expand_args: list[str]) -> str | None:
    """Load and expand a turn prompt, or return ``None`` if missing."""
    template = _load_turn_prompt(name)
    if template is None:
        return None
    return _expand_turn_prompt(template, expand_args)


# ── /template two-turn flow ────────────────────────────────────────────────


async def execute_template_flow(data: dict[str, Any]) -> dict[str, Any]:
    """Two-turn flow for /template: tool-based predicate discovery → YAML generation.

    Turn 1 uses the :func:`_run_tool_loop` with only the ``predicate.search``
    tool available, so the LLM can search for relevant predicates by calling
    the tool directly (no fragile JSON-in-text parsing).

    Turn 2 passes the discovered predicates to the LLM for YAML template
    generation.

    Both turn prompts are stored as user-editable files in
    ``~/.config/semantika/commands/_template_turns/``.
    """
    from pathlib import Path

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

    # ── Turn 1: Predicate discovery via tool calling ──────────────────────
    turn1_text = _load_and_expand_turn("turn1", args)
    if turn1_text is None:
        # Fallback hardcoded prompt if file is missing
        turn1_text = (
            "Your task is to find relevant predicates in the Semantika "
            "knowledge graph for creating a triple template.\n\n"
            "User description:\n" + user_description + "\n\n"
            "Use the **predicate.search** tool with different keywords "
            "to find predicates relevant to the user's description. "
            "Try multiple searches. Once you have a good set, summarise "
            "what predicates you found and what they are for."
        )

    turn1_messages = [
        {
            "role": "system",
            "content": (
                "You are a predicate discovery assistant for the Semantika "
                "knowledge graph. Your ONLY job is to find existing predicates "
                "relevant to the user's template description.\n\n"
                "Use the **predicate.search** tool to search for predicates. "
                "Each call returns matching predicate IDs and labels. "
                "Try different keyword variations to get broad coverage.\n\n"
                "Once you have a good set of predicates, provide a concise "
                "summary listing the predicate IDs you found."
            ),
        },
        {"role": "user", "content": turn1_text},
    ]

    # Build tool definitions — only predicate.search (READ-level, no confirm)
    all_defs = get_command_definitions()
    pred_search_defs = [d for d in all_defs if d["path"] == ["predicate", "search"]]
    turn1_tools = defs_to_tools(pred_search_defs) if pred_search_defs else []

    try:
        turn1_result = await _run_tool_loop(turn1_messages, turn1_tools, "template_turn1", max_rounds=10)
    except Exception as exc:
        logger.exception("/template turn 1 failed")
        return {"type": "status", "title": "/template", "data": {"message": f"Turn 1 failed: {exc}"}}

    # Extract predicates summary from LLM's final answer
    predicate_summary = turn1_result if isinstance(turn1_result, str) and turn1_result.strip() else ""
    if not predicate_summary:
        # If the tool loop returned no text, try to reconstruct from messages
        # Pick last assistant message content that has tool results context
        for msg in reversed(turn1_messages):
            if msg["role"] == "assistant" and msg.get("content", "").strip():
                predicate_summary = msg["content"]
                break

    # ── Turn 2: YAML template generation ─────────────────────────────────
    turn2_expand_args = [predicate_summary, user_description] if predicate_summary else [user_description]
    turn2_text = _load_and_expand_turn("turn2", turn2_expand_args)
    if turn2_text is None:
        # Fallback hardcoded prompt
        schema_block = (
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
            '  - "{var1} {predicate1} {var2}"           # URI (node ref)\n'
            '  - "{var1} {predicate2} {var3} --str"     # string literal\n'
            '  - "{var1} {predicate3} {var4} --int"     # number literal\n'
            "```"
        )
        turn2_text = (
            "You are a YAML template generator for the Semantika knowledge graph.\n\n"
            "Generate a triple template YAML from the user's description.\n\n"
            + schema_block +
            "\n\n## Rules\n"
            "- No flag = URI reference (object is another node)\n"
            "- `--str` = string literal, `--int` = number literal\n"
            "- Optional params: if not filled, the triple is auto-skipped\n"
            "- Use PREDICATE IDs that already exist in your graph\n\n"
            "## Predicates found\n"
            + (predicate_summary or "No predicates found.") + "\n\n"
            "## User description\n" + user_description + "\n\n"
            "Output ONLY the YAML code block — no explanation, no surrounding text."
        )

    turn2_prompt = (
        "You are a YAML template generator for the Semantika knowledge graph.\n\n"
        + turn2_text
    )

    try:
        turn2_result = await provider.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a YAML template generator. Generate a triple "
                        "template YAML from the user's description and the "
                        "predicates found. Output ONLY the YAML code block."
                    ),
                },
                {"role": "user", "content": turn2_prompt},
            ],
        )
    except Exception as exc:
        logger.exception("/template turn 2 failed")
        return {"type": "status", "title": "/template", "data": {"message": f"Turn 2 failed: {exc}"}}

    yaml_content = _extract_yaml(turn2_result) or turn2_result or ""
    return {
        "type": "template_yaml",
        "title": "/template",
        "data": {
            "yaml": yaml_content,
            "description": user_description,
        },
    }
