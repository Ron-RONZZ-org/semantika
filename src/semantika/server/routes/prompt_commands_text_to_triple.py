"""Text-to-triples three-turn flow logic.

Extracted from prompt_commands_helpers.py to keep each file under 500 lines.
Provides the three-turn LLM flow for /text-to-triples (and /ttt):

- Turn 1: Node discovery (search + create)
- Turn 2: Template + predicate discovery
- Turn 3: Triple creation with post-loop validation
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lightercore.llm.base import defs_to_tools
from lightercore.paths import config_dir

from semantika.server.command.handlers.context import (
    _current_context_session,
    clear_context,
    get_filtered_context,
    init_context,
)
from semantika.server.command.registry import (
    get_command_definitions,
    get_command_level,
    get_handler_metadata,
)
from semantika.server.llm.provider import get_provider
from semantika.server.llm.system_prompt import load_system_prompt
from semantika.server.routes.prompt_commands_helpers import (
    _make_context_dispatch_wrapper,
)

logger = logging.getLogger(__name__)

_TTT_TURN_DIR = "commands/_text_to_triple_turns"


def _ttt_turns_dir() -> Path:
    """Return the text-to-triples turns directory path."""
    return config_dir() / _TTT_TURN_DIR


def _load_ttt_turn(name: str) -> str | None:
    """Load a text-to-triples turn prompt file.

    Reads ``~/.config/semantika/commands/_text_to_triple_turns/{name}.md``.
    Returns ``None`` if the file doesn't exist.
    """
    path = _ttt_turns_dir() / f"{name}.md"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("Failed to read text-to-triples turn prompt: %s", path)
        return None


def _expand_turn_prompt(template: str, vars: dict[str, str]) -> str:
    """Expand a turn prompt with named ``$VARIABLE`` placeholders."""
    result = template
    for name, value in vars.items():
        result = result.replace(f"${name}", value)
    return result


def _render_markdown(text: str) -> str:
    """Render markdown text to HTML using mistune."""
    import mistune
    return mistune.html(text)


async def execute_text_to_triple_flow(data: dict[str, Any]) -> dict[str, Any]:
    """Three-turn flow for /text-to-triples: Nodes → Templates+Predicates → Triples.

    Args:
        data: Request body with ``{"args": [user_text]}``.

    Returns:
        Either a ``confirm_tool`` (HITL), ``chat`` (final), or ``status`` response.
    """
    args = data.get("args", [])
    user_text = " ".join(args) if args else ""

    if not user_text:
        return {
            "type": "status",
            "title": "/text-to-triples",
            "data": {"message": "Provide the text you want to translate into triples."},
        }

    provider = get_provider()
    if not provider.available:
        return {
            "type": "status",
            "title": "/text-to-triples",
            "data": {
                "message": (
                    "LLM not configured. "
                    "Use !llm configure or set up a provider in Settings."
                ),
            },
        }

    # Initialise context store
    import uuid
    context_session_id = str(uuid.uuid4())
    init_context(context_session_id)

    # ── Turn 1: Nodes ──────────────────────────────────────────────
    result = await _run_t1_nodes(context_session_id, user_text)
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        from semantika.server.routes.prompt_commands_helpers import _annotate_ttt_flow
        _annotate_ttt_flow(
            result["session_id"], "predicates", user_text, context_session_id,
        )
        return result

    # ── Turn 2: Templates + Predicates ─────────────────────────────
    result = await _run_t2_templates_predicates(context_session_id, user_text)
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        from semantika.server.routes.prompt_commands_helpers import _annotate_ttt_flow
        _annotate_ttt_flow(
            result["session_id"], "triples", user_text, context_session_id,
        )
        return result

    # ── Turn 3: Triples (with validation) ──────────────────────────
    return await _run_t3_triples(context_session_id, user_text)


async def _run_t1_nodes(context_session_id: str, user_text: str) -> dict[str, Any]:
    """Turn 1: Identify entities, search/create nodes."""
    _current_context_session.set(context_session_id)

    turn1_text = _load_ttt_turn("turn1")
    if turn1_text is None:
        from semantika.server.llm.prompt_defaults import DEFAULT_TTT_TURN1
        turn1_text = _expand_turn_prompt(DEFAULT_TTT_TURN1, {"ARGUMENTS": user_text})

    turn1_system = (
        "You are a node discovery assistant for the Semantika "
        "knowledge graph.\n\n"
        "Your task is to identify all entities mentioned in the user's text, "
        "search for existing nodes, and create any that are missing.\n\n"
        "Use **node.search** to find existing nodes by their labels. "
        "Try different keyword variations and languages.\n"
        "Use **node.add** to create missing nodes with appropriate labels. "
        "If no label language is specified, use English.\n\n"
        "Once you have created all missing nodes, provide a summary "
        "listing all node IDs (both existing and newly created)."
    )
    turn1_messages = [
        {
            "role": "system",
            "content": load_system_prompt() + "\n\n" + turn1_system,
        },
        {"role": "user", "content": turn1_text},
    ]

    all_defs = get_command_definitions()
    turn1_tool_paths = {("node", "search"), ("node", "add")}
    turn1_defs = [d for d in all_defs if tuple(d["path"]) in turn1_tool_paths]
    turn1_tools = defs_to_tools(turn1_defs) if turn1_defs else []

    from lightercore.llm.tool_loop import run_tool_loop as _lc_tool_loop

    provider = get_provider()
    ctx_dispatch = _make_context_dispatch_wrapper(context_session_id)

    try:
        result = await _lc_tool_loop(
            messages=turn1_messages,
            tools=turn1_tools,
            name="text_to_triple_t1",
            provider=provider,
            dispatch_fn=ctx_dispatch,
            get_handler_metadata_fn=get_handler_metadata,
            get_command_level_fn=get_command_level,
            max_rounds=10,
        )
    except Exception as exc:
        logger.exception("/text-to-triples turn 1 failed")
        clear_context(context_session_id)
        return {
            "type": "status",
            "title": "/text-to-triples",
            "data": {"message": f"Node discovery failed: {exc}"},
        }

    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    return result  # Text summary


async def _run_t2_templates_predicates(context_session_id: str,
                                       user_text: str) -> dict[str, Any]:
    """Turn 2: Discover matching templates, search/create predicates."""
    _current_context_session.set(context_session_id)

    turn2_text = _load_ttt_turn("turn2")
    if turn2_text is None:
        from semantika.server.llm.prompt_defaults import DEFAULT_TTT_TURN2
        turn2_text = _expand_turn_prompt(DEFAULT_TTT_TURN2, {"ARGUMENTS": user_text})

    turn2_system = (
        "You are a predicate and template discovery assistant for the "
        "Semantika knowledge graph.\n\n"
        "Your task is to:\n"
        "1. Check if any existing triple templates match the text pattern "
        "using **template.list** and **template.view**.\n"
        "2. Search for existing predicates using **predicate.search**, "
        "and create missing ones using **predicate.add**.\n\n"
        "Templates define reusable triple patterns. If one matches, note "
        "which template it is and what parameters it needs.\n\n"
        "Predicates are relationship types (e.g. hasAuthor, hasTitle). "
        "Create only those that genuinely appear in the text.\n\n"
        "Once done, provide a summary of the templates found and "
        "predicates created or discovered."
    )
    turn2_messages = [
        {
            "role": "system",
            "content": load_system_prompt() + "\n\n" + turn2_system,
        },
        {"role": "user", "content": turn2_text},
    ]

    all_defs = get_command_definitions()
    turn2_tool_paths = {
        ("template", "list"), ("template", "view"),
        ("predicate", "search"), ("predicate", "add"),
    }
    turn2_defs = [d for d in all_defs if tuple(d["path"]) in turn2_tool_paths]
    turn2_tools = defs_to_tools(turn2_defs) if turn2_defs else []

    from lightercore.llm.tool_loop import run_tool_loop as _lc_tool_loop

    provider = get_provider()
    ctx_dispatch = _make_context_dispatch_wrapper(context_session_id)

    try:
        result = await _lc_tool_loop(
            messages=turn2_messages,
            tools=turn2_tools,
            name="text_to_triple_t2",
            provider=provider,
            dispatch_fn=ctx_dispatch,
            get_handler_metadata_fn=get_handler_metadata,
            get_command_level_fn=get_command_level,
            max_rounds=15,
        )
    except Exception as exc:
        logger.exception("/text-to-triples turn 2 failed")
        return {
            "type": "status",
            "title": "/text-to-triples",
            "data": {"message": f"Template/predicate discovery failed: {exc}"},
        }

    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    return result


async def _run_t3_triples(context_session_id: str, user_text: str) -> dict[str, Any]:
    """Turn 3: Create triples with post-loop validation and auto-correction.

    After the tool loop, a validation pass checks that all referenced
    entities exist in the context store.  Invalid references trigger an
    automatic corrective prompt and a re-entry into the loop (max 3 rounds).
    """
    _current_context_session.set(context_session_id)

    turn3_text = _load_ttt_turn("turn3")
    if turn3_text is None:
        from semantika.server.llm.prompt_defaults import DEFAULT_TTT_TURN3
        turn3_text = _expand_turn_prompt(DEFAULT_TTT_TURN3, {"ARGUMENTS": user_text})

    turn3_system = (
        "You are a triple creation assistant for the Semantika "
        "knowledge graph.\n\n"
        "CRITICAL: Before creating any triples, call **context.get(type=all)** "
        "to retrieve the exact node and predicate IDs from previous turns. "
        "Use ONLY those IDs — do NOT invent or guess IDs.\n\n"
        "To create triples, you can either:\n"
        "- Use **!template use <name> --param1 <label> --param2 <label>** "
        "if a matching template was found. This creates nodes from labels "
        "automatically.\n"
        "  For node params, labels can be JSON for multiple languages:\n"
        "  ``--param '{\"en\":\"Title\",\"fr\":\"Titre\"}'``\n"
        "- Use **!triple add --subject_id <id> --predicate_id <id> --object_value <value>** "
        "for direct triple creation.\n\n"
        "For literal values, use the appropriate flag:\n"
        "- ``--str`` for string literals\n"
        "- ``--int`` for numbers\n"
        "- ``--lang <code>`` for language-tagged strings\n\n"
        "Always batch multiple triples in a single response. "
        "After creating all triples, summarise what was created.\n"
        "If the text contains patterns that repeat across different entities, "
        "suggest creating a reusable template via **/template**."
    )
    turn3_messages = [
        {
            "role": "system",
            "content": load_system_prompt() + "\n\n" + turn3_system,
        },
        {"role": "user", "content": turn3_text},
    ]

    all_defs = get_command_definitions()
    turn3_tool_paths = {
        ("context", "get"),
        ("triple", "add"),
        ("template", "use"),
        ("template", "list"), ("template", "view"),
        ("node", "search"),
    }
    turn3_defs = [d for d in all_defs if tuple(d["path"]) in turn3_tool_paths]
    turn3_tools = defs_to_tools(turn3_defs) if turn3_defs else []

    from lightercore.llm.tool_loop import run_tool_loop as _lc_tool_loop

    provider = get_provider()
    ctx_dispatch = _make_context_dispatch_wrapper(context_session_id)

    # ── Post-loop validation rounds ─────────────────────────────────
    for vround in range(3):
        try:
            result = await _lc_tool_loop(
                messages=turn3_messages,
                tools=turn3_tools,
                name="text_to_triple_t3",
                provider=provider,
                dispatch_fn=ctx_dispatch,
                get_handler_metadata_fn=get_handler_metadata,
                get_command_level_fn=get_command_level,
                max_rounds=15,
            )
        except Exception as exc:
            logger.exception("/text-to-triples turn 3 failed")
            clear_context(context_session_id)
            return {
                "type": "status",
                "title": "/text-to-triples",
                "data": {"message": f"Triple creation failed: {exc}"},
            }

        # HITL gate — pause and let user confirm
        if isinstance(result, dict) and result.get("type") == "confirm_tool":
            return result

        # Post-loop validation
        errors = _validate_triple_refs(turn3_messages, context_session_id)
        if not errors:
            # All clean — return result
            clear_context(context_session_id)
            if isinstance(result, str) and result.strip():
                html = _render_markdown(result)
                return {
                    "type": "chat",
                    "title": "/text-to-triples",
                    "data": {"html": html, "actions": []},
                }
            return {
                "type": "chat",
                "title": "/text-to-triples",
                "data": {
                    "html": "<p><em>Triple creation completed.</em></p>",
                    "actions": [],
                },
            }

        # Validation failed — inject corrective prompt
        corrective = _build_corrective_prompt(errors, context_session_id)
        turn3_messages.append({"role": "user", "content": corrective})

        if vround >= 2:
            logger.warning(
                "T3 validation failed after 3 rounds: %s", errors
            )

    # Exhausted validation rounds — return the last result anyway
    clear_context(context_session_id)
    final = result if isinstance(result, str) and result.strip() else ""
    if final:
        return {
            "type": "chat",
            "title": "/text-to-triples",
            "data": {"html": _render_markdown(final), "actions": []},
        }
    return {
        "type": "chat",
        "title": "/text-to-triples",
        "data": {
            "html": "<p><em>Triple creation completed (with validation warnings).</em></p>",
            "actions": [],
        },
    }


# ── T3 validation helpers ────────────────────────────────────────────


def _validate_triple_refs(messages: list[dict],
                          context_session_id: str) -> list[str]:
    """Check all triple.add tool calls in *messages* against the context store.

    Returns a list of error strings (empty = all valid).
    Checks subject_id, predicate_id, and URI-type object_value.
    """
    ctx = get_filtered_context(context_session_id, "all")
    all_node_ids = set()
    for n in ctx.get("nodes", []):
        all_node_ids.add(n.get("id", ""))
    all_pred_ids = set()
    for p in ctx.get("predicates", []):
        all_pred_ids.add(p.get("id", ""))

    errors: list[str] = []

    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            if fn.get("name") != "triple_add":
                continue
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue

            subj = args.get("subject_id", "")
            pred = args.get("predicate_id", "")
            obj = args.get("object_value", "")
            obj_type = args.get("object_type", "uri")

            if subj and subj not in all_node_ids:
                errors.append(
                    f"!triple.add: subject node '{subj}' not found"
                )
            if pred and pred not in all_pred_ids:
                errors.append(
                    f"!triple.add: predicate '{pred}' not found"
                )
            if obj_type == "uri" and obj and obj not in all_node_ids:
                errors.append(
                    f"!triple.add: object node '{obj}' not found"
                )

    # Deduplicate
    seen = set()
    unique: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique


def _build_corrective_prompt(errors: list[str],
                             context_session_id: str) -> str:
    """Build a corrective user message for invalid triple references."""
    ctx = get_filtered_context(context_session_id, "all")
    lines: list[str] = [
        "The following triples reference nodes or predicates that do not exist:",
        "",
    ]
    for e in errors:
        lines.append(f"- {e}")

    lines += [
        "",
        "Available nodes:",
    ]
    for n in ctx.get("nodes", []):
        lines.append(f"  - {n.get('id', '')}  ({n.get('labels', {}).get('en', '')})")
    lines += [
        "",
        "Available predicates:",
    ]
    for p in ctx.get("predicates", []):
        lines.append(f"  - {p.get('id', '')}")
    lines += [
        "",
        "Use **context.get(type=all)** to retrieve the exact IDs, "
        "then correct the triples and retry.",
        "Do NOT invent node or predicate IDs.",
    ]

    return "\n".join(lines)
