"""Editable system prompt for the Semantika LLM agent.

Delegates to :class:`lightercore.system_prompt.SystemPromptManager` for
file-based prompt management with auto-seed on first run.

The shipped default is defined here (app-specific content).  The user
can customise the system prompt by editing the file at the path returned
by :func:`system_prompt_path` (typically
``~/.config/semantika/system_prompt.md``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from lightercore.system_prompt import SystemPromptManager

from semantika.core import config_dir

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_FILENAME = "system_prompt.md"
_LEGACY_FILENAME = "AGENTS.md"
"""Legacy filename from the earlier append-only customisation model.

On first access to the new system prompt, the loader attempts to migrate
content from the legacy AGENTS.md to the new system_prompt.md.  The legacy
file is **not** removed — the user may delete it manually after confirming
the migration.
"""

# ── Shipped default ─────────────────────────────────────────────────────────

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

# ── Backward-compat alias ───────────────────────────────────────────────────

#: The default system prompt text, kept for backward compatibility with code
#: that imports ``SEMANTIKA_SYSTEM_PROMPT`` directly.  New code should call
#: :func:`load_system_prompt` instead to respect user customisation.
SEMANTIKA_SYSTEM_PROMPT = DEFAULT_SEMANTIKA_PROMPT

# ── Default config files registry ─────────────────────────────────────────

_CONFIG_DEFAULTS: dict[str, str] = {
    _SYSTEM_PROMPT_FILENAME: DEFAULT_SEMANTIKA_PROMPT,
}
"""Registry of config filenames → default content.

Add new entries here when introducing a new user-editable config file
with a shipped default.  The :func:`seed_config_defaults` function
reads this dict on startup and creates any missing files.
"""


def seed_config_defaults() -> None:
    """Create default config files if they do not already exist.

    Called once on server startup (from ``lifespan``).  For each known
    config file, if the file is missing, it is created with its shipped
    default content so the user has a starting point for customisation.

    All write failures are logged as warnings and silently swallowed —
    a failure to seed a config file should never prevent the server from
    starting.  The corresponding ``load_*`` functions will fall back to
    lazy seeding when the file is first accessed.
    """
    for filename, default in _CONFIG_DEFAULTS.items():
        path = config_dir() / filename
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    continue  # file exists with content — respect user edits
            except OSError:
                pass  # unreadable file — try to reseed below

        # Handle legacy migration for system_prompt.md
        if filename == _SYSTEM_PROMPT_FILENAME:
            migrated = _migrate_from_legacy()
            if migrated is not None:
                continue  # migration created the file

        # Auto-seed with shipped default
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default, encoding="utf-8")
            logger.info("Seeded default config: %s", path)
        except OSError as exc:
            logger.warning("Failed to seed %s: %s", path, exc)


# ── Manager factory ─────────────────────────────────────────────────────────


def _get_manager() -> SystemPromptManager:
    """Return a fresh SystemPromptManager for the current config dir."""
    return SystemPromptManager(config_dir(), _SYSTEM_PROMPT_FILENAME)


def _get_legacy_path() -> Path:
    """Return the path to the legacy AGENTS.md file."""
    return config_dir() / _LEGACY_FILENAME


def _migrate_from_legacy() -> str | None:
    """Migrate content from legacy AGENTS.md to system_prompt.md.

    Called on startup (from :func:`seed_config_defaults`) or on first
    access (from :func:`load_system_prompt`) when ``system_prompt.md``
    does not exist yet but ``AGENTS.md`` does.  Creates ``system_prompt.md``
    with the shipped default prepended so the user sees the full base
    prompt plus their existing customisations in a single file.

    Returns the merged content, or ``None`` if there is nothing to migrate.
    """
    legacy = _get_legacy_path()
    if not legacy.is_file():
        return None

    try:
        legacy_content = legacy.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Failed to read legacy AGENTS.md at %s", legacy)
        return None

    if not legacy_content:
        return None

    # Prepend the shipped default so the user gets the full base prompt
    # in a single file.  The separator header helps users understand what
    # was part of the app default vs their custom additions.
    merged = (
        DEFAULT_SEMANTIKA_PROMPT
        + "\n\n"
        + "---\n"
        + "*The content below was migrated from AGENTS.md.*  "
        "You may edit or remove it freely.\n"
        + "---\n\n"
        + legacy_content
    )

    prompt_path = _get_manager().path()
    try:
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(merged, encoding="utf-8")
        logger.info(
            "Migrated system prompt from legacy AGENTS.md to %s",
            prompt_path,
        )
        return merged
    except OSError as exc:
        logger.warning("Failed to write migrated system prompt: %s", exc)
        return None


def system_prompt_path() -> Path:
    """Return the path to the user-modifiable system prompt file.

    Returns:
        ``~/.config/semantika/system_prompt.md``.
    """
    return _get_manager().path()


def load_system_prompt() -> str:
    """Load the system prompt, auto-seeding on first run.

    Under normal operation :func:`seed_config_defaults` already creates
    the file on startup, so this function reads an existing file.  The
    fallback paths handle edge cases (e.g. the user deleted the file
    while the server is running).

    Resolution order:
    1. If ``system_prompt.md`` already exists → return its content.
    2. If ``AGENTS.md`` (legacy) exists → migrate it into ``system_prompt.md``
       with the shipped default prepended, then return the merged content.
    3. Otherwise → auto-seed ``system_prompt.md`` with the shipped default.

    Returns:
        The system prompt string.
    """
    prompt_path = _get_manager().path()

    # Fast path: file already exists
    if prompt_path.is_file():
        try:
            content = prompt_path.read_text(encoding="utf-8").strip()
            if content:
                return content
        except OSError:
            pass

    # Attempt legacy migration
    migrated = _migrate_from_legacy()
    if migrated is not None:
        return migrated

    # Auto-seed with the shipped default (fallback)
    return _get_manager().load(DEFAULT_SEMANTIKA_PROMPT)


def reload_system_prompt() -> str:
    """Force-reload the system prompt, ignoring any cached version.

    Useful when the user edits the prompt file while the server is running.
    """
    return _get_manager().reload(DEFAULT_SEMANTIKA_PROMPT)


__all__ = [
    "DEFAULT_SEMANTIKA_PROMPT",
    "SEMANTIKA_SYSTEM_PROMPT",
    "load_system_prompt",
    "reload_system_prompt",
    "seed_config_defaults",
    "system_prompt_path",
]
