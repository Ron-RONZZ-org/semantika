"""Command dispatch API route.

``POST /api/v1/command`` — Execute a parsed command token list.
``GET /api/v1/command/tree`` — Return the command tree for autocomplete.
``GET /api/v1/command/help`` — Flat help text.

Ported from lighterbird's command dispatch pattern.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from semantika.server.command.errors import CommandError, CommandNotFound, CommandValidationError
from semantika.server.command.models import CommandRequest, CommandResponse

router = APIRouter(tags=["command"])

# ── Interactive command form mapping ──────────────────────────────────────
_INTERACTIVE_FORMS: dict[str, str] = {
    "node.add": "node-add",
    "node.delete": "node-delete",
    "predicate.add": "predicate-add",
    "predicate.delete": "predicate-delete",
    "triple.add": "triple-add",
    "triple.delete": "triple-delete",
    "triple.modify": "triple-modify",
    "unit.add": "unit-add",
    "proof.add": "proof-add",
    "predicate-group.add": "predicate-group-add",
    "reset": "reset-no-backup",
}


def _resolve_form_type(tokens: list[str]) -> str | None:
    for i in range(len(tokens), 1, -1):
        key = ".".join(tokens[:i])
        if key in _INTERACTIVE_FORMS:
            return _INTERACTIVE_FORMS[key]
    return None


# ── Command tree ─────────────────────────────────────────────────────────

def get_command_tree() -> list[dict]:
    """Return the full structured command tree for autocomplete."""
    return [
        {
            "name": "node",
            "description": "Manage knowledge graph nodes",
            "children": [
                {"name": "list", "description": "List all nodes", "params": [{"name": "limit", "type": "number", "default": 100}]},
                {"name": "search", "description": "Search nodes by label", "params": [{"name": "q", "type": "string", "required": True}]},
                {"name": "view", "description": "View a node and its triples", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a new node", "interactive": True, "params": [{"name": "labels", "type": "string"}]},
                {"name": "update", "description": "Update node labels/definitions", "params": [
                    {"name": "id", "type": "string", "required": True},
                    {"name": "labels", "type": "string"},
                ], "flags": [
                    {"name": "definitions", "type": "string", "help": "New definitions (JSON or LANG::TEXT)"},
                    {"name": "new-id", "type": "string", "help": "Rename to new ID"},
                ]},
                {"name": "delete", "description": "Delete nodes (multiple IDs or --prefix)", "interactive": True, "params": [{"name": "id", "type": "string"}], "flags": [
                    {"name": "prefix", "type": "string", "help": "Delete all nodes with this ID prefix"},
                ]},
                {"name": "merge", "description": "Merge source node into target node", "params": [
                    {"name": "source", "type": "string", "required": True},
                    {"name": "target", "type": "string", "required": True},
                ]},
                {"name": "rename", "description": "Rename a node", "params": [
                    {"name": "id", "type": "string", "required": True},
                    {"name": "new_id", "type": "string", "required": True},
                ]},
            ],
        },
        {
            "name": "predicate",
            "description": "Manage predicates (semantic properties)",
            "children": [
                {"name": "list", "description": "List all predicates"},
                {"name": "search", "description": "Search predicates", "params": [{"name": "q", "type": "string", "required": True}], "flags": [
                    {"name": "wikidata", "type": "flag", "help": "Also search Wikidata"},
                ]},
                {"name": "view", "description": "View predicate details", "params": [{"name": "predicate_id", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a predicate", "interactive": True, "params": [{"name": "predicate_id", "type": "string", "required": True}], "flags": [
                    {"name": "wikidata", "type": "flag", "help": "Auto-fetch labels from Wikidata"},
                    {"name": "labels", "type": "string", "help": "Labels as LANG::TEXT (repeatable)"},
                    {"name": "descriptions", "type": "string", "help": "Descriptions as LANG::TEXT (repeatable)"},
                ]},
                {"name": "update", "description": "Update a predicate", "params": [
                    {"name": "predicate_id", "type": "string", "required": True},
                ], "flags": [
                    {"name": "labels", "type": "string", "help": "Labels as LANG::TEXT (repeatable)"},
                    {"name": "descriptions", "type": "string", "help": "Descriptions as LANG::TEXT (repeatable)"},
                    {"name": "replace", "type": "flag", "help": "Replace instead of merging labels/descriptions"},
                    {"name": "new-id", "type": "string", "help": "Rename to new ID"},
                ]},
                {"name": "delete", "description": "Delete predicates (multiple IDs or --prefix)", "interactive": True, "params": [{"name": "predicate_id", "type": "string"}], "flags": [
                    {"name": "prefix", "type": "string", "help": "Delete all predicates with this ID prefix"},
                ]},
                {"name": "rename", "description": "Rename a predicate", "params": [
                    {"name": "predicate_id", "type": "string", "required": True},
                    {"name": "new_id", "type": "string", "required": True},
                ]},
            ],
        },
        {
            "name": "predicate-group",
            "description": "Manage predicate groups",
            "children": [
                {"name": "list", "description": "List all predicate groups"},
                {"name": "view", "description": "View group details and members", "params": [{"name": "name", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a predicate group", "interactive": True, "params": [{"name": "name", "type": "string", "required": True}]},
                {"name": "rename", "description": "Rename a predicate group", "params": [
                    {"name": "name", "type": "string", "required": True},
                    {"name": "new_name", "type": "string", "required": True},
                ]},
                {"name": "delete", "description": "Delete predicate groups", "params": [{"name": "name", "type": "string", "required": True}]},
                {"name": "search", "description": "Search groups by name", "params": [{"name": "q", "type": "string", "required": True}]},
                {"name": "add-member", "description": "Add predicate to group", "params": [
                    {"name": "group", "type": "string", "required": True},
                    {"name": "predicate_id", "type": "string", "required": True},
                ]},
                {"name": "remove-member", "description": "Remove predicate from group", "params": [
                    {"name": "group", "type": "string", "required": True},
                    {"name": "predicate_id", "type": "string", "required": True},
                ]},
            ],
        },
        {
            "name": "triple",
            "description": "Manage subject-predicate-object arcs",
            "children": [
                {"name": "list", "description": "List all triples"},
                {"name": "add", "description": "Add a triple", "interactive": True, "params": [
                    {"name": "subject_id", "type": "string", "required": True},
                    {"name": "predicate_id", "type": "string", "required": True},
                    {"name": "object_value", "type": "string", "required": True},
                ], "flags": [
                    {"name": "str", "type": "flag", "help": "Object is a string literal"},
                    {"name": "int", "type": "flag", "help": "Object is an integer literal"},
                    {"name": "float", "type": "flag", "help": "Object is a float literal"},
                    {"name": "bool", "type": "flag", "help": "Object is a boolean literal"},
                    {"name": "lang", "type": "string", "help": "Language tag (with --str)"},
                    {"name": "unit", "type": "string", "help": "Unit node ID (with --int/--float)"},
                    {"name": "katex", "type": "string", "help": "KaTeX formula"},
                    {"name": "str-dosiero", "type": "string", "help": "Read file as string literal"},
                    {"name": "kodlingvo", "type": "string", "help": "Programming language for code block"},
                ]},
                {"name": "delete", "description": "Delete a triple (interactive picker if args partial)", "interactive": True, "params": [
                    {"name": "subject", "type": "string", "required": True},
                    {"name": "predicate", "type": "string"},
                    {"name": "object", "type": "string"},
                ]},
                {"name": "modify", "description": "Modify an existing triple", "interactive": True, "params": [
                    {"name": "subject", "type": "string", "required": True},
                    {"name": "predicate", "type": "string"},
                    {"name": "object", "type": "string"},
                ], "flags": [
                    {"name": "new-subject", "type": "string", "help": "New subject ID"},
                    {"name": "new-predicate", "type": "string", "help": "New predicate ID"},
                    {"name": "new-object", "type": "string", "help": "New object value"},
                    {"name": "str", "type": "flag", "help": "New object is a string literal"},
                    {"name": "int", "type": "flag", "help": "New object is integer literal"},
                    {"name": "float", "type": "flag", "help": "New object is float literal"},
                    {"name": "bool", "type": "flag", "help": "New object is boolean literal"},
                    {"name": "lang", "type": "string", "help": "Language tag"},
                    {"name": "unit", "type": "string", "help": "Unit node ID"},
                    {"name": "katex", "type": "string", "help": "KaTeX formula"},
                    {"name": "str-dosiero", "type": "string", "help": "Read file as string"},
                ]},
                {"name": "view", "description": "View all triples for a node", "params": [{"name": "id", "type": "string", "required": True}]},
            ],
        },
        {
            "name": "unit",
            "description": "Manage unit ontology",
            "children": [
                {"name": "list", "description": "List all units"},
                {"name": "view", "description": "View unit details", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "resolve", "description": "Resolve a unit expression", "params": [{"name": "expr", "type": "string", "required": True}]},
                {"name": "decompose", "description": "Decompose a compound unit", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a custom unit", "interactive": True},
            ],
        },
        {
            "name": "search",
            "description": "Full-text search across the graph",
            "params": [{"name": "q", "type": "string", "required": True}],
            "flags": [
                {"name": "date-from", "type": "string", "help": "Start date (ISO or YYYYMMDD)"},
                {"name": "date-to", "type": "string", "help": "End date (ISO or YYYYMMDD)"},
                {"name": "limit", "type": "number", "help": "Max results"},
            ],
        },
        {
            "name": "view",
            "description": "View all triples for a node (alias for triple view)",
            "params": [{"name": "id", "type": "string", "required": True}],
        },
        {
            "name": "trash",
            "description": "Manage soft-deleted items",
            "children": [
                {"name": "list", "description": "List trashed nodes"},
                {"name": "restore", "description": "Restore a trashed node", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "delete", "description": "Permanently delete from trash", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "purge", "description": "Permanently delete old trash entries", "params": [{"name": "days", "type": "number"}]},
            ],
        },
        {"name": "export", "description": "Export graph in Turtle format", "flags": [
            {"name": "output", "type": "string", "help": "Output file path"},
            {"name": "base-uri", "type": "string", "help": "Custom base URI"},
        ]},
        {"name": "import", "description": "Import Turtle (.ttl) data", "params": [{"name": "data", "type": "string", "required": True}]},
        {"name": "stats", "description": "Show graph statistics"},
        {
            "name": "review",
            "description": "Interactive triple review (view and quiz modes)",
            "children": [
                {"name": "start", "description": "Start a review session", "params": [
                    {"name": "mode", "type": "string", "help": "view or quiz (default: view)"},
                ], "flags": [
                    {"name": "date-from", "type": "string", "help": "Start date filter (ISO or YYYYMMDD)"},
                    {"name": "date-to", "type": "string", "help": "End date filter (ISO or YYYYMMDD)"},
                    {"name": "limit", "type": "number", "help": "Number of questions (default: 10)"},
                ]},
                {"name": "sessions", "description": "List past review sessions"},
                {"name": "view", "description": "View session details", "params": [{"name": "uuid", "type": "string", "required": True}]},
                {"name": "delete", "description": "Delete a review session", "params": [{"name": "uuid", "type": "string", "required": True}]},
            ],
        },
        {
            "name": "proof",
            "description": "Manage proofs (evidence attached to triples)",
            "children": [
                {"name": "add", "description": "Add proof to a triple", "interactive": True, "params": [
                    {"name": "subject_id", "type": "string", "required": True},
                    {"name": "predicate_id", "type": "string", "required": True},
                    {"name": "object_value", "type": "string", "required": True},
                ], "flags": [
                    {"name": "proof-type", "type": "string", "help": "Type (observation, experiment, reference, etc.)"},
                    {"name": "source", "type": "string", "help": "Source citation"},
                    {"name": "notes", "type": "string", "help": "Notes about this proof"},
                ]},
                {"name": "view", "description": "View proofs for a triple", "params": [
                    {"name": "subject_id", "type": "string", "required": True},
                    {"name": "predicate_id", "type": "string", "required": True},
                    {"name": "object_value", "type": "string", "required": True},
                ]},
                {"name": "delete", "description": "Delete a proof", "params": [{"name": "uuid", "type": "string", "required": True}]},
            ],
        },
        {
            "name": "llm",
            "description": "Manage LLM provider configuration",
            "children": [
                {"name": "show", "description": "Show current LLM configuration", "params": []},
                {"name": "profiles", "description": "List saved LLM profiles"},
                {"name": "new", "description": "Create a new LLM config", "params": [
                    {"name": "provider_type", "type": "string", "required": True},
                ], "flags": [
                    {"name": "api-key", "type": "string", "help": "API key"},
                    {"name": "base-url", "type": "string", "help": "Base URL for the API"},
                    {"name": "model", "type": "string", "help": "Model name"},
                    {"name": "temperature", "type": "number", "help": "Temperature (0-2)"},
                    {"name": "max-tokens", "type": "number", "help": "Max tokens per response"},
                    {"name": "alias", "type": "string", "help": "Save as a named profile"},
                ]},
                {"name": "set", "description": "Modify current LLM settings", "params": [], "flags": [
                    {"name": "provider-type", "type": "string", "help": "Provider type (openai, deepseek, ollama, custom)"},
                    {"name": "api-key", "type": "string", "help": "API key"},
                    {"name": "base-url", "type": "string", "help": "Base URL for the API"},
                    {"name": "model", "type": "string", "help": "Model name"},
                    {"name": "temperature", "type": "number", "help": "Temperature (0-2)"},
                    {"name": "max-tokens", "type": "number", "help": "Max tokens per response"},
                    {"name": "alias", "type": "string", "help": "Save as a named profile"},
                ]},
                {"name": "clear", "description": "Clear LLM provider configuration"},
                {"name": "profile", "description": "Manage named profiles", "children": [
                    {"name": "list", "description": "List saved profiles"},
                    {"name": "show", "description": "Show current profile details"},
                    {"name": "load", "description": "Activate a saved profile", "params": [
                        {"name": "name", "type": "string", "required": True},
                    ]},
                    {"name": "delete", "description": "Delete a saved profile", "params": [
                        {"name": "name", "type": "string", "required": True},
                    ]},
                ]},
            ],
        },
        {
            "name": "backup",
            "description": "Database backup and restore",
            "children": [
                {"name": "now", "description": "Create timestamped DB backup for all strategies"},
                {"name": "list", "description": "List available backup snapshots"},
                {"name": "restore", "description": "Restore from latest (or --timestamp) backup"},
                {"name": "prune", "description": "Delete old backups, keeping N newest", "params": [{"name": "keep", "type": "number"}]},
                {
                    "name": "config",
                    "description": "Backup strategy management",
                    "children": [
                        {"name": "list", "description": "List backup strategies"},
                        {"name": "add", "description": "Add a backup strategy", "params": [
                            {"name": "id", "type": "string", "required": True},
                            {"name": "label", "type": "string"},
                            {"name": "interval", "type": "number"},
                            {"name": "max_copies", "type": "number"},
                            {"name": "target", "type": "string"},
                            {"name": "enabled", "type": "string"},
                        ]},
                        {"name": "modify", "description": "Modify a backup strategy", "params": [{"name": "id", "type": "string", "required": True}]},
                        {"name": "delete", "description": "Delete a backup strategy", "params": [{"name": "id", "type": "string", "required": True}]},
                        {"name": "test", "description": "Test a strategy's target directory", "params": [{"name": "id", "type": "string", "required": True}]},
                    ],
                },
                {"name": "export", "description": "Export all data to a portable zip", "params": [{"name": "output", "type": "string"}]},
                {"name": "import", "description": "Import data from an export zip", "params": [{"name": "path", "type": "string", "required": True}]},
            ],
        },
        {
            "name": "reset",
            "description": "Reset Semantika to a fresh state (backup first!)",
            "params": [
                {"name": "path", "type": "string", "placeholder": "/path/to/backup.db"},
            ],
            "flags": [
                {"name": "no-backup", "type": "flag", "help": "Skip backup and delete everything (irreversible!)"},
            ],
        },
    ]


# ── Tree-based command resolution ────────────────────────────────────────

def _resolve_command_path(
    tokens: list[str],
    tree: list[dict],
) -> tuple[list[str], list[str], dict] | None:
    """Walk the command tree to separate path tokens from positional params.

    Returns (cmd_tokens, remaining_tokens, merged_flags) or None if no match.
    Extra positional tokens are injected into *merged_flags* using param names
    defined on the leaf node.
    """
    cmd_tokens: list[str] = []
    remaining = list(tokens)
    current_level = tree
    leaf_node = None

    while remaining and current_level:
        token = remaining[0].lower()
        matched = None
        for child in current_level:
            if child["name"].lower() == token:
                matched = child
                break
        if not matched:
            break
        cmd_tokens.append(remaining.pop(0))
        if matched.get("children"):
            current_level = matched["children"]
        else:
            leaf_node = matched
            break

    if not cmd_tokens:
        return None

    # Remaining tokens become positional params
    params = leaf_node.get("params") if leaf_node else []
    merged = {}
    param_idx = 0
    for val in remaining:
        if param_idx < len(params):
            merged[params[param_idx]["name"]] = val
            param_idx += 1
        else:
            # Extra positional — store with numeric key
            merged[f"_{param_idx}"] = val
            param_idx += 1

    return cmd_tokens, remaining, merged


# ── Dispatch ─────────────────────────────────────────────────────────────

def _dispatch(tokens: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """Dispatch a command to the appropriate handler."""
    from semantika.graph.db import get_services

    # Resolve command path using the tree
    resolved = _resolve_command_path(tokens, get_command_tree())
    if resolved is None:
        raise CommandNotFound(tokens)
    cmd_tokens, remaining, positional = resolved

    # Merge: explicitly provided flags override positional auto-detection
    merged = {**positional, **flags}
    path = ".".join(cmd_tokens).lower()
    svc = get_services()

    # ── Stats ─────────────────────────────────────────────────────────
    if path == "stats":
        return {"type": "status", "data": svc["triple"].get_stats()}

    # ── Export ────────────────────────────────────────────────────────
    if path == "export":
        base_uri = flags.get("base_uri", "https://example.org/")
        ttl = svc["triple"].export_turtle(base_uri=base_uri)
        output = flags.get("output", "")
        if output:
            try:
                Path(output).write_text(ttl, encoding="utf-8")
                return {"type": "status", "data": {"message": f"Exported to {output}"}}
            except OSError as e:
                raise CommandValidationError(f"Could not write to {output}: {e}")
        return {"type": "status", "data": {"ttl": ttl[:500] + "..." if len(ttl) > 500 else ttl}}

    # ── Import ────────────────────────────────────────────────────────
    if path == "import":
        ttl_content = merged.get("data") or (remaining and remaining[0]) or ""
        if not ttl_content:
            raise CommandValidationError("Provide TTL content via data= flag")
        from semantika.graph.triple_turtle import import_turtle as _import
        stats = _import(ttl_content)
        return {"type": "status", "data": stats}

    # ── Search ────────────────────────────────────────────────────────
    if path == "search":
        q = merged.get("q") or ""
        if not q:
            raise CommandValidationError("Enter a search query")
        date_from = flags.get("date_from") or flags.get("date-from") or None
        date_to = flags.get("date_to") or flags.get("date-to") or None
        raw_limit = flags.get("limit", "50")
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 50
        nodes = svc["node"].search(q, limit=limit)
        predicates = svc["predicate"].search(q, limit=limit)
        triples = svc["triple"].search_by_labels(
            subject=q, limit=limit,
            created_after=date_from, created_before=date_to,
        ) or []
        pred_triples = svc["triple"].search_by_labels(
            predicate=q, limit=limit,
            created_after=date_from, created_before=date_to,
        ) or []
        all_triples = list({t["subject_id"] + t["predicate_id"] + t["object_value"]: t for t in triples + pred_triples}.values())
        return {
            "type": "status",
            "data": {
                "nodes": nodes,
                "predicates": predicates,
                "triples": all_triples[:limit],
                "_summary": f"Nodes: {len(nodes)}, Predicates: {len(predicates)}, Triples: {len(all_triples)}",
            },
        }

    # ── View (root command, alias for triple view) ────────────────────
    if path == "view":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        node = svc["node"].resolve_node_id_prefix(node_id)
        if not node:
            raise CommandValidationError(f"Node not found: {node_id}")
        triples = svc["triple"].get_by_subject(node["node_id"])
        node["triples"] = triples
        return {"type": "status", "data": node}

    # ── Node commands ─────────────────────────────────────────────────
    if path == "node.list":
        nodes = svc["node"].list(limit=int(merged.get("limit", 100)))
        return {"type": "table", "data": nodes, "label": "Nodes"}

    if path == "node.search":
        q = merged.get("q", "")
        if not q:
            raise CommandValidationError("Enter a search term")
        nodes = svc["node"].search(q)
        return {"type": "table", "data": nodes, "label": f"Nodes matching '{q}'"}

    if path == "node.view":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        node = svc["node"].resolve_node_id_prefix(node_id)
        if not node:
            raise CommandValidationError(f"Node not found: {node_id}")
        triples = svc["triple"].get_by_subject(node["node_id"])
        node["triples"] = triples
        return {"type": "status", "data": node}

    if path == "node.add":
        labels_raw = merged.get("labels") or (remaining and remaining[0]) or ""
        payload = {"labels": {"en": labels_raw}} if labels_raw else {"labels": {}}
        try:
            node = svc["node"].create(payload)
            msg = f"Created node {node['node_id']}"
            if labels_raw:
                msg += f" with label \"{labels_raw}\""
            return {"type": "status", "data": {"message": msg, "node": node}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "node.update":
        node_id = merged.get("id") or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        node = svc["node"].resolve_node_id_prefix(node_id)
        if not node:
            raise CommandValidationError(f"Node not found: {node_id}")
        payload: dict = {}
        labels_raw = merged.get("labels") or ""
        if labels_raw:
            try:
                labels_dict = json.loads(labels_raw) if labels_raw.startswith("{") else _parse_lang_tag_pairs(labels_raw)
            except json.JSONDecodeError:
                labels_dict = {"en": labels_raw}
            payload["labels"] = labels_dict
        defs_raw = flags.get("definitions") or flags.get("defs") or ""
        if defs_raw:
            try:
                defs_dict = json.loads(defs_raw) if defs_raw.startswith("{") else _parse_lang_tag_pairs(defs_raw)
            except json.JSONDecodeError:
                defs_dict = {"en": defs_raw}
            payload["definitions"] = defs_dict
        new_id = flags.get("new_id") or flags.get("new-id") or ""
        try:
            if new_id:
                result = svc["node"].update_node_id(node_id, new_id, data=payload if payload else None)
                return {"type": "status", "data": {"message": f"Updated node {node_id} -> {new_id}", "node": result}}
            elif payload:
                result = svc["node"].update(node_id, payload)
                return {"type": "status", "data": {"message": f"Updated node {node_id}", "node": result}}
            else:
                raise CommandValidationError("No changes specified (use --labels, --definitions, or --new-id)")
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "node.delete":
        ids: list[str] = []
        pos_id = merged.get("id") or ""
        if pos_id:
            ids.append(pos_id)
        # Extra positional tokens are additional IDs
        for k, v in merged.items():
            if k.startswith("_") and v:
                ids.append(v)
        prefix = flags.get("prefix") or ""
        if prefix:
            prefix_nodes = svc["node"].db.execute(
                "SELECT * FROM nodes WHERE node_id LIKE ? ORDER BY node_id",
                (f"{prefix}%",),
            )
            seen = set(ids)
            for n in prefix_nodes:
                if n["node_id"] not in seen:
                    ids.append(n["node_id"])
        if not ids:
            raise CommandValidationError("Specify node ID(s) or use --prefix")
        deleted = 0
        errors = []
        for nid in ids:
            try:
                svc["triple"].remove(subject_id=nid)
                svc["triple"].remove(object_value=nid)
                svc["node"].delete(nid, soft=True)
                deleted += 1
            except Exception as e:
                errors.append(f"{nid}: {e}")
        msg = f"Deleted {deleted} node(s)"
        if errors:
            msg += f" ({len(errors)} error(s))"
        return {"type": "status", "data": {"message": msg, "errors": errors}}

    if path == "node.rename":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        new_id = merged.get("new_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        if not node_id or not new_id:
            raise CommandValidationError("Specify current and new node ID")
        try:
            result = svc["node"].update_node_id(node_id, new_id)
            return {"type": "status", "data": {"message": f"Renamed {node_id} → {new_id}", "node": result}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "node.merge":
        source = merged.get("source") or (remaining and remaining[0] if len(remaining) > 0 else "") or ""
        target = merged.get("target") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        if not source or not target:
            raise CommandValidationError("Specify source and target node IDs")
        try:
            result = svc["node"].merge_nodes(source, target)
            return {"type": "status", "data": {"message": f"Merged {source} into {target}", "node": result}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    # ── Predicate commands ────────────────────────────────────────────
    if path == "predicate.list":
        preds = svc["predicate"].list()
        return {"type": "table", "data": preds, "label": "Predicates"}

    if path == "predicate.search":
        q = merged.get("q", "")
        results = svc["predicate"].search(q)
        wikidata_flag = "wikidata" in flags or flags.get("wikidata", "").lower() in ("true", "1", "yes")
        if wikidata_flag:
            try:
                from semantika.graph.node_helpers import search_wikidata
                wd_results = search_wikidata(q)
                local_ids = {r["predicate_id"] for r in results}
                for wd in wd_results:
                    if wd["predicate_id"] not in local_ids:
                        results.append(wd)
            except Exception:
                pass  # Wikidata search is best-effort
        return {"type": "table", "data": results, "label": f"Predicates matching '{q}'"}

    if path == "predicate.view":
        pred_id = merged.get("predicate_id") or (remaining and remaining[0]) or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        pred = svc["predicate"].get(pred_id)
        if not pred:
            raise CommandValidationError(f"Predicate not found: {pred_id}")
        return {"type": "status", "data": pred}

    if path == "predicate.add":
        pred_id = merged.get("predicate_id") or (remaining and remaining[0]) or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        labels_raw = flags.get("labels") or ""
        descs_raw = flags.get("descriptions") or ""
        wikidata_flag = "wikidata" in flags or flags.get("wikidata", "").lower() in ("true", "1", "yes")
        data: dict = {"predicate_id": pred_id}
        if labels_raw:
            try:
                data["labels"] = json.loads(labels_raw) if labels_raw.startswith("{") else _parse_lang_tag_pairs(labels_raw)
            except json.JSONDecodeError:
                data["labels"] = {"en": labels_raw}
        if descs_raw:
            try:
                data["descriptions"] = json.loads(descs_raw) if descs_raw.startswith("{") else _parse_lang_tag_pairs(descs_raw)
            except json.JSONDecodeError:
                data["descriptions"] = {"en": descs_raw}
        if wikidata_flag:
            data["source"] = "wikidata"
            try:
                from semantika.graph.node_helpers import fetch_wikidata_details
                wd = fetch_wikidata_details(pred_id)
                if wd:
                    data.setdefault("labels", {}).update(wd.get("labels", {}))
                    data.setdefault("descriptions", {}).update(wd.get("descriptions", {}))
            except Exception:
                pass  # Best-effort
        try:
            pred = svc["predicate"].create(data)
            return {"type": "status", "data": {"message": f"Created predicate {pred['predicate_id']}", "predicate": pred}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate.update":
        pred_id = merged.get("predicate_id") or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        existing = svc["predicate"].get(pred_id)
        if not existing:
            raise CommandValidationError(f"Predicate not found: {pred_id}")
        payload = {}
        labels_raw = merged.get("labels") or ""
        descs_raw = flags.get("descriptions") or ""
        replace = "replace" in flags or flags.get("replace", "").lower() in ("true", "1", "yes")
        if labels_raw:
            parsed = _parse_lang_tag_pairs(labels_raw)
            if replace:
                payload["labels"] = parsed
            else:
                merged_labels = _safe_json_loads(existing.get("labels", "{}"))
                merged_labels.update(parsed)
                payload["labels"] = merged_labels
        if descs_raw:
            parsed = _parse_lang_tag_pairs(descs_raw)
            if replace:
                payload["descriptions"] = parsed
            else:
                merged_descs = _safe_json_loads(existing.get("descriptions", "{}"))
                merged_descs.update(parsed)
                payload["descriptions"] = merged_descs
        new_id = flags.get("new_id") or flags.get("new-id") or ""
        try:
            if new_id:
                svc["predicate"].update_predicate_id(pred_id, new_id, updates=payload if payload else None)
                return {"type": "status", "data": {"message": f"Renamed {pred_id} → {new_id}"}}
            elif payload:
                svc["predicate"].update(pred_id, payload)
                return {"type": "status", "data": {"message": f"Updated {pred_id}"}}
            else:
                raise CommandValidationError("No changes specified (use --labels, --descriptions, or --new-id)")
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate.rename":
        pred_id = merged.get("predicate_id") or (remaining and remaining[0]) or ""
        new_id = merged.get("new_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        if not pred_id or not new_id:
            raise CommandValidationError("Specify current and new predicate ID")
        try:
            result = svc["predicate"].update_predicate_id(pred_id, new_id)
            return {"type": "status", "data": {"message": f"Renamed {pred_id} → {new_id}", "predicate": result}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate.delete":
        ids: list[str] = []
        pos_id = merged.get("predicate_id") or ""
        if pos_id:
            ids.append(pos_id)
        for k, v in merged.items():
            if k.startswith("_") and v:
                ids.append(v)
        prefix = flags.get("prefix") or ""
        if prefix:
            prefix_preds = svc["predicate"].db.execute(
                "SELECT * FROM predicates WHERE predicate_id LIKE ? ORDER BY predicate_id",
                (f"{prefix}%",),
            )
            seen = set(ids)
            for p in prefix_preds:
                if p["predicate_id"] not in seen:
                    ids.append(p["predicate_id"])
        if not ids:
            raise CommandValidationError("Specify predicate ID(s) or use --prefix")
        deleted = 0
        errors = []
        for pid in ids:
            try:
                svc["triple"].remove(predicate_id=pid)
                svc["predicate"].delete(pid, soft=True)
                deleted += 1
            except Exception as e:
                errors.append(f"{pid}: {e}")
        msg = f"Deleted {deleted} predicate(s)"
        if errors:
            msg += f" ({len(errors)} error(s))"
        return {"type": "status", "data": {"message": msg, "errors": errors}}

    # ── Predicate Group commands ──────────────────────────────────────
    if path == "predicate-group.list":
        groups = svc["predicate_group"].list()
        return {"type": "table", "data": groups, "label": "Predicate Groups"}

    if path == "predicate-group.view":
        name = merged.get("name") or (remaining and remaining[0]) or ""
        if not name:
            raise CommandValidationError("Specify a group name")
        group = svc["predicate_group"].get_by_field("group_name", name)
        if not group:
            raise CommandValidationError(f"Group not found: {name}")
        members = svc["predicate_group"].list_members(name)
        group["members"] = members
        return {"type": "status", "data": group}

    if path == "predicate-group.add":
        name = merged.get("name") or (remaining and remaining[0]) or ""
        if not name:
            raise CommandValidationError("Specify a group name")
        try:
            svc["predicate_group"].create({"group_name": name})
            return {"type": "status", "data": {"message": f"Created group '{name}'"}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate-group.rename":
        name = merged.get("name") or (remaining and remaining[0]) or ""
        new_name = merged.get("new_name") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        if not name or not new_name:
            raise CommandValidationError("Specify current and new group name")
        try:
            svc["predicate_group"].rename(name, new_name)
            return {"type": "status", "data": {"message": f"Renamed '{name}' → '{new_name}'"}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate-group.delete":
        name = merged.get("name") or (remaining and remaining[0]) or ""
        if not name:
            raise CommandValidationError("Specify a group name")
        group = svc["predicate_group"].get_by_field("group_name", name)
        if not group:
            raise CommandValidationError(f"Group not found: {name}")
        try:
            svc["predicate_group"].clear_members(group["uuid"])
            svc["predicate_group"].delete(group["uuid"])
            return {"type": "status", "data": {"message": f"Deleted group '{name}'"}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate-group.search":
        q = merged.get("q") or (remaining and remaining[0]) or ""
        if not q:
            raise CommandValidationError("Enter a search term")
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        results = svc["predicate_group"].db.execute(
            "SELECT * FROM predicate_groups WHERE group_name LIKE ? ESCAPE '\\'",
            (f"%{escaped}%",),
        )
        return {"type": "table", "data": results, "label": f"Groups matching '{q}'"}

    if path == "predicate-group.add-member":
        group_name = merged.get("group") or (remaining and remaining[0]) or ""
        pred_id = merged.get("predicate_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        if not group_name or not pred_id:
            raise CommandValidationError("Specify group name and predicate_id")
        try:
            svc["predicate_group"].add_member(group_name, pred_id)
            return {"type": "status", "data": {"message": f"Added {pred_id} to '{group_name}'"}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate-group.remove-member":
        group_name = merged.get("group") or (remaining and remaining[0]) or ""
        pred_id = merged.get("predicate_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        if not group_name or not pred_id:
            raise CommandValidationError("Specify group name and predicate_id")
        try:
            svc["predicate_group"].remove_member(group_name, pred_id)
            return {"type": "status", "data": {"message": f"Removed {pred_id} from '{group_name}'"}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    # ── Triple commands ──────────────────────────────────────────────
    if path == "triple.list":
        triples = svc["triple"].db.execute("SELECT * FROM triples ORDER BY subject_id, predicate_id LIMIT ?", (100,))
        return {"type": "table", "data": triples, "label": "Triples"}

    if path == "triple.view":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        triples = svc["triple"].get_by_subject(node_id)
        if not triples:
            return {"type": "status", "data": {"message": f"No triples found for {node_id}", "triples": []}}
        return {"type": "table", "data": triples, "label": f"Triples for {node_id}"}

    if path == "triple.add":
        subject_id = merged.get("subject_id") or (remaining and remaining[0]) or ""
        predicate_id = merged.get("predicate_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        object_value = merged.get("object_value") or (remaining and remaining[2] if len(remaining) > 2 else "") or ""
        if not subject_id or not predicate_id or not object_value:
            raise CommandValidationError("Specify subject_id, predicate_id, and object_value")

        # Determine object type and value from flags
        str_flag = "str" in flags or flags.get("str", "").lower() in ("true", "1", "yes")
        int_flag = "int" in flags or flags.get("int", "").lower() in ("true", "1", "yes")
        float_flag = "float" in flags or flags.get("float", "").lower() in ("true", "1", "yes")
        bool_flag = "bool" in flags or flags.get("bool", "").lower() in ("true", "1", "yes")
        lang = flags.get("lang", None)
        unit = flags.get("unit", None)
        katex = flags.get("katex", None)
        str_dosiero = flags.get("str_dosiero", None) or flags.get("str-dosiero", None)
        kodlingvo = flags.get("kodlingvo", None)

        # Resolve object source
        if katex is not None:
            object_value = katex.strip().strip("$")
            object_type = "literal"
            object_datatype = "text/katex"
        elif str_dosiero is not None:
            try:
                object_value = Path(str_dosiero).read_text(encoding="utf-8")
            except (FileNotFoundError, OSError) as e:
                raise CommandValidationError(f"Could not read file: {e}")
            object_type = "literal"
            object_datatype = "text/plain"
            str_flag = True
            if kodlingvo:
                object_datatype = f"text/x-{kodlingvo}"
        elif str_flag:
            object_type = "literal"
        elif int_flag:
            object_type = "literal"
            object_datatype = "xsd:integer"
        elif float_flag:
            object_type = "literal"
            object_datatype = "xsd:decimal"
        elif bool_flag:
            object_type = "literal"
            object_datatype = "xsd:boolean"
        else:
            object_type = "uri"
            object_datatype = None

        object_lang = lang if str_flag else None

        # Resolve subject/object IDs for URI type
        try:
            if object_type == "uri":
                obj_node = svc["node"].resolve_node_id_prefix(object_value)
                if not obj_node:
                    obj_node = svc["node"].resolve_node_id_substring(object_value)
                if not obj_node:
                    raise CommandValidationError(f"Object node not found: {object_value}")
                object_value = obj_node["node_id"]
        except Exception as e:
            if "Ambiguous" in str(e):
                raise CommandValidationError(str(e))

        try:
            triple = svc["triple"].add(
                subject_id=subject_id,
                predicate_id=predicate_id,
                object_value=object_value,
                object_type=object_type,
                object_lang=object_lang,
                object_datatype=object_datatype,
                object_unit=unit,
            )
            return {"type": "status", "data": {"message": f"Added triple: {subject_id} → {predicate_id} → {object_value}", "triple": triple}}
        except ValueError as e:
            # Duplicate handling: offer metadata update
            existing = svc["triple"].get_one(subject_id, predicate_id, object_value, object_type)
            if existing:
                changes = {}
                if object_lang is not None and object_lang != existing.get("object_lang"):
                    changes["object_lang"] = object_lang
                if object_datatype is not None and object_datatype != existing.get("object_datatype"):
                    changes["object_datatype"] = object_datatype
                if unit is not None and unit != existing.get("object_unit"):
                    changes["object_unit"] = unit
                if changes:
                    svc["triple"].update_metadata(
                        subject_id, predicate_id, object_value, object_type,
                        **changes,
                    )
                    return {"type": "status", "data": {"message": "Triple already existed — metadata updated", "changes": changes}}
                return {"type": "status", "data": {"message": "Triple already exists with identical metadata"}}
            raise CommandValidationError(str(e))

    if path == "triple.delete":
        subject = merged.get("subject") or (remaining and remaining[0]) or ""
        predicate = merged.get("predicate") or (remaining and remaining[1] if len(remaining) > 1 else "")
        object_val = merged.get("object") or (remaining and remaining[2] if len(remaining) > 2 else "")

        if not subject:
            raise CommandValidationError("Specify a subject")

        # Try to find the triple(s)
        if predicate and object_val:
            # Full SPO — direct delete
            triple = svc["triple"].get_one(subject, predicate, object_val)
            if not triple:
                # Try to resolve as URI
                try:
                    obj_node = svc["node"].resolve_node_id_prefix(object_val)
                    if obj_node:
                        triple = svc["triple"].get_one(subject, predicate, obj_node["node_id"])
                        if triple:
                            object_val = obj_node["node_id"]
                except Exception:
                    pass
            if not triple:
                raise CommandValidationError("Triple not found")
            svc["proof"].cascade_delete_proofs(subject, predicate, object_val)
            svc["triple"].remove(subject_id=subject, predicate_id=predicate, object_value=object_val)
            return {"type": "status", "data": {"message": "Triple deleted"}}
        elif predicate:
            # Delete by subject + predicate
            triples = svc["triple"].get_by_sp(subject, predicate)
            count = 0
            for t in triples:
                svc["proof"].cascade_delete_proofs(t["subject_id"], t["predicate_id"], t["object_value"])
                svc["triple"].remove(
                    subject_id=t["subject_id"], predicate_id=t["predicate_id"],
                    object_value=t["object_value"], object_type=t.get("object_type", "uri"),
                )
                count += 1
            return {"type": "status", "data": {"message": f"Deleted {count} triple(s)"}}
        else:
            # Delete all triples for subject
            triples = svc["triple"].get_by_subject(subject)
            count = 0
            for t in triples:
                svc["proof"].cascade_delete_proofs(t["subject_id"], t["predicate_id"], t["object_value"])
                svc["triple"].remove(
                    subject_id=t["subject_id"], predicate_id=t["predicate_id"],
                    object_value=t["object_value"], object_type=t.get("object_type", "uri"),
                )
                count += 1
            return {"type": "status", "data": {"message": f"Deleted {count} triple(s)"}}

    if path == "triple.modify":
        subject = merged.get("subject") or (remaining and remaining[0]) or ""
        predicate = merged.get("predicate") or (remaining and remaining[1] if len(remaining) > 1 else "")
        object_val = merged.get("object") or (remaining and remaining[2] if len(remaining) > 2 else "")

        if not subject:
            raise CommandValidationError("Specify a subject")

        # Find the existing triple
        triple = None
        if predicate and object_val:
            triple = svc["triple"].get_one(subject, predicate, object_val) or None
            if not triple:
                try:
                    obj_node = svc["node"].resolve_node_id_prefix(object_val)
                    if obj_node:
                        triple = svc["triple"].get_one(subject, predicate, obj_node["node_id"])
                        if triple:
                            object_val = obj_node["node_id"]
                except Exception:
                    pass
        if not triple:
            raise CommandValidationError("Triple not found")

        # Extract new values from flags
        new_subject = flags.get("new_subject", None) or flags.get("new-subject", None) or triple["subject_id"]
        new_predicate = flags.get("new_predicate", None) or flags.get("new-predicate", None) or triple["predicate_id"]
        new_object_raw = flags.get("new_object", None) or flags.get("new-object", None) or triple["object_value"]

        str_flag = "str" in flags
        int_flag = "int" in flags
        float_flag = "float" in flags
        bool_flag = "bool" in flags
        lang = flags.get("lang", None)
        unit = flags.get("unit", None)
        katex = flags.get("katex", None)
        str_dosiero = flags.get("str_dosiero", None) or flags.get("str-dosiero", None)

        if katex is not None:
            new_object = katex.strip().strip("$")
            new_type = "literal"
            new_datatype = "text/katex"
        elif str_dosiero is not None:
            try:
                new_object = Path(str_dosiero).read_text(encoding="utf-8")
            except (FileNotFoundError, OSError) as e:
                raise CommandValidationError(f"Could not read file: {e}")
            new_type = "literal"
            new_datatype = "text/plain"
        elif str_flag:
            new_object = new_object_raw
            new_type = "literal"
            new_datatype = None
        elif int_flag:
            new_object = new_object_raw
            new_type = "literal"
            new_datatype = "xsd:integer"
        elif float_flag:
            new_object = new_object_raw
            new_type = "literal"
            new_datatype = "xsd:decimal"
        elif bool_flag:
            new_object = new_object_raw
            new_type = "literal"
            new_datatype = "xsd:boolean"
        else:
            new_object = new_object_raw
            new_type = triple.get("object_type", "uri")
            new_datatype = triple.get("object_datatype", None)

        new_lang = lang if str_flag else triple.get("object_lang", None)
        new_unit = unit or triple.get("object_unit", None)

        # No-op check
        noop = (
            triple["subject_id"] == new_subject
            and triple["predicate_id"] == new_predicate
            and triple["object_value"] == new_object
            and triple.get("object_type", "uri") == new_type
            and triple.get("object_unit") == new_unit
        )
        if noop:
            return {"type": "status", "data": {"message": "No change — triple remains unchanged"}}

        # Remove old + insert new
        old_type = triple.get("object_type", "uri")
        svc["proof"].cascade_delete_proofs(triple["subject_id"], triple["predicate_id"], triple["object_value"])
        svc["triple"].remove(
            subject_id=triple["subject_id"], predicate_id=triple["predicate_id"],
            object_value=triple["object_value"], object_type=old_type,
        )
        svc["triple"].add(
            subject_id=new_subject, predicate_id=new_predicate,
            object_value=new_object, object_type=new_type,
            object_lang=new_lang, object_datatype=new_datatype,
            object_unit=new_unit,
        )
        return {"type": "status", "data": {"message": f"Triple modified: {triple['subject_id']} → {triple['predicate_id']} → {triple['object_value']}"}}

    # ── Unit commands ─────────────────────────────────────────────────
    if path == "unit.list":
        from semantika.graph.unit_service import UnitService
        us = UnitService(svc["node"].db, svc["node"], svc["triple"])
        units = us.list_units()
        return {"type": "table", "data": units, "label": "Units"}

    if path == "unit.view":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        from semantika.graph.unit_service import UnitService
        us = UnitService(svc["node"].db, svc["node"], svc["triple"])
        info = us.get_unit_info(node_id)
        if not info:
            raise CommandValidationError(f"Unit not found: {node_id}")
        return {"type": "status", "data": info}

    if path == "unit.resolve":
        expr = merged.get("expr") or (remaining and remaining[0]) or ""
        from semantika.graph.unit_service import UnitService
        us = UnitService(svc["node"].db, svc["node"], svc["triple"])
        nid = us.resolve_unit(expr)
        info = us.get_unit_info(nid)
        return {"type": "status", "data": {"resolved": nid, "info": info}}

    if path == "unit.decompose":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        from semantika.graph.unit_service import UnitService
        us = UnitService(svc["node"].db, svc["node"], svc["triple"])
        info = us.get_unit_info(node_id)
        if not info:
            raise CommandValidationError(f"Unit not found: {node_id}")
        return {"type": "status", "data": {"decomposition": info.get("decomposition", "")}}

    # ── Trash commands ────────────────────────────────────────────────
    if path == "trash.list":
        items = svc["node"].list_trash()
        return {"type": "table", "data": items, "label": "Trash"}

    if path == "trash.restore":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        restored = svc["node"].restore_from_trash(node_id)
        if not restored:
            raise CommandValidationError(f"Node not found in trash: {node_id}")
        return {"type": "status", "data": {"message": f"Restored {restored.get('node_id', node_id)}"}}

    if path == "trash.delete":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        svc["node"].permanent_delete(node_id)
        return {"type": "status", "data": {"message": f"Permanently deleted {node_id}"}}

    if path == "trash.purge":
        raw_days = merged.get("days") or (remaining and remaining[0]) or "30"
        try:
            days = int(raw_days)
        except ValueError:
            raise CommandValidationError(f"Invalid days value: {raw_days}")
        if days <= 0:
            count = svc["node"].empty_all_trash()
        else:
            items = svc["node"].get_trash_older_than(days)
            count = len(items)
            for item in items:
                nid = item.get("node_id") or item.get(svc["node"]._pk_column)
                if nid:
                    svc["node"].permanent_delete(nid)
        return {"type": "status", "data": {"message": f"Purged {count} item(s) from trash"}}

    # ── Review commands ───────────────────────────────────────────────
    if path == "review.start":
        mode = merged.get("mode") or (remaining and remaining[0]) or "view"
        if mode not in ("view", "quiz"):
            raise CommandValidationError("Mode must be 'view' or 'quiz'")
        date_from = flags.get("date_from", None)
        date_to = flags.get("date_to", None)
        raw_limit = flags.get("limit", "10")
        try:
            limit = int(raw_limit)
        except ValueError:
            raise CommandValidationError(f"Invalid limit value: {raw_limit}")
        session = svc["review"].create_session(
            mode=mode, date_from=date_from, date_to=date_to, limit=limit,
        )
        return {"type": "status", "data": session}

    if path == "review.sessions":
        sessions = svc["review"].list_sessions()
        return {"type": "table", "data": sessions, "label": "Review Sessions"}

    if path == "review.view":
        session_uuid = merged.get("uuid") or (remaining and remaining[0]) or ""
        if not session_uuid:
            raise CommandValidationError("Specify a session UUID")
        session = svc["review"].get_session(session_uuid, enrich=True)
        if not session:
            raise CommandValidationError(f"Session not found: {session_uuid}")
        return {"type": "status", "data": session}

    if path == "review.delete":
        session_uuid = merged.get("uuid") or (remaining and remaining[0]) or ""
        if not session_uuid:
            raise CommandValidationError("Specify a session UUID")
        svc["review"].delete_session(session_uuid)
        return {"type": "status", "data": {"message": f"Deleted session {session_uuid}"}}

    # ── Proof commands ────────────────────────────────────────────────
    if path == "proof.add":
        subject_id = merged.get("subject_id") or (remaining and remaining[0]) or ""
        predicate_id = merged.get("predicate_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        object_value = merged.get("object_value") or (remaining and remaining[2] if len(remaining) > 2 else "") or ""
        if not subject_id or not predicate_id or not object_value:
            raise CommandValidationError("Specify subject_id, predicate_id, and object_value")
        # Resolve node IDs from prefixes
        subj_node = svc["node"].resolve_node_id_prefix(subject_id)
        if subj_node:
            subject_id = subj_node["node_id"]
        obj_node = svc["node"].resolve_node_id_prefix(object_value)
        if obj_node:
            object_value = obj_node["node_id"]
        proof_data = {
            "subject_id": subject_id,
            "predicate_id": predicate_id,
            "object_value": object_value,
            "proof_type": flags.get("proof_type", "observation"),
            "source": flags.get("source", ""),
            "notes": flags.get("notes", ""),
        }
        proof = svc["proof"].create(proof_data)
        return {"type": "status", "data": {"message": f"Created proof {proof['uuid']}", "proof": proof}}

    if path == "proof.view":
        subject_id = merged.get("subject_id") or (remaining and remaining[0]) or ""
        predicate_id = merged.get("predicate_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        object_value = merged.get("object_value") or (remaining and remaining[2] if len(remaining) > 2 else "") or ""
        if not subject_id or not predicate_id or not object_value:
            raise CommandValidationError("Specify subject_id, predicate_id, and object_value")
        subj_node = svc["node"].resolve_node_id_prefix(subject_id)
        if subj_node:
            subject_id = subj_node["node_id"]
        obj_node = svc["node"].resolve_node_id_prefix(object_value)
        if obj_node:
            object_value = obj_node["node_id"]
        proofs = svc["proof"].get_by_triple(subject_id, predicate_id, object_value)
        return {"type": "table", "data": proofs, "label": "Proofs"}

    if path == "proof.delete":
        proof_uuid = merged.get("uuid") or (remaining and remaining[0]) or ""
        if not proof_uuid:
            raise CommandValidationError("Specify a proof UUID")
        svc["proof"].delete(proof_uuid)
        return {"type": "status", "data": {"message": f"Deleted proof {proof_uuid}"}}

    # ── LLM command handlers ──────────────────────────────────────────
    if path == "llm":
        return {
            "type": "status",
            "title": "LLM Commands",
            "data": {
                "_summary": (
                    "Available !llm commands:\n"
                    "  !llm show                      — Show current config\n"
                    "  !llm new <protocol>            — Create config (openai, deepseek, ollama, custom)\n"
                    "  !llm set [flags]               — Modify current settings\n"
                    "  !llm clear                     — Clear config\n"
                    "  !llm profiles                  — List saved profiles\n"
                    "  !llm profile list               — List saved profiles\n"
                    "  !llm profile show               — Show current profile details\n"
                    "  !llm profile load <name>         — Load a saved profile\n"
                    "  !llm profile delete <name>       — Delete a saved profile"
                ),
            },
        }

    if path == "llm.show":
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        cfg = p.config
        return {
            "type": "status",
            "title": "LLM Configuration",
            "data": {
                "provider_type": cfg.provider_type,
                "has_api_key": bool(cfg.api_key),
                "base_url": cfg.base_url,
                "model": cfg.model,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "available": p.available,
            },
        }

    if path == "llm.new":
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        protocol = merged.get("provider_type") or (remaining and remaining[0]) or ""
        if not protocol:
            raise CommandValidationError(
                "Missing protocol.",
                "Usage: !llm new openai|deepseek|ollama|custom [--api-key KEY] [--base-url URL] [--model MODEL]",
            )
        p.configure(
            provider_type=protocol,
            api_key=flags.get("api_key", ""),
            base_url=flags.get("base_url", ""),
            model=flags.get("model", ""),
            temperature=float(flags.get("temperature", 0.7)),
            max_tokens=int(flags.get("max_tokens", 2048)),
        )
        result: dict[str, Any] = {
            "protocol": protocol,
            "available": p.available,
        }
        if "alias" in flags:
            name = flags["alias"]
            cfg = p.config
            p.save_profile(
                name=name,
                provider_type=cfg.provider_type,
                api_key=cfg.api_key or "",
                base_url=cfg.base_url or "",
                model=cfg.model or "",
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )
            result["saved_as"] = name
        return {"type": "status", "title": "LLM Configured", "data": result}

    if path == "llm.set":
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        if not flags:
            raise CommandValidationError(
                "No settings provided.",
                "Usage: !llm set --model gpt-4 --api-key sk-...",
            )
        cfg = p.config
        p.configure(
            provider_type=flags.get("provider_type", cfg.provider_type or "deepseek"),
            api_key=flags.get("api_key", cfg.api_key or ""),
            base_url=flags.get("base_url", cfg.base_url or ""),
            model=flags.get("model", cfg.model or ""),
            temperature=float(flags.get("temperature", cfg.temperature or 0.7)),
            max_tokens=int(flags.get("max_tokens", cfg.max_tokens or 2048)),
        )
        result = {"_summary": "done"}
        if "alias" in flags:
            name = flags["alias"]
            c = p.config
            p.save_profile(name=name, provider_type=c.provider_type, api_key=c.api_key or "",
                           base_url=c.base_url or "", model=c.model or "",
                           temperature=c.temperature, max_tokens=c.max_tokens)
            result["saved_as"] = name
        return {"type": "status", "title": "Profile Updated", "data": result}

    if path == "llm.clear":
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        p.clear_config()
        return {"type": "status", "title": "LLM Cleared", "data": {"_summary": "done"}}

    if path == "llm.profiles":
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        profiles = p.list_profiles()
        return {"type": "status", "title": "LLM Profiles", "data": {"profiles": profiles, "active_profile": p.active_profile_name}}

    if path == "llm.profile.list":
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        profiles = p.list_profiles()
        return {"type": "status", "title": "LLM Profiles", "data": {"profiles": profiles, "active_profile": p.active_profile_name}}

    if path == "llm.profile.show":
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        cfg = p.config
        return {
            "type": "status",
            "title": "Active Profile",
            "data": {
                "provider_type": cfg.provider_type,
                "has_api_key": bool(cfg.api_key),
                "base_url": cfg.base_url,
                "model": cfg.model,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "available": p.available,
                "active_profile_name": p.active_profile_name,
            },
        }

    if path == "llm.profile.load":
        name = merged.get("name") or (remaining and remaining[0]) or ""
        if not name:
            raise CommandValidationError("Missing profile name.", "Usage: !llm profile load <name>")
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        config = p.switch_to_profile(name)
        if config is None:
            raise CommandValidationError(f"Profile not found: {name}")
        return {"type": "status", "title": "Profile Loaded", "data": {
            "name": name, "protocol": config.provider_type, "model": config.model, "available": p.available,
        }}

    if path == "llm.profile.delete":
        name = merged.get("name") or (remaining and remaining[0]) or ""
        if not name:
            raise CommandValidationError("Missing profile name.", "Usage: !llm profile delete <name>")
        from semantika.server.llm.provider import LLMProvider as _Provider
        p = _Provider()
        if p.delete_profile(name):
            return {"type": "status", "title": "Profile Deleted", "data": {"removed": [name]}}
        raise CommandValidationError(f"Profile not found: {name}")

    # ── Backup command handlers ───────────────────────────────────────
    if path == "backup":
        return {
            "type": "status",
            "title": "Backup Commands",
            "data": {
                "_summary": (
                    "Available !backup commands:\n"
                    "  !backup now             — Create timestamped DB backup for all strategies\n"
                    "  !backup list            — List available backup snapshots\n"
                    "  !backup restore         — Restore from the latest backup\n"
                    "  !backup prune           — Delete old backups, keeping N newest\n"
                    "  !backup config          — View backup config summary\n"
                    "  !backup config list     — List backup strategies\n"
                    "  !backup config add      — Add a backup strategy\n"
                    "  !backup config modify   — Modify a backup strategy\n"
                    "  !backup config delete   — Delete a backup strategy\n"
                    "  !backup config test     — Test a strategy's target\n"
                    "  !backup export          — Export all data to a portable zip\n"
                    "  !backup import          — Import data from an export zip\n"
                ),
            },
        }

    if path == "backup.now":
        from semantika.core.backup import backup_all_strategies, load_config, resolve_target_path

        created = backup_all_strategies()
        if not created:
            return {"type": "status", "title": "Backup", "data": {"message": "No data files found to back up."}}

        cfg = load_config()
        loc_lines = ["  Local backup dir: " + _backup_dir_abs()]
        for s in cfg.get("strategies", []):
            loc_lines.append(f"  {s['id']}: {resolve_target_path(s)}")
        location = "\n".join(loc_lines)

        return {
            "type": "status",
            "title": "Backup Complete",
            "data": {
                "message": f"Created {len(created)} backup(s).\n\nBackup location:\n{location}",
                "backups": [str(p) for p in created],
            },
        }

    if path == "backup.list":
        from semantika.core.backup import list_backups as _list_backups

        stem = flags.get("stem")
        strategy_filter = flags.get("strategy")
        backups = _list_backups()
        if stem:
            backups = [b for b in backups if b["stem"] == stem]
        if strategy_filter:
            backups = [b for b in backups if b["strategy"] == strategy_filter]

        if not backups:
            return {"type": "status", "title": "Backups", "data": {"message": "No backups found."}}

        entries = []
        for b in backups:
            entries.append({
                "file": b["path"].name,
                "timestamp": _fmt_ts(b["timestamp"]),
                "size": _fmt_size(b["size_bytes"]),
                "database": b["stem"],
                "strategy": b.get("strategy", "legacy"),
            })

        return {
            "type": "status",
            "title": f"Backups ({len(entries)})",
            "data": {"entries": entries},
        }

    if path == "backup.restore":
        from semantika.core.backup import restore_latest, restore_by_timestamp
        from semantika.graph.db import get_db_path, close_db

        timestamp = flags.get("timestamp")

        # Close the DB connection before overwriting the file
        close_db()

        target = str(get_db_path().parent)
        try:
            if timestamp:
                restored = restore_by_timestamp(timestamp, target)
            else:
                restored = restore_latest(target)
        except (FileNotFoundError, LookupError, OSError) as e:
            raise CommandValidationError(str(e))

        # Reinitialize the DB
        from semantika.graph.db import init_db
        init_db()

        return {
            "type": "status",
            "title": "Restore Complete",
            "data": {
                "message": f"Restored to: {restored}",
                "file": str(restored),
            },
        }

    if path == "backup.prune":
        from semantika.core.backup import prune_backups

        raw = flags.get("keep", "")
        if raw:
            try:
                retention = int(raw)
            except ValueError:
                raise CommandValidationError(f"Invalid --keep value: {raw}")
        else:
            retention = None

        deleted = prune_backups(retention=retention)
        return {
            "type": "status",
            "title": "Backup Pruned",
            "data": {"message": f"Deleted {deleted} old backup(s)."},
        }

    if path == "backup.config":
        from semantika.core.backup import load_config, resolve_target_path

        cfg = load_config()
        strategies = cfg.get("strategies", [])
        enabled_count = sum(1 for s in strategies if s.get("enabled", True))

        summary = (
            f"Backup strategies: {len(strategies)} configured ({enabled_count} enabled)\n"
        )
        for s in strategies:
            status = "✓" if s.get("enabled", True) else "✗"
            interval = s.get("interval_minutes", 0)
            sched_str = f"{interval} min" if interval > 0 else "on-demand"
            summary += (
                f"  {status} {s['id']:12s}  {s.get('label', ''):20s}  "
                f"max {s.get('max_copies', 10):3d}  target={resolve_target_path(s)}  "
                f"every {sched_str}\n"
            )
        summary += "\nUse !backup config list for interactive management."

        return {
            "type": "status",
            "title": "Backup Config",
            "data": {"_summary": summary},
        }

    if path == "backup.config.list":
        from semantika.core.backup import list_strategies, resolve_target_path

        strategies = list_strategies()
        for s in strategies:
            s["_resolved_target"] = resolve_target_path(s)
        return {
            "type": "status",
            "title": f"Backup Strategies ({len(strategies)})",
            "data": {"strategies": strategies},
        }

    if path == "backup.config.add":
        from semantika.core.backup import BackupStrategy, add_strategy

        sid = flags.get("id", "")
        if not sid:
            raise CommandValidationError(
                "Missing --id", "Usage: !backup config add --id daily --label 'Daily backups'"
            )

        label = flags.get("label", "") or sid
        raw_interval = flags.get("interval", "0")
        try:
            interval_minutes = int(raw_interval)
        except ValueError:
            raise CommandValidationError(f"Invalid --interval value: {raw_interval}")
        raw_max = flags.get("max_copies", "10")
        try:
            max_copies = int(raw_max)
        except ValueError:
            raise CommandValidationError(f"Invalid --max-copies value: {raw_max}")
        if interval_minutes < 0:
            raise CommandValidationError("--interval must be >= 0")
        target = flags.get("target", "local")
        enabled_raw = flags.get("enabled", "true")
        enabled = enabled_raw.lower() in ("true", "1", "yes")

        try:
            strategy = BackupStrategy(
                id=sid,
                label=label,
                interval_minutes=interval_minutes,
                max_copies=max_copies,
                target=target,
                enabled=enabled,
            )
            add_strategy(strategy)
        except ValueError as e:
            raise CommandValidationError(str(e))

        return {
            "type": "status",
            "title": "Strategy Added",
            "data": {"strategy": sid, "message": f"Added backup strategy '{sid}'."},
        }

    if path == "backup.config.modify":
        from semantika.core.backup import get_strategy, update_strategy

        if not remaining:
            raise CommandValidationError(
                "Missing strategy id.", "Usage: !backup config modify daily --max-copies 5"
            )
        sid = remaining[0]
        strategy = get_strategy(sid)
        if strategy is None:
            raise CommandValidationError(f"Strategy '{sid}' not found.")

        updates: dict[str, Any] = {}
        if "label" in flags:
            updates["label"] = flags["label"]
        if "interval" in flags:
            raw = flags["interval"]
            try:
                updates["interval_minutes"] = int(raw)
            except ValueError:
                raise CommandValidationError(f"Invalid interval value: {raw}")
        if "max_copies" in flags:
            updates["max_copies"] = flags["max_copies"]
        if "target" in flags:
            updates["target"] = flags["target"]
        if "enabled" in flags:
            raw = flags["enabled"]
            updates["enabled"] = raw.lower() in ("true", "1", "yes") if raw else not strategy.get("enabled", True)

        if not updates:
            raise CommandValidationError(
                "No changes specified.",
                "Use --label, --interval, --max-copies, --target, or --enabled.",
            )

        try:
            update_strategy(sid, updates)
        except ValueError as e:
            raise CommandValidationError(str(e))

        return {
            "type": "status",
            "title": "Strategy Modified",
            "data": {
                "strategy": sid,
                "changed": list(updates.keys()),
                "message": f"Modified strategy '{sid}': {', '.join(updates.keys())}.",
            },
        }

    if path == "backup.config.delete":
        from semantika.core.backup import remove_strategy

        if not remaining:
            raise CommandValidationError(
                "Missing strategy id.", "Usage: !backup config delete daily"
            )
        sid = remaining[0]
        try:
            remove_strategy(sid)
        except ValueError as e:
            raise CommandValidationError(str(e))

        return {
            "type": "status",
            "title": "Strategy Deleted",
            "data": {"strategy": sid, "message": f"Deleted backup strategy '{sid}'."},
        }

    if path == "backup.config.test":
        from semantika.core.backup import verify_strategy_target

        if not remaining:
            raise CommandValidationError(
                "Missing strategy id.", "Usage: !backup config test daily"
            )
        sid = remaining[0]
        try:
            result = verify_strategy_target(sid)
        except ValueError as e:
            raise CommandValidationError(str(e))

        if result.get("success"):
            return {"type": "status", "title": "Test Passed", "data": {"message": result["message"]}}
        return {
            "type": "error",
            "title": "Test Failed",
            "data": {"message": result.get("message", ""), "error": result.get("error", "")},
        }

    if path == "backup.export":
        from semantika.core.backup import export_data

        output = flags.get("output", ".")
        try:
            export_path = export_data(output)
        except OSError as e:
            raise CommandValidationError(f"Export failed: {e}")

        return {
            "type": "status",
            "title": "Export Complete",
            "data": {
                "path": str(export_path),
                "message": f"Data exported to: {export_path}",
            },
        }

    if path == "backup.import":
        from semantika.core.backup import import_data
        from semantika.graph.db import close_db

        if not remaining:
            raise CommandValidationError(
                "Missing export path.", "Usage: !backup import <path> [--force]"
            )

        export_path = remaining[0]
        force = "force" in flags

        # Close DB before overwriting
        close_db()

        try:
            result = import_data(export_path, force=force)
        except (FileNotFoundError, ValueError, OSError) as e:
            raise CommandValidationError(f"Import failed: {e}")

        # Re-initialize DB after import
        if result.get("imported"):
            from semantika.graph.db import init_db
            init_db()

        imported = result.get("imported", [])
        skipped = result.get("skipped", [])
        errors = result.get("errors", [])

        msg_parts = [f"Imported {len(imported)} file(s)."]
        if skipped:
            msg_parts.append(f"{len(skipped)} skipped.")
        if errors:
            msg_parts.append(f"{len(errors)} error(s).")

        return {
            "type": "status",
            "title": "Import Complete",
            "data": {
                "imported": imported,
                "skipped": skipped,
                "errors": errors,
                "message": " ".join(msg_parts),
            },
        }

    # ── Reset command handler ─────────────────────────────────────────
    if path == "reset":
        has_path = bool(remaining)
        no_backup = "no-backup" in flags
        confirmed = flags.get("confirmed", "").lower() in ("true", "1", "yes")

        # Validate arguments — mutually exclusive
        if not has_path and not no_backup:
            raise CommandValidationError(
                "Provide either a backup path or --no-backup.",
                "Usage: !reset /path/to/backup.db   or   !reset --no-backup",
            )

        if has_path and no_backup:
            raise CommandValidationError(
                "Cannot specify both a backup path and --no-backup.",
                "Use either !reset <path> to backup first, or !reset --no-backup to skip backup.",
            )

        # --no-backup mode: require GUI confirmation
        if no_backup and not confirmed:
            return {
                "type": "form-required",
                "title": "Confirm Reset",
                "data": {
                    "form": "reset-no-backup",
                    "message": (
                        "This will permanently delete ALL your Semantika data — "
                        "nodes, predicates, triples, reviews, proofs, and unit ontology. "
                        "LLM configuration and saved profiles will also be cleared. "
                        "This action CANNOT be undone."
                    ),
                },
            }

        # Execute reset
        from semantika.core.reset import reset_to_fresh_state

        try:
            backup_path = remaining[0] if remaining else None
            result = reset_to_fresh_state(backup_path=backup_path)
        except (FileNotFoundError, OSError) as e:
            raise CommandValidationError(f"Reset failed: {e}")

        # Build response
        msg_parts = ["Semantika has been reset to a fresh state."]
        if result.get("backup_path"):
            msg_parts.append(f"Backup saved to: {result['backup_path']}")
        msg_parts.append(
            f"Databases removed: {len(result.get('databases_removed', []))}"
        )
        msg_parts.append(
            f"Credentials cleared: {result.get('credentials_cleared', 0)}"
        )

        return {
            "type": "status",
            "title": "Reset Complete",
            "data": {
                "message": " ".join(msg_parts),
                **result,
            },
        }

    raise CommandNotFound(tokens)


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_lang_tag_pairs(text: str | list[str]) -> dict[str, str]:
    """Parse ``LANG::TEXT`` or ``LANG:TEXT`` pairs into a dict.

    Accepts either a comma/space-separated string or a list of strings.
    """
    result: dict[str, str] = {}
    if isinstance(text, str):
        items = [t.strip() for t in text.replace(",", " ").split() if t.strip()]
    else:
        items = text
    for item in items:
        if "::" in item:
            lang, _, val = item.partition("::")
        elif ":" in item:
            lang, _, val = item.partition(":")
        else:
            continue
        lang = lang.strip()
        val = val.strip()
        if lang and val:
            result[lang] = val
    return result


def _safe_json_loads(raw: Any) -> dict:
    """Safely parse a JSON string to a dict, returning {} on failure."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _fmt_size(b: int) -> str:
    """Format a byte count for human display."""
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KiB"
    return f"{b / (1024 * 1024):.1f} MiB"


def _fmt_ts(ts: str) -> str:
    """Format a backup timestamp for human display."""
    if len(ts) >= 15:
        base = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
        if len(ts) > 15:
            base += f".{ts[15:21]}"
        return base
    return ts


def _backup_dir_abs() -> str:
    """Return the absolute path of the default backup directory."""
    from semantika.core.paths import data_dir
    return str((data_dir() / ".backups").resolve())


# ── Routes ───────────────────────────────────────────────────────────────

@router.post("", response_model=CommandResponse)
def execute_command(req: CommandRequest) -> dict[str, Any]:
    """Execute a parsed command and return structured output."""
    try:
        if "form" in req.flags:
            form_type = _resolve_form_type(req.tokens)
            if form_type:
                return {
                    "type": "form-required",
                    "title": f"Complete {form_type.replace('-', ' ').title()}",
                    "data": {"form": form_type, "initialData": req.flags},
                }

        result = _dispatch(req.tokens, req.flags)
        return {"type": result.get("type", "status"), "title": result.get("title", ""), "data": result.get("data", result)}
    except CommandNotFound as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CommandValidationError as e:
        form_type = _resolve_form_type(req.tokens)
        if form_type:
            return {"type": "form-required", "title": f"Complete {form_type.replace('-', ' ').title()}", "data": {"form": form_type, "initialData": req.flags, "message": str(e)}}
        raise HTTPException(status_code=400, detail={"error": str(e), "suggestion": getattr(e, "suggestion", "")})
    except CommandError as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "suggestion": getattr(e, "suggestion", "")})


@router.get("/tree")
def command_tree() -> list[dict]:
    """Return the full structured command tree for autocomplete."""
    return get_command_tree()


@router.get("/help")
def help_text() -> dict:
    """Return flat help text."""
    return {
        "commands": [
            {"cmd": "!node list/search/view/add/update/delete/merge/rename", "desc": "Manage nodes"},
            {"cmd": "!predicate list/search/view/add/update/delete/rename", "desc": "Manage predicates"},
            {"cmd": "!predicate-group list/view/add/rename/delete/search", "desc": "Manage predicate groups"},
            {"cmd": "!triple list/add/delete/modify/view", "desc": "Manage triples"},
            {"cmd": "!unit list/view/resolve/decompose/add", "desc": "Unit ontology"},
            {"cmd": "!search <q> [--date-from] [--date-to]", "desc": "Full-text search with optional date filter"},
            {"cmd": "!view <id>", "desc": "View all triples for a node"},
            {"cmd": "!export [--output FILE] [--base-uri URI]", "desc": "Export as Turtle"},
            {"cmd": "!import <data>", "desc": "Import Turtle data"},
            {"cmd": "!stats", "desc": "Graph statistics"},
            {"cmd": "!proof add/view/delete", "desc": "Manage proofs"},
            {"cmd": "!review start/sessions/view/delete", "desc": "Flashcard review"},
            {"cmd": "!trash list/restore/delete/purge", "desc": "Trash management"},
            {"cmd": "!llm show/new/set/clear", "desc": "LLM provider configuration"},
            {"cmd": "!llm profile list/show/load/delete", "desc": "LLM profile management"},
            {"cmd": "!backup now/list/restore/prune", "desc": "Database backup"},
            {"cmd": "!backup config list/add/modify/delete", "desc": "Backup strategies"},
            {"cmd": "!backup export/import", "desc": "Portable data export/import"},
            {"cmd": "!reset [path] [--no-backup]", "desc": "Reset to fresh state (with optional backup)"},
            {"cmd": "!ask <question>", "desc": "Ask the LLM about the graph"},
        ]
    }
