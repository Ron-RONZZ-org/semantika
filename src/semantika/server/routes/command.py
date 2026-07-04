"""Command dispatch API route.

``POST /api/v1/command`` — Execute a parsed command token list.
``GET /api/v1/command/tree`` — Return the command tree for autocomplete.
``GET /api/v1/command/help`` — Flat help text.

Ported from lighterbird's command dispatch pattern.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from semantika.server.command.errors import CommandError, CommandNotFound, CommandValidationError
from semantika.server.command.models import CommandRequest, CommandResponse

router = APIRouter(tags=["command"])

# ── Interactive command form mapping ──────────────────────────────────────
_INTERACTIVE_FORMS: dict[str, str] = {
    "node.add": "node-add",
    "predicate.add": "predicate-add",
    "triple.add": "triple-add",
    "unit.add": "unit-add",
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
                {"name": "delete", "description": "Delete a node", "params": [{"name": "id", "type": "string", "required": True}]},
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
                {"name": "search", "description": "Search predicates", "params": [{"name": "q", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a predicate", "interactive": True, "params": [{"name": "predicate_id", "type": "string", "required": True}]},
                {"name": "update", "description": "Update a predicate", "params": [
                    {"name": "predicate_id", "type": "string", "required": True},
                    {"name": "labels", "type": "string"},
                ]},
                {"name": "delete", "description": "Delete a predicate", "params": [
                    {"name": "predicate_id", "type": "string", "required": True},
                ]},
                {"name": "rename", "description": "Rename a predicate", "params": [
                    {"name": "predicate_id", "type": "string", "required": True},
                    {"name": "new_id", "type": "string", "required": True},
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
                ]},
            ],
        },
        {
            "name": "unit",
            "description": "Manage unit ontology",
            "children": [
                {"name": "list", "description": "List all units"},
                {"name": "view", "description": "View unit details", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "resolve", "description": "Resolve a unit expression", "params": [{"name": "expr", "type": "string", "required": True}]},
                {"name": "add", "description": "Create a custom unit", "interactive": True},
            ],
        },
        {
            "name": "search",
            "description": "Full-text search across the graph",
            "params": [{"name": "q", "type": "string", "required": True}],
        },
        {
            "name": "trash",
            "description": "Manage soft-deleted nodes (trash)",
            "children": [
                {"name": "list", "description": "List trashed nodes"},
                {"name": "restore", "description": "Restore a trashed node", "params": [{"name": "id", "type": "string", "required": True}]},
                {"name": "purge", "description": "Permanently delete old trash entries", "params": [{"name": "days", "type": "number"}]},
            ],
        },
        {"name": "export", "description": "Export graph in Turtle format"},
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

    # Command flags override positional auto-fill
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

    if path == "stats":
        return {"type": "status", "data": svc["triple"].get_stats()}

    if path == "export":
        ttl = svc["triple"].export_turtle()
        return {"type": "status", "data": {"ttl": ttl[:500] + "..." if len(ttl) > 500 else ttl}}

    if path == "import":
        ttl_content = merged.get("data") or (remaining and remaining[0]) or ""
        if not ttl_content:
            raise CommandValidationError("Provide TTL content via data= flag")
        from semantika.graph.triple_turtle import import_turtle as _import
        stats = _import(ttl_content)
        return {"type": "status", "data": stats}

    if path == "search":
        q = merged.get("q") or ""
        if not q:
            raise CommandValidationError("Enter a search query")
        nodes = svc["node"].search(q)
        predicates = svc["predicate"].search(q)
        triples = svc["triple"].search_by_labels(subject=q, limit=50) or []
        # Also try as predicate/object
        pred_triples = svc["triple"].search_by_labels(predicate=q, limit=50) or []
        all_triples = list({t["subject_id"] + t["predicate_id"] + t["object_value"]: t for t in triples + pred_triples}.values())
        return {
            "type": "status",
            "data": {
                "nodes": nodes,
                "predicates": predicates,
                "triples": all_triples[:10],
                "_summary": f"Nodes: {len(nodes)}, Predicates: {len(predicates)}, Triples: {len(all_triples)}",
            },
        }

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

    if path == "node.delete":
        node_id = merged.get("id") or (remaining and remaining[0]) or ""
        if not node_id:
            raise CommandValidationError("Specify a node ID")
        svc["node"].delete(node_id, soft=True)
        return {"type": "status", "data": {"message": f"Deleted {node_id}"}}

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

    if path == "predicate.list":
        preds = svc["predicate"].list()
        return {"type": "table", "data": preds, "label": "Predicates"}

    if path == "predicate.search":
        q = merged.get("q", "")
        results = svc["predicate"].search(q)
        return {"type": "table", "data": results, "label": f"Predicates matching '{q}'"}

    if path == "predicate.update":
        pred_id = merged.get("predicate_id") or ""
        labels_raw = merged.get("labels") or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        payload = {}
        if labels_raw:
            try:
                labels_dict = json.loads(labels_raw) if labels_raw.startswith("{") else {"en": labels_raw}
            except json.JSONDecodeError:
                labels_dict = {"en": labels_raw}
            payload["labels"] = labels_dict
        try:
            pred = svc["predicate"].update(pred_id, payload)
            return {"type": "status", "data": {"message": f"Updated {pred_id}"}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "predicate.delete":
        pred_id = merged.get("predicate_id") or (remaining and remaining[0]) or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        svc["triple"].remove(predicate_id=pred_id)
        svc["predicate"].delete(pred_id, soft=True)
        return {"type": "status", "data": {"message": f"Deleted {pred_id}"}}

    if path == "predicate.add":
        pred_id = merged.get("predicate_id") or (remaining and remaining[0]) or ""
        if not pred_id:
            raise CommandValidationError("Specify a predicate_id")
        try:
            pred = svc["predicate"].create({"predicate_id": pred_id, "labels": {"en": pred_id}})
            return {"type": "status", "data": {"message": f"Created predicate {pred['predicate_id']}", "predicate": pred}}
        except ValueError as e:
            raise CommandValidationError(str(e))

    if path == "triple.list":
        triples = svc["triple"].db.execute("SELECT * FROM triples ORDER BY subject_id, predicate_id LIMIT ?", (100,))
        return {"type": "table", "data": triples, "label": "Triples"}

    if path == "triple.add":
        subject_id = merged.get("subject_id") or (remaining and remaining[0]) or ""
        predicate_id = merged.get("predicate_id") or (remaining and remaining[1] if len(remaining) > 1 else "") or ""
        object_value = merged.get("object_value") or (remaining and remaining[2] if len(remaining) > 2 else "") or ""
        if not subject_id or not predicate_id or not object_value:
            raise CommandValidationError("Specify subject_id, predicate_id, and object_value")
        try:
            triple = svc["triple"].add(subject_id, predicate_id, object_value, object_type="uri")
            return {"type": "status", "data": {"message": f"Added triple: {subject_id} → {predicate_id} → {object_value}", "triple": triple}}
        except ValueError as e:
            raise CommandValidationError(str(e))

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

    # ── LLM command handlers ──────────────────────────────────────────────
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

    # ── Backup command handlers ──────────────────────────────────────────
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

    # ── Reset command handler ──────────────────────────────────────────────
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


# ── Backup helpers ────────────────────────────────────────────────────────

# ── Backup helpers ────────────────────────────────────────────────────────


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
        # Append microseconds if available
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
            {"cmd": "!node list/search/view/add/delete", "desc": "Manage nodes"},
            {"cmd": "!predicate list/search/add", "desc": "Manage predicates"},
            {"cmd": "!triple list/add", "desc": "Manage triples"},
            {"cmd": "!unit list/view/resolve/add", "desc": "Unit ontology"},
            {"cmd": "!search <q>", "desc": "Full-text search"},
            {"cmd": "!export", "desc": "Export as Turtle"},
            {"cmd": "!stats", "desc": "Graph statistics"},
            {"cmd": "!review start/sessions", "desc": "Flashcard review"},
            {"cmd": "!llm show/new/set/clear", "desc": "LLM provider configuration"},
            {"cmd": "!llm profile list/show/load/delete", "desc": "LLM profile management"},
            {"cmd": "!backup now/list/restore/prune", "desc": "Database backup"},
            {"cmd": "!backup config list/add/modify/delete", "desc": "Backup strategies"},
            {"cmd": "!backup export/import", "desc": "Portable data export/import"},
            {"cmd": "!reset [path] [--no-backup]", "desc": "Reset to fresh state (with optional backup)"},
            {"cmd": "!ask <question>", "desc": "Ask the LLM about the graph"},
        ]
    }
