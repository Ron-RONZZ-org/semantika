"""Command handlers for node management: list, search, view, add, update, delete, rename, merge."""

from __future__ import annotations

import json
import logging

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.helpers import parse_lang_tag_pairs
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)


@command("node.list", description="List all nodes",
         params=[{"name": "limit", "type": "number", "default": 100}])
def cmd_node_list(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    nodes = svc["node"].list(limit=int(flags.get("limit", 100)))
    return {"type": "table", "data": nodes, "label": "Nodes"}


@command("node.search", description="Search nodes by label",
         params=[{"name": "q", "type": "string", "required": True}])
def cmd_node_search(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    q = flags.get("q", "")
    if not q:
        raise CommandValidationError("Enter a search term")
    nodes = svc["node"].search(q)
    return {"type": "table", "data": nodes, "label": f"Nodes matching '{q}'"}


@command("node.view", description="View a node and its triples",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_node_view(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if remaining else "")
    if not node_id:
        raise CommandValidationError("Specify a node ID")
    node = svc["node"].resolve_node_id_prefix(node_id)
    if not node:
        raise CommandValidationError(f"Node not found: {node_id}")
    triples = svc["triple"].get_by_subject(node["node_id"])
    node["triples"] = triples
    return {"type": "status", "data": node}


@command("node.add", description="Create a new node", interactive=True,
         params=[{"name": "labels", "type": "string"}])
def cmd_node_add(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    payload = {"labels": {"en": labels_raw}} if labels_raw else {"labels": {}}
    try:
        node = svc["node"].create(payload)
        msg = f"Created node {node['node_id']}"
        if labels_raw:
            msg += f" with label \"{labels_raw}\""
        return {"type": "status", "data": {"message": msg, "node": node}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("node.update", description="Update node labels/definitions",
         params=[{"name": "id", "type": "string", "required": True}],
         flags=[{"name": "labels", "type": "string", "help": "New labels (JSON or LANG::TEXT)"},
                {"name": "definitions", "type": "string", "help": "New definitions"},
                {"name": "new-id", "type": "string", "help": "Rename to new ID"}])
def cmd_node_update(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    node_id = flags.get("id") or ""
    if not node_id:
        raise CommandValidationError("Specify a node ID")
    node = svc["node"].resolve_node_id_prefix(node_id)
    if not node:
        raise CommandValidationError(f"Node not found: {node_id}")
    payload: dict = {}
    labels_raw = flags.get("labels") or ""
    if labels_raw:
        try:
            labels_dict = json.loads(labels_raw) if labels_raw.startswith("{") else parse_lang_tag_pairs(labels_raw)
        except json.JSONDecodeError:
            labels_dict = {"en": labels_raw}
        payload["labels"] = labels_dict
    defs_raw = flags.get("definitions") or flags.get("defs") or ""
    if defs_raw:
        try:
            defs_dict = json.loads(defs_raw) if defs_raw.startswith("{") else parse_lang_tag_pairs(defs_raw)
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


@command("node.delete", description="Delete nodes (multiple IDs or --prefix)", interactive=True,
         params=[{"name": "id", "type": "string"}],
         flags=[{"name": "prefix", "type": "string", "help": "Delete all nodes with this ID prefix"},
                {"name": "force", "type": "string", "help": "Skip dependency warning and proceed"}])
def cmd_node_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    ids: list[str] = []
    pos_id = flags.get("id") or ""
    if pos_id:
        ids.append(pos_id)
    for k, v in flags.items():
        if k.startswith("_") and k[1:].isdigit() and v:
            ids.append(v)
    prefix = flags.get("prefix") or ""
    if prefix:
        prefix_nodes = svc["node"].db.execute(
            "SELECT * FROM nodes WHERE node_id LIKE ? ORDER BY node_id", (f"{prefix}%",))
        seen = set(ids)
        for n in prefix_nodes:
            if n["node_id"] not in seen:
                ids.append(n["node_id"])
    if not ids:
        raise CommandValidationError("Specify node ID(s) or use --prefix")
    force = flags.get("force")
    for nid in ids:
        warning = svc["node"].get_delete_warning(nid)
        if warning and not force:
            raise CommandValidationError(warning)
    deleted = 0
    errors = []
    for nid in ids:
        try:
            # _move_to_trash handles triple cleanup; no need to remove separately
            svc["node"].delete(nid, soft=True)
            deleted += 1
        except Exception as e:
            errors.append(f"{nid}: {e}")
    msg = f"Deleted {deleted} node(s)"
    if errors:
        msg += f" ({len(errors)} error(s))"
    return {"type": "status", "data": {"message": msg, "errors": errors}}


@command("node.rename", description="Rename a node",
         params=[{"name": "id", "type": "string", "required": True},
                 {"name": "new_id", "type": "string", "required": True}])
def cmd_node_rename(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if len(remaining) > 0 else "")
    new_id = flags.get("new_id") or (remaining[1] if len(remaining) > 1 else "") or ""
    if not node_id or not new_id:
        raise CommandValidationError("Specify current and new node ID")
    try:
        result = svc["node"].update_node_id(node_id, new_id)
        return {"type": "status", "data": {"message": f"Renamed {node_id} → {new_id}", "node": result}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("node.merge", description="Merge source node into target node",
         params=[{"name": "source", "type": "string", "required": True},
                 {"name": "target", "type": "string", "required": True}])
def cmd_node_merge(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    source = flags.get("source") or (remaining[0] if len(remaining) > 0 else "") or ""
    target = flags.get("target") or (remaining[1] if len(remaining) > 1 else "") or ""
    if not source or not target:
        raise CommandValidationError("Specify source and target node IDs")
    try:
        result = svc["node"].merge_nodes(source, target)
        return {"type": "status", "data": {"message": f"Merged {source} into {target}", "node": result}}
    except ValueError as e:
        raise CommandValidationError(str(e))
