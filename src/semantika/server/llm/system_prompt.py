"""Editable system prompt for the Semantika LLM agent.

Two files work together:

1. **``system_prompt.md``** — the base prompt (the app's operational
   instructions: tool usage, batch operations, error recovery, etc.).
   Shipped default is :data:`DEFAULT_SEMANTIKA_PROMPT`.  Edited by
   power users who want deep customisation of the LLM's behaviour.

2. **``AGENTS.md``** — the user's custom style instructions (naming
   conventions, language preferences, workflow rules, domain conventions,
   writing style, etc.).  Always *appended* after the base prompt.
   This is the primary customisation point for regular users.
   :func:`load_user_style` makes this content available to **both** the
   main LLM agent and the cowrite (co-writing) endpoint, ensuring
   consistent style across all LLM interactions.

The old per-domain ``cowrite_style*.md`` files have been removed in
favour of a single ``AGENTS.md`` file.  All writing style rules (tone,
conventions, domain guidance) should go into ``AGENTS.md``.

Both files are auto-seeded on first access (lazy seeding).  The combined
result is returned by :func:`load_system_prompt`.

Backward-compat note: users who previously ran a version that merged
AGENTS.md into system_prompt.md will see their existing system_prompt.md
returned as-is (no double-append of AGENTS.md).
"""

from __future__ import annotations

import logging
from pathlib import Path

from lightercore.system_prompt import SystemPromptManager

from semantika.core import config_dir

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_FILENAME = "system_prompt.md"
_AGENTS_FILENAME = "AGENTS.md"
_MIGRATION_MARKER = "migrated from AGENTS.md"
"""String embedded in system_prompt.md by the previous single-file migration.

If present, the file already contains the user's AGENTS.md content merged
in, so we must NOT append AGENTS.md again on top.
"""

# ── Shipped defaults ─────────────────────────────────────────────────────────

DEFAULT_SEMANTIKA_PROMPT = (
    "You are Semantika AI, the built-in assistant of the **Semantika "
    "knowledge graph** application. You run INSIDE the app and can "
    "call tools to create, read, and update graph data.\n\n"
    "## What Semantika Is\n"
    "Semantika stores structured knowledge as:\n"
    "- **Nodes** — entities or concepts (e.g. a book, a person, an idea)\n"
    "- **Predicates** — relationship types between nodes (e.g. author, theme)\n"
    "- **Triples** — subject-predicate-object statements\n\n"
    "## How to Use Tools\n"
    "- **Batch operations**: You can return MULTIPLE tool calls in a "
    "single response. If you need to create 3 nodes, call the add tool "
    "three times in one response — do NOT create them one at a time.\n"
    "- **Plan first**: Decide everything you need before calling tools, "
    "then batch all independent calls in a single round.\n"
    "- **Search before creating**: Always check if data already exists "
    "before creating duplicates (nodes, predicates).\n"
    "- **Prefer update over delete+recreate**: If something just needs "
    "changes, use the update tool instead of deleting and re-creating.\n"
    "- **Stop when done**: Once you have fetched or modified all the "
    "data the user asked for, produce a final text answer summarising "
    "what you did. Do NOT keep calling tools after the task is complete.\n\n"
    "## Write Operations\n"
    "Tools that modify data (add, update, delete, merge) will prompt "
    "the user for confirmation before executing. This is normal — "
    "explain what the tool will do when the confirmation dialog appears.\n\n"
    "## How to Respond\n"
    "- Keep responses concise and helpful. Use Markdown formatting.\n"
    "- Never invent data. If you truly have no data, say so clearly.\n"
    "- When you have completed the user's request, output a plain text "
    "answer summarising what you did. That signals the task is done."
)

DEFAULT_AGENTS_STYLE = (
    "# AGENTS.md — Additional context for Semantika AI\n\n"
    "This file is loaded automatically and appended to the system prompt "
    "for ALL interactions (chat, cowrite, prompt commands).  Use it to add "
    "your personal naming conventions, style preferences, or workflow rules.\n\n"
    "## General Style\n"
    "- Clear, factual, and neutral tone\n"
    "- Use precise terminology\n"
    "- Be concise \u2014 entries should be easy to scan\n"
    "- Use English for labels and definitions\n"
    "- Avoid promotional language, subjective opinions, or fluff\n\n"
    "## Node Conventions\n"
    "- Use singular form for concept nodes\n"
    "- Capitalize proper nouns only\n"
    "- One or two sentences capturing the essential meaning\n"
    "- Include a brief etymology or source if relevant\n\n"
    "## Predicate Conventions\n"
    "- Use camelCase for multi-word IDs (hasAuthor, isPartOf, depicts)\n"
    "- Keep IDs short but descriptive\n"
    "- Follow existing predicate naming conventions in the graph\n\n"
    "## Triple Conventions\n"
    "- Subject-Predicate-Object: clear and unambiguous\n"
    "- Use existing predicates from the built-in catalog when possible\n"
    "- Briefly explain the relationship if it's non-obvious\n\n"
    "## Review and Proof\n"
    "- Evaluate accuracy, consistency, and completeness of triples\n"
    "- Cite specific sources or reasoning steps\n"
    "- Distinguish between direct evidence and inference\n"
    "- Note confidence level when appropriate\n"
)

# ── Backward-compat alias ───────────────────────────────────────────────────

#: The default system prompt text, kept for backward compatibility with code
#: that imports ``SEMANTIKA_SYSTEM_PROMPT`` directly.
SEMANTIKA_SYSTEM_PROMPT = DEFAULT_SEMANTIKA_PROMPT

# ── Manager factory ─────────────────────────────────────────────────────────


def _get_manager(filename: str) -> SystemPromptManager:
    """Return a fresh SystemPromptManager for *filename* in the config dir."""
    return SystemPromptManager(config_dir(), filename)


# ── Path access ─────────────────────────────────────────────────────────────


def system_prompt_path() -> Path:
    """Return the path to the base system prompt file.

    Returns:
        ``~/.config/semantika/system_prompt.md``.
    """
    return config_dir() / _SYSTEM_PROMPT_FILENAME


def agents_path() -> Path:
    """Return the path to the user's AGENTS.md style file.

    Returns:
        ``~/.config/semantika/AGENTS.md``.
    """
    return config_dir() / _AGENTS_FILENAME


# ── Lazy loading helpers ────────────────────────────────────────────────────


def _has_migration_marker(content: str) -> bool:
    """Check if *content* contains the legacy migration marker string."""
    return _MIGRATION_MARKER in content


def _lazy_seed(filepath: Path, default: str) -> str | None:
    """Auto-seed *filepath* with *default* if it doesn't exist.

    Returns the file content if successfully seeded, ``None`` if the
    file exists with content already or if writing fails.
    """
    if filepath.is_file():
        try:
            content = filepath.read_text(encoding="utf-8").strip()
            if content:
                return None  # already exists with content
        except OSError:
            pass

    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(default, encoding="utf-8")
        logger.info("Auto-seeded: %s", filepath)
        return default
    except OSError as exc:
        logger.warning("Failed to seed %s: %s", filepath, exc)
        return None


def load_user_style() -> str | None:
    """Load the user's AGENTS.md style guide, auto-seeding on first access.

    Called by both the main LLM system prompt loader and the cowrite
    endpoint to ensure consistent style across all LLM interactions.

    Returns the content of AGENTS.md, or ``None`` if the file is missing
    or empty (no style guidance to append).
    """
    path = agents_path()
    if path.is_file():
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return content
        except OSError:
            pass

    # Auto-seed on first access
    _lazy_seed(path, DEFAULT_AGENTS_STYLE)
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content if content else None
    except OSError:
        return None


# ── Public API ──────────────────────────────────────────────────────────────


def load_system_prompt() -> str:
    """Load the full system prompt = base prompt + user's AGENTS.md.

    Resolution order:
    1. If ``system_prompt.md`` exists and *does not* contain the legacy
       migration marker → return its content with AGENTS.md appended
       (if present).  This is the normal two-file mode.
    2. If ``system_prompt.md`` exists and *does* contain the migration
       marker → return its content as-is (backward compat — the file
       already includes the user's AGENTS.md content merged in).
    3. Otherwise → auto-seed ``system_prompt.md`` with the shipped
       default, load AGENTS.md, combine, and return.

    Returns:
        The combined system prompt string.
    """
    base_path = system_prompt_path()

    # Fast path: existing system_prompt.md
    if base_path.is_file():
        try:
            content = base_path.read_text(encoding="utf-8").strip()
            if content:
                # Backward compat: if the file was migrated from AGENTS.md
                # in a previous single-file version, return as-is.
                if _has_migration_marker(content):
                    return content
                # Normal two-file mode: base exists, append AGENTS.md
                style = load_user_style()
                if style:
                    return content + "\n\n" + style
                return content
        except OSError:
            pass

    # First run (no system_prompt.md yet): auto-seed base + load style
    base = DEFAULT_SEMANTIKA_PROMPT
    _lazy_seed(base_path, base)

    style = load_user_style()
    if style:
        return base + "\n\n" + style
    return base


def reload_system_prompt() -> str:
    """Force-reload the system prompt, re-reading both files from disk.

    Useful when the user edits the prompt file(s) while the server is
    running.  Re-reads both ``system_prompt.md`` and ``AGENTS.md`` and
    returns the combined result.
    """
    base_path = system_prompt_path()

    if base_path.is_file():
        try:
            content = base_path.read_text(encoding="utf-8").strip()
            if content:
                # Backward compat: migrated file → return as-is
                if _has_migration_marker(content):
                    return content
                # Normal two-file mode: re-read AGENTS.md and combine
                style = load_user_style()
                if style:
                    return content + "\n\n" + style
                return content
        except OSError:
            pass

    # Fall back to fresh combine
    return load_system_prompt()


__all__ = [
    "DEFAULT_AGENTS_STYLE",
    "DEFAULT_SEMANTIKA_PROMPT",
    "SEMANTIKA_SYSTEM_PROMPT",
    "agents_path",
    "load_system_prompt",
    "load_user_style",
    "reload_system_prompt",
    "system_prompt_path",
]
