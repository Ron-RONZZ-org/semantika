"""Command handlers for trash management."""

from __future__ import annotations

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command


@command("trash.list", description="List trashed nodes")
def cmd_trash_list(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    items = svc["node"].list_trash()
    return {"type": "table", "data": items, "label": "Trash"}


@command("trash.restore", description="Restore a trashed node",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_trash_restore(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if remaining else "") or ""
    if not node_id:
        raise CommandValidationError("Specify a node ID")
    restored = svc["node"].restore_from_trash(node_id)
    if not restored:
        raise CommandValidationError(f"Node not found in trash: {node_id}")
    return {"type": "status", "data": {"message": f"Restored {restored.get('node_id', node_id)}"}}


@command("trash.delete", description="Permanently delete a trashed node",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_trash_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if remaining else "") or ""
    if not node_id:
        raise CommandValidationError("Specify a node ID")
    svc["node"].delete(node_id, soft=False)
    return {"type": "status", "data": {"message": f"Permanently deleted {node_id}"}}


@command("trash.purge", description="Purge old trashed nodes",
         params=[{"name": "days", "type": "number", "default": 30}])
def cmd_trash_purge(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    raw_days = flags.get("days") or (remaining[0] if remaining else "") or "30"
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
            nid = item.get("node_id")
            if nid:
                svc["node"].delete(nid, soft=False)
    return {"type": "status", "data": {"message": f"Purged {count} item(s) from trash"}}
