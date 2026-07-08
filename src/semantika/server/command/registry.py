"""Command registry — decorator-based handler registration with auto-generated tree.

Usage:
    @command("node.list", description="List all nodes")
    def cmd_node_list(remaining: list[str], flags: dict[str, str]) -> dict:
        ...

Then dispatch(["node", "list"], {}) calls cmd_node_list([], {}).
The command tree for frontend autocomplete is auto-generated from registrations.
"""

from __future__ import annotations

from typing import Any, Callable

from lightercore.permissions import PermissionLevel

from semantika.server.command.errors import CommandNotFound

# ── Registry ──────────────────────────────────────────────────────────────

_commands: dict[str, tuple[Callable, dict[str, Any]]] = {}
"""Maps dot-separated path -> (handler_fn, metadata_dict)."""

_group_descriptions: dict[str, str] = {}
"""Optional descriptions for non-leaf group nodes."""

_interactive_forms: dict[str, str] = {}
"""Maps dot-separated path -> frontend form type string."""


def command(path: str, **metadata: Any) -> Callable:
    """Decorator: register a function as a command handler.

    Args:
        path: Dot-separated command path, e.g. ``"node.list"``.
        **metadata: Arbitrary metadata. Recognized keys:
            description: Human-readable help text.
            params: List of {"name", "type", "required", "default"} dicts.
            flags: List of {"name", "type", "help"} dicts.
            interactive: bool — whether this command has a form fallback.
            form_type: str — frontend form type (defaults to path with ``-``).
    """
    def wrapper(fn: Callable) -> Callable:
        _commands[path] = (fn, metadata)
        if metadata.get("interactive"):
            form_type = metadata.get("form_type", path.replace(".", "-"))
            _interactive_forms[path] = form_type
        _invalidate_cache()
        return fn
    return wrapper


def group_command(path: str, **metadata: Any) -> Callable:
    """Register a group-level handler (e.g. ``"llm"`` with no subcommand).

    Same interface as ``@command()`` but also sets the group description.
    """
    if metadata.get("description"):
        _group_descriptions[path] = metadata["description"]
        metadata.pop("description", None)
    return command(path, **metadata)


# ── Dispatch ──────────────────────────────────────────────────────────────


def dispatch(tokens: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """Resolve *tokens* against the registry and call the matching handler.

    Tries longest-prefix match: ``["node", "add", "MyLabel"]`` first tries
    ``"node.add"``, then ``"node"``.
    Positional tokens after the matched path are injected into *flags* using
    param names from the handler's metadata (if defined) or ``_0, _1`` keys.

    Raises:
        CommandNotFound: If no handler matches.
    """
    for i in range(len(tokens), 0, -1):
        key = ".".join(tokens[:i]).lower()
        entry = _commands.get(key)
        if entry is not None:
            handler_fn, metadata = entry
            remaining = list(tokens[i:])

            # Copy flags to avoid mutating the caller's dict
            resolved = dict(flags)

            # Inject positional params into flags using metadata
            params = metadata.get("params", [])
            for idx, val in enumerate(remaining):
                if idx < len(params):
                    pname = params[idx]["name"]
                    if pname not in resolved:
                        resolved[pname] = val
                else:
                    fname = f"_{idx}"
                    if fname not in resolved:
                        resolved[fname] = val

            return handler_fn(remaining, resolved)
    raise CommandNotFound(tokens)


def get_handler_metadata(path: str) -> dict[str, Any] | None:
    """Return the metadata dict for a registered command path, or None."""
    entry = _commands.get(path)
    if entry is not None:
        return entry[1]
    return None


def get_command_level(path: str) -> PermissionLevel:
    """Return the permission level for a command path.

    Uses the ``permission_level`` metadata from the ``@command()`` decorator.
    Defaults to :attr:`PermissionLevel.WRITE` when not explicitly set.
    """
    meta = get_handler_metadata(path)
    if meta is None:
        return PermissionLevel.WRITE
    return meta.get("permission_level", PermissionLevel.WRITE)


# ── Command tree cache ─────────────────────────────────────────────────────

_command_tree_cache: list[dict[str, Any]] | None = None
"""Cached command tree — invalidated when a new handler is registered."""


def _invalidate_cache() -> None:
    """Clear cached tree/definitions so they are rebuilt on next access.

    Called automatically by ``@command()`` / ``@group_command()``.
    """
    global _command_tree_cache, _command_defs_cache
    _command_tree_cache = None
    _command_defs_cache = None


def clear_command_cache() -> None:
    """Public helper: clear cached tree and definitions.

    Useful in tests where handlers are registered dynamically.
    """
    _invalidate_cache()
    global _command_defs_cache
    _command_defs_cache = None


# ── Auto-generated command tree ──────────────────────────────────────────


def get_command_tree() -> list[dict[str, Any]]:
    """Build the command tree from registered handlers.

    The tree is built dynamically from ``@command()`` decorator registrations,
    so it never goes out of sync with available commands.  The result is
    cached and only rebuilt when a new handler is registered.
    """
    global _command_tree_cache
    if _command_tree_cache is not None:
        return list(_command_tree_cache)

    root: dict[str, Any] = {}

    for path_str, (_, meta) in _commands.items():
        parts = path_str.split(".")
        current = root
        for idx, part in enumerate(parts):
            is_last = idx == len(parts) - 1
            if part not in current:
                entry: dict[str, Any] = {"name": part}
                if is_last:
                    entry["description"] = meta.get("description", "")
                    if meta.get("params"):
                        entry["params"] = list(meta["params"])
                    if meta.get("flags"):
                        entry["flags"] = list(meta["flags"])
                    if meta.get("interactive"):
                        entry["interactive"] = True
                else:
                    group_desc = _group_descriptions.get(".".join(parts[:idx + 1]), "")
                    entry["description"] = group_desc
                    entry["children"] = {}
                current[part] = entry
            else:
                # Node exists — if it was a leaf but now needs children, add them
                if not is_last and "children" not in current[part]:
                    # Convert leaf to group node, preserving description
                    existing = current[part]
                    group_desc = _group_descriptions.get(".".join(parts[:idx + 1]), "")
                    children = {}
                    desc = existing.get("description") or group_desc
                    current[part] = {"name": part, "description": desc, "children": children}
                elif is_last and "children" in current[part]:
                    # Node has children and also a direct command handler — set description
                    if meta.get("description"):
                        current[part]["description"] = meta.get("description")
            if not is_last:
                # Navigate into the group node's children dict, not the node itself
                current = current[part]["children"]
            else:
                current = current[part]

    def _to_list(node: dict) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": node["name"],
            "description": node.get("description", ""),
        }
        if "children" in node:
            result["children"] = sorted(
                [_to_list(v) for v in node["children"].values()],
                key=lambda x: x["name"],
            )
        if "params" in node:
            result["params"] = node["params"]
        if "flags" in node:
            result["flags"] = node["flags"]
        if node.get("interactive"):
            result["interactive"] = True
        return result

    _command_tree_cache = sorted(
        [_to_list(v) for v in root.values()],
        key=lambda x: x["name"],
    )
    return list(_command_tree_cache)


# ── Helpers for command definitions ──────────────────────────────────────────

# Maps short param names to human-readable descriptions for tool definitions.
_DERIVED_PARAM_DESC: dict[str, str] = {
    "q": "Search query text",
    "id": "Entity ID or prefix",
    "ids": "Entity IDs",
    "limit": "Maximum number of results",
    "prefix": "Entity ID prefix to match",
    "source": "Source node ID",
    "target": "Target node ID",
    "subject_id": "Subject node ID (the subject in a triple)",
    "predicate_id": "Predicate ID (the relationship type)",
    "object_value": "Object value (node ID or literal)",
    "labels": "Labels as LANG::TEXT or JSON",
    "definitions": "Definitions as LANG::TEXT or JSON",
    "descriptions": "Descriptions as LANG::TEXT or JSON",
    "name": "Entity or command name",
    "new_id": "New ID for rename operation",
    "group_name": "Group name",
    "type": "Entity type filter",
    "message": "Chat message text",
    "key": "Configuration key",
    "value": "Configuration value",
    "locale": "Language locale code (e.g. en, fr, eo)",
    "force": "Skip safety checks and proceed",
}


def _derive_param_description(p: dict, command_desc: str) -> str:
    """Derive a human-readable description for a command parameter.

    Priority: explicit ``description`` field > ``_DERIVED_PARAM_DESC`` map
    > param name > command description snippet.
    """
    explicit = p.get("description", "")
    if explicit:
        return explicit
    mapped = _DERIVED_PARAM_DESC.get(p["name"], "")
    if mapped:
        return mapped
    # Fallback: describe as "<name> for <command>"
    cmd_snippet = command_desc[:60].strip() if command_desc else ""
    if cmd_snippet:
        return f"{p['name']} — for {cmd_snippet.lower()}"
    return p["name"]


# Cache for flattened definitions (derived from tree cache)
_command_defs_cache: list[dict] | None = None


def get_command_definitions(tree: list[dict] | None = None) -> list[dict]:
    """Flatten the command tree into machine-readable definitions for the LLM."""
    global _command_defs_cache
    should_cache = tree is None
    if tree is None:
        if _command_defs_cache is not None:
            return list(_command_defs_cache)
        tree = get_command_tree()
    definitions: list[dict] = []

    def _walk(nodes: list[dict], prefix: list[str] | None = None) -> None:
        for node in nodes:
            path = (prefix or []) + [node["name"]]
            desc = node.get("description", "")
            entry: dict[str, Any] = {
                "path": path,
                "canonical": f"!{' '.join(path)}",
                "description": desc,
            }
            if node.get("params"):
                entry["params"] = [
                    {
                        "name": p["name"],
                        "description": _derive_param_description(p, desc),
                        "required": p.get("required", False),
                        "type": p.get("type", "string"),
                    }
                    for p in node["params"]
                ]
            if node.get("flags"):
                entry["flags"] = [
                    {
                        "name": f["name"],
                        "type": f.get("type", "string"),
                        "required": f.get("required", False),
                        "help": f.get("help", ""),
                    }
                    for f in node["flags"]
                ]
            definitions.append(entry)
            if node.get("children"):
                _walk(node["children"], path)

    _walk(tree)
    if should_cache:
        _command_defs_cache = list(definitions)
    return definitions


def resolve_form_type(tokens: list[str]) -> str | None:
    """Return the interactive form type for a command path, or None."""
    for i in range(len(tokens), 0, -1):
        key = ".".join(tokens[:i])
        if key in _interactive_forms:
            return _interactive_forms[key]
    return None


def dispatch_path(path: str, flags: dict[str, str]) -> dict:
    """Dispatch a command by its dot-separated path.

    Unlike :func:`dispatch`, this takes a pre-split dot-separated path
    directly (e.g. ``"node.search"``) — no token array needed.  Used
    by the LLM tool-calling flow where tool names are already in
    underscore form (``"node_search"`` → ``"node.search"``).

    Returns the same result dict as :func:`dispatch`.
    """
    tokens = path.split(".")
    return dispatch(tokens, flags)


# ── User hooks support ──────────────────────────────────────────────────────

_system_commands: dict[str, tuple[Callable, dict[str, Any]]] = {}
"""Snapshot of system commands taken before user hooks are loaded.
Used by :func:`call_system_command` for delegation."""


def freeze_system_commands() -> None:
    """Snapshot all currently registered commands as the "system" baseline.

    Called **before** loading user hooks from the config directory so
    that user-defined command handlers can delegate to the original
    system implementation via :func:`call_system_command`.
    """
    _system_commands.clear()
    _system_commands.update(_commands)


def call_system_command(
    path: str,
    remaining: list[str] | None = None,
    flags: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Call the original system handler for *path*, bypassing user overrides.

    Useful inside user-defined hook handlers that want to extend rather
    than fully replace a system command::

        from semantika.server.command.registry import (
            command, call_system_command,
        )

        @command("node.add", ...)
        def my_node_add(remaining, flags):
            # custom logic, then delegate
            return call_system_command("node.add", remaining, flags)

    Args:
        path: Dot-separated command path (e.g. ``"node.add"``).
        remaining: Positional tokens to forward.
        flags: Flags dict to forward.

    Returns:
        The result dict from the original handler.

    Raises:
        CommandNotFound: If *path* is not a registered system command.
    """
    entry = _system_commands.get(path)
    if entry is None:
        raise CommandNotFound(path.split("."))
    handler_fn, metadata = entry
    return handler_fn(remaining or [], flags or {})


def load_user_hooks() -> None:
    """Load and register user-defined command hooks from the config dir.

    Scans ``~/.config/semantika/hooks.py`` (or ``SEMANTIKA_CONFIG_DIR``)
    and imports it.  Any ``@command`` / ``@group_command`` decorators in
    that file will register (or override) handlers in the command registry.

    This function should be called **once** during application startup,
    **after** all system handlers are registered and
    :func:`freeze_system_commands` has been called.
    """
    import importlib.util
    from pathlib import Path
    from lightercore.paths import config_dir

    hooks_path = config_dir() / "hooks.py"
    if not hooks_path.exists():
        return

    spec = importlib.util.spec_from_file_location(
        "semantika_user_hooks", hooks_path,
    )
    if spec is None or spec.loader is None:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Could not load user hooks from %s", hooks_path)
        return

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    logger = __import__("logging").getLogger(__name__)
    logger.info("Loaded user hooks from %s", hooks_path)
