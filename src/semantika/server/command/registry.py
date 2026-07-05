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


# ── Auto-generated command tree ──────────────────────────────────────────


def get_command_tree() -> list[dict[str, Any]]:
    """Build the command tree from registered handlers.

    The tree is built dynamically from ``@command()`` decorator registrations,
    so it never goes out of sync with available commands.
    """
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
                    desc = existing.get("description", group_desc)
                    current[part] = {"name": part, "description": desc, "children": children}
                elif is_last and "children" in current[part]:
                    # Node has children and also a direct command handler — set description
                    if meta.get("description"):
                        current[part]["description"] = meta.get("description")
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

    return sorted(
        [_to_list(v) for v in root.values()],
        key=lambda x: x["name"],
    )


def get_command_definitions(tree: list[dict] | None = None) -> list[dict]:
    """Flatten the command tree into machine-readable definitions for the LLM."""
    if tree is None:
        tree = get_command_tree()
    definitions: list[dict] = []

    def _walk(nodes: list[dict], prefix: list[str] | None = None) -> None:
        for node in nodes:
            path = (prefix or []) + [node["name"]]
            entry: dict[str, Any] = {
                "path": path,
                "canonical": f"!{' '.join(path)}",
                "description": node.get("description", ""),
            }
            if node.get("params"):
                entry["params"] = [
                    {"name": p["name"], "required": p.get("required", False), "type": p.get("type", "string")}
                    for p in node["params"]
                ]
            if node.get("flags"):
                entry["flags"] = [
                    {"name": f["name"], "type": f.get("type", "string"), "required": f.get("required", False)}
                    for f in node["flags"]
                ]
            definitions.append(entry)
            if node.get("children"):
                _walk(node["children"], path)

    _walk(tree)
    return definitions


def resolve_form_type(tokens: list[str]) -> str | None:
    """Return the interactive form type for a command path, or None."""
    for i in range(len(tokens), 1, -1):
        key = ".".join(tokens[:i])
        if key in _interactive_forms:
            return _interactive_forms[key]
    return None
