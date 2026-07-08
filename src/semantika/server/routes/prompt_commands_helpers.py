"""Shared helpers for prompt command routes and tool-calling flow.

Extracted from ``prompt_commands.py`` to keep each file under 500 lines
(per AGENTS.md convention).
"""

from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any

from lightercore.paths import config_dir

from semantika.server.command.registry import get_handler_metadata
from semantika.server.llm.system_prompt import SEMANTIKA_SYSTEM_PROMPT


def commands_dir() -> str:
    """Return the commands directory path (config_dir / 'commands')."""
    return str(config_dir() / "commands")


def load_user_prompt() -> str:
    """Load the user's ``~/.config/semantika/AGENTS.md`` file.

    This file provides additional context / instructions that the user
    wants injected into every prompt command.  It is **appended** to the
    base ``SEMANTIKA_SYSTEM_PROMPT``, so the user does not need to
    duplicate the base prompt.

    The file is auto-seeded on first run with a template explaining its
    purpose.  The user can edit it freely.
    """
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


def build_prompt_messages(expanded: str) -> list[dict]:
    """Build messages with Semantika system context for prompt commands.

    Combines the base system prompt with the user's ``AGENTS.md``
    (if present), then appends the expanded prompt command template
    as the user message.
    """
    user_prompt = load_user_prompt()
    if user_prompt:
        full_system = SEMANTIKA_SYSTEM_PROMPT + "\n\n" + user_prompt
    else:
        full_system = SEMANTIKA_SYSTEM_PROMPT

    return [
        {"role": "system", "content": full_system},
        {"role": "user", "content": expanded},
    ]


def is_registered(path: str) -> bool:
    """Check whether a dot-separated command path is registered."""
    return get_handler_metadata(path) is not None


def sanitize_tool_result(result: dict) -> dict:
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
                    parsed = _json.loads(stripped)
                    return _walk(parsed)
                except (_json.JSONDecodeError, ValueError):
                    pass
        return value

    return _walk(result)


def parse_tool_domains(
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

    for line in template.split("\n"):
        stripped = line.strip()
        match = re.match(r"^#\s*\+tools:\s*(.+)$", stripped, re.IGNORECASE)
        if match:
            domains = {d.strip().lower() for d in match.group(1).split(",") if d.strip()}
            return domains if domains else None
    return None


def render_markdown(text: str) -> str:
    """Render markdown text to HTML using mistune."""
    import mistune

    return mistune.html(text)


def parse_search_plan(text: str | None) -> list[str]:
    """Parse LLM response for a search_plan JSON object."""
    if not text:
        return []

    text = text.strip()
    json_match = re.search(r'\{[^{}]*"type"\s*:\s*"search_plan"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            obj = _json.loads(json_match.group())
            return obj.get("keywords", [])
        except (_json.JSONDecodeError, TypeError):
            pass
    return []


def extract_yaml(text: str | None) -> str | None:
    """Extract YAML content from a code-fenced block."""
    if not text:
        return None
    match = re.search(
        r"```(?:yaml|yml)?\s*\n(.*?)```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def get_predicate_label(pred: dict) -> str:
    """Get the best human-readable label for a predicate."""
    labels = pred.get("labels", {}) or {}
    return labels.get("en", labels.get("eo", pred.get("predicate_id", "")))


def resolve_command_desc(path: str) -> str:
    """Return the description of the command at *path*, or empty string."""
    meta = get_handler_metadata(path)
    if meta is None:
        return ""
    return meta.get("description", "")
