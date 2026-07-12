"""Shared helpers for file-based prompt command routes (/ prefix).

Extracted from prompt_commands.py to keep each file under 500 lines.
Provides the template flow, text-to-triples flow, context system,
resume wrapper, and internal utilities.

The core tool-calling loop lives in lightercore — this module only
contains semantika-specific logic and thin wrappers.
"""

from __future__ import annotations

import contextvars
import json
import logging
from pathlib import Path
from typing import Any

from lightercore.llm.base import defs_to_tools
from lightercore.paths import config_dir

from semantika.server.command.errors import CommandError
from semantika.server.command.handlers.context import (
    _current_context_session,
    clear_context,
    collect_into_context,
    get_filtered_context,
    init_context,
)
from semantika.server.command.registry import (
    dispatch_path as _raw_dispatch,
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


def _render_markdown(text: str) -> str:
    """Render markdown text to HTML using mistune."""
    import mistune
    return mistune.html(text)


def _load_user_prompt() -> str:
    """Load the user's ``~/.config/semantika/system_prompt.md`` file.

    .. deprecated::
        Kept for backward compat.  New code should call
        :func:`load_system_prompt` directly.
    """
    return load_system_prompt()


# ── Multi-turn flow session tracking ────────────────────────────────

# Kept outside lightercore's _pending_executions because the resume
# wrapper pops the HITL state first and needs flow-level annotations
# to decide what to do next (start turn 2, run validation, etc.).
_flow_sessions: dict[str, dict] = {}


def _annotate_template_flow(session_id: str, user_description: str) -> None:
    """Annotate a pending execution session with template flow context."""
    _flow_sessions[session_id] = {
        "flow_type": "template",
        "next_turn": "turn2",
        "user_description": user_description,
    }


def _annotate_ttt_flow(session_id: str, next_turn: str, user_text: str,
                       context_session_id: str) -> None:
    """Annotate a pending execution for the text-to-triples flow.

    Args:
        session_id: The HITL session UUID.
        next_turn: Which turn to start after resume (``"predicates"`` or ``"triples"``).
        user_text: The original user text for the command.
        context_session_id: The context store session ID.
    """
    _flow_sessions[session_id] = {
        "flow_type": "text_to_triple",
        "next_turn": next_turn,
        "user_text": user_text,
        "context_session_id": context_session_id,
    }


# ── Resume (wrapper around lightercore) ──────────────────────────────


async def resume_execution(
    session_id: str,
    decisions: dict | None = None,
    confirmed: bool | None = None,
    feedback: dict | str | None = None,
) -> dict[str, Any]:
    """Resume a paused prompt command execution after user confirmation.

    Thin wrapper around :func:`lightercore.llm.tool_loop.resume_execution`
    that adds semantika-specific features:
    - ``CommandError``/``suggestion`` in dispatch results
    - ``/template`` two-turn flow continuation
    - ``/text-to-triples`` three-turn flow continuation
    - Context store population after turn completion
    - T3 post-loop validation for text-to-triples

    Returns:
        Either a final ``{"type": "chat", ...}`` response, or another
        ``{"type": "confirm_tool", ...}`` if further tools need approval.
    """
    from fastapi import HTTPException

    from lightercore.llm.tool_loop import resume_execution as _lc_resume

    # Save flow context before _lc_resume consumes the session
    flow_data = _flow_sessions.pop(session_id, None)

    # Dispatch wrapper with context collection
    context_sid = (flow_data or {}).get("context_session_id", "")

    def _dispatch_wrapper(path: str, flags: dict) -> dict:
        try:
            result = _raw_dispatch(path, flags)
        except CommandError as exc:
            return {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}
        if context_sid:
            collect_into_context(context_sid, path, result)
        return result

    provider = get_provider()

    try:
        raw_result: str | dict | None = await _lc_resume(
            session_id=session_id,
            decisions=decisions,
            confirmed=confirmed,
            feedback=feedback,
            provider=provider,
            dispatch_fn=_dispatch_wrapper,
            get_handler_metadata_fn=get_handler_metadata,
            get_command_level_fn=get_command_level,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Post-processing: confirm_tool (nested) or flow continuation or chat
    if isinstance(raw_result, dict) and raw_result.get("type") == "confirm_tool":
        # Nested confirm_tool — preserve flow annotation for next resume
        if flow_data and "session_id" in raw_result:
            _flow_sessions[raw_result["session_id"]] = flow_data
        return raw_result

    flow_type = (flow_data or {}).get("flow_type", "")
    llm_answer = raw_result if isinstance(raw_result, str) and raw_result.strip() else ""

    # ── Template flow: turn 1 completed → proceed to turn 2 ──────────
    if flow_type == "template" and llm_answer:
        return await _run_template_turn2(
            predicate_summary=llm_answer,
            user_description=flow_data["user_description"],
        )

    # ── Text-to-triples flow continuation ────────────────────────────
    if flow_type == "text_to_triple" and llm_answer:
        ctx_sid = flow_data["context_session_id"]
        next_turn = flow_data["next_turn"]
        user_text = flow_data["user_text"]

        if next_turn == "predicates":
            return await _run_t2_templates_predicates(ctx_sid, user_text)
        elif next_turn == "triples":
            return await _run_t3_triples(ctx_sid, user_text)

    # ── Fallback: format as chat response ─────────────────────────────
    if llm_answer:
        return {
            "type": "chat",
            "title": "Prompt Command",
            "data": {"html": _render_markdown(llm_answer), "actions": []},
        }

    return {
        "type": "chat",
        "title": "Prompt Command",
        "data": {"html": "<p><em>(command completed)</em></p>", "actions": []},
    }


# ── Turn prompts for /template two-turn flow ─────────────────────────

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


def _expand_turn_prompt(template: str, vars: dict[str, str]) -> str:
    """Expand a turn prompt with named ``$VARIABLE`` placeholders.

    Unlike prompt commands, turn prompts use named variables only
    (e.g. ``$AVAILABLE_PREDICATES``, ``$TEMPLATE_DESCRIPTION``,
    ``$STYLE_EXAMPLE``, ``$ARGUMENTS``).  Unknown placeholders are left
    as-is so that old-style ``$1`` / ``$2`` files visibly fail rather
    than silently producing wrong output.
    """
    result = template
    for name, value in vars.items():
        result = result.replace(f"${name}", value)
    return result


def _load_and_expand_turn(name: str, vars: dict[str, str]) -> str | None:
    """Load and expand a turn prompt, or return ``None`` if missing."""
    template = _load_turn_prompt(name)
    if template is None:
        return None
    return _expand_turn_prompt(template, vars)


# ── Style example for template turn 2 ────────────────────────────────


def _get_style_example() -> str:
    """Return the most recently modified user-created template as a YAML example.

    Scans ``~/.config/semantika/templates/*.{yaml,yml}`` and picks the
    most recently modified file.  Returns ``""`` if no templates exist.
    """
    from semantika.server.templates.loader import list_templates

    templates = list_templates()
    if not templates:
        return ""

    # Pick the most recently modified
    best = max(templates, key=lambda t: t.path.stat().st_mtime)
    try:
        return best.path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ── /template two-turn flow ──────────────────────────────────────────


async def _run_template_turn2(
    predicate_summary: str,
    user_description: str,
) -> dict[str, Any]:
    """Run turn 2 of the template flow — YAML generation.

    The LLM can use **context.get** to retrieve predicate IDs discovered
    in turn 1, instead of relying on injected text variables.
    """
    from lightercore.llm.tool_loop import run_tool_loop as _lc_tool_loop

    # Build turn2 variables
    style_example = _get_style_example()
    turn2_vars: dict[str, str] = {
        "TEMPLATE_DESCRIPTION": user_description,
        "STYLE_EXAMPLE": style_example,
    }
    turn2_text = _load_and_expand_turn("turn2", turn2_vars)
    if turn2_text is None:
        from semantika.server.llm.prompt_defaults import DEFAULT_TURN2
        turn2_text = _expand_turn_prompt(DEFAULT_TURN2, turn2_vars)

    turn2_system = (
        "You are a YAML template generator for the Semantika knowledge graph. "
        "Your job is to generate valid YAML triple templates and save them "
        "using the available tools.\n\n"
        "## Get predicate IDs from context\n"
        "Call **context.get(type=predicates)** to see the exact predicate IDs "
        "that were discovered or created in the previous turn. Use ONLY "
        "those IDs — do NOT invent predicate IDs.\n\n"
        "## Triple format — STRINGS, not dicts\n"
        "Each triple must be a single string like "
        '"`{{subject}} rs:predicate {{object}}`". '
        "Do NOT use dict format (``subject: ...``, ``predicate: ...``).\n"
        "- No flag → URI reference (object is another node)\n"
        "- ``--str`` → string literal\n"
        "- ``--int`` → number literal\n\n"
        "Available tools:\n"
        "- **context.get** — Retrieve predicates from the previous turn.\n"
        "- **template.save** — Save a reusable triple pattern as a named template "
        "(WRITE-level, requires user confirmation).\n"
        "- **template.list** — Check existing template names (no confirmation).\n"
        "- **template.view** — Inspect a template's full structure (no confirmation).\n"
        "- **predicate.search** — Find predicate IDs by keyword (no confirmation).\n\n"
        "Important: Always generate the YAML content first, then call "
        "``template.save --yaml <content>`` to persist it. The user will "
        "be prompted to approve the save operation.\n\n"
        "After the template is saved, the ``template.save`` tool result "
        "includes a ``usage`` field showing the correct ``!triple add --template`` "
        "syntax. Include this usage example verbatim in your final summary "
        "so the user knows how to invoke the template."
    )
    turn2_messages = [
        {
            "role": "system",
            "content": load_system_prompt() + "\n\n" + turn2_system,
        },
        {"role": "user", "content": turn2_text},
    ]

    # Build tool definitions — include context.get
    all_defs = get_command_definitions()
    turn2_tool_paths = {
        ("context", "get"),
        ("template", "save"),
        ("template", "list"),
        ("template", "view"),
        ("predicate", "search"),
    }
    turn2_defs = [d for d in all_defs if tuple(d["path"]) in turn2_tool_paths]
    turn2_tools = defs_to_tools(turn2_defs) if turn2_defs else []

    if not turn2_tools:
        logger.warning("No turn 2 tools available — falling back to plain chat")
        provider = get_provider()
        try:
            turn2_result = await provider.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a YAML template generator. Generate a triple "
                            "template YAML from the user's description. "
                            "Output ONLY the YAML code block."
                        ),
                    },
                    {"role": "user", "content": turn2_text},
                ],
            )
        except Exception as exc:
            logger.exception("/template turn 2 plain-chat fallback failed")
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

    provider = get_provider()

    # Context-aware dispatch wrapper (reuses the context from turn 1)
    from semantika.server.command.handlers.context import _current_context_session
    # The context_session_id from turn 1 is already set in the contextvar
    # via execute_template_flow.  We don't need to set it again here —
    # the context.get handler reads it automatically.

    def _dispatch_wrapper(path: str, flags: dict) -> dict:
        try:
            result = _raw_dispatch(path, flags)
        except CommandError as exc:
            return {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}
        # Collect into context (context_session_id is set via the contextvar)
        sid = _current_context_session.get()
        if sid:
            collect_into_context(sid, path, result)
        return result

    try:
        turn2_result = await _lc_tool_loop(
            messages=turn2_messages,
            tools=turn2_tools,
            name="template_turn2",
            provider=provider,
            dispatch_fn=_dispatch_wrapper,
            get_handler_metadata_fn=get_handler_metadata,
            get_command_level_fn=get_command_level,
            max_rounds=15,
        )
    except Exception as exc:
        logger.exception("/template turn 2 failed")
        return {"type": "status", "title": "/template", "data": {"message": f"Turn 2 failed: {exc}"}}

    if isinstance(turn2_result, dict) and turn2_result.get("type") == "confirm_tool":
        return turn2_result

    if isinstance(turn2_result, str) and turn2_result.strip():
        html = _render_markdown(turn2_result)
        return {
            "type": "chat",
            "title": "/template",
            "data": {"html": html, "actions": []},
        }

    return {
        "type": "chat",
        "title": "/template",
        "data": {"html": "<p><em>Template generation produced no output.</em></p>", "actions": []},
    }


async def execute_template_flow(data: dict[str, Any]) -> dict[str, Any]:
    """Two-turn flow for /template: tool-based predicate discovery → YAML generation.

    Turn 1 uses lightercore's :func:`run_tool_loop` with ``predicate.search``
    and ``predicate.add`` tools.  Write-level operations (``predicate.add``)
    gate behind HITL confirmation.

    Turn 2 passes the discovered predicates to the LLM for YAML template
    generation (see :func:`_run_template_turn2`).

    Both turn prompts are stored as user-editable files in
    ``~/.config/semantika/commands/_template_turns/``.
    """
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

    # ── Turn 1: Predicate discovery (with optional creation) ─────────
    turn1_text = _load_and_expand_turn("turn1", {"ARGUMENTS": user_description})
    if turn1_text is None:
        from semantika.server.llm.prompt_defaults import DEFAULT_TURN1
        turn1_text = _expand_turn_prompt(DEFAULT_TURN1, {"ARGUMENTS": user_description})

    turn1_system = (
        "You are a predicate discovery assistant for the Semantika "
        "knowledge graph.\n\n"
        "Use the **predicate.search** tool to find existing predicates. "
        "Each call returns matching predicate IDs and labels. "
        "Try different keyword variations to get broad coverage.\n\n"
        "If a predicate you need does not exist, create it with "
        "**predicate.add**.\n\n"
        "Once you have a good set of predicates (both existing and "
        "newly created), provide a concise summary listing the "
        "predicate IDs you found or created."
    )
    turn1_messages = [
        {
            "role": "system",
            "content": load_system_prompt() + "\n\n" + turn1_system,
        },
        {"role": "user", "content": turn1_text},
    ]

    # Build tool definitions
    all_defs = get_command_definitions()
    turn1_tool_paths = {("predicate", "search"), ("predicate", "add")}
    turn1_defs = [d for d in all_defs if tuple(d["path"]) in turn1_tool_paths]
    turn1_tools = defs_to_tools(turn1_defs) if turn1_defs else []

    # Context store for predicates discovered/created
    import uuid
    context_session_id = str(uuid.uuid4())
    init_context(context_session_id)
    _current_context_session.set(context_session_id)
    ctx_dispatch = _make_context_dispatch_wrapper(context_session_id)

    from lightercore.llm.tool_loop import run_tool_loop as _lc_tool_loop

    try:
        turn1_result = await _lc_tool_loop(
            messages=turn1_messages,
            tools=turn1_tools,
            name="template_turn1",
            provider=provider,
            dispatch_fn=ctx_dispatch,
            get_handler_metadata_fn=get_handler_metadata,
            get_command_level_fn=get_command_level,
            max_rounds=10,
        )
    except Exception as exc:
        logger.exception("/template turn 1 failed")
        return {"type": "status", "title": "/template", "data": {"message": f"Turn 1 failed: {exc}"}}

    # Handle HITL from turn 1 (predicate.add gated behind confirmation)
    if isinstance(turn1_result, dict) and turn1_result.get("type") == "confirm_tool":
        _annotate_template_flow(turn1_result["session_id"], user_description)
        return turn1_result

    # Extract predicates summary from LLM's final answer
    predicate_summary = turn1_result if isinstance(turn1_result, str) and turn1_result.strip() else ""
    if not predicate_summary:
        for msg in reversed(turn1_messages):
            if msg["role"] == "assistant" and msg.get("content", "").strip():
                predicate_summary = msg["content"]
                break

    # ── Turn 2: YAML template generation ─────────────────────────────
    return await _run_template_turn2(predicate_summary, user_description)


# ── Context-aware dispatch wrapper ─────────────────────────────────────


def _make_context_dispatch_wrapper(context_session_id: str) -> Any:
    """Return a dispatch wrapper that automatically populates context.

    The returned wrapper:
    1. Dispatches the command (catching CommandError)
    2. Collects any created/found entities into the context store

    Use this instead of a raw ``_raw_dispatch`` wrapper in multi-turn flows.
    """
    def _wrapper(path: str, flags: dict) -> dict:
        try:
            result = _raw_dispatch(path, flags)
        except CommandError as exc:
            return {"error": str(exc), "suggestion": getattr(exc, "suggestion", "")}
        collect_into_context(context_session_id, path, result)
        return result
    return _wrapper


# ── Text-to-triples flow (extracted to separate file) ─────────────

# The 3-turn flow, T1/T2/T3 functions, and validation helpers live in
# ``prompt_commands_text_to_triple.py`` to keep this file under 500 lines.
# Import the main entry point for use in prompt_commands.py routing:
