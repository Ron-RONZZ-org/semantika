"""Command handlers for predicate trash management."""

from __future__ import annotations

from lightercore.permissions import PermissionLevel
from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command


@command("predicate.trash.list", description="List trashed predicates")
def cmd_predicate_trash_list(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    items = svc["predicate"].list_trash()
    return {"type": "table", "data": items, "label": "Predicate Trash"}


@command("predicate.trash.restore", description="Restore a trashed predicate",
         params=[{"name": "predicate_id", "type": "string", "required": True}])
def cmd_predicate_trash_restore(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    pred_id = flags.get("predicate_id") or (remaining[0] if remaining else "") or ""
    if not pred_id:
        raise CommandValidationError("Specify a predicate ID")
    restored = svc["predicate"].restore_from_trash(pred_id)
    if not restored:
        raise CommandValidationError(f"Predicate not found in trash: {pred_id}")
    return {"type": "status", "data": {"message": f"Restored predicate {restored.get('predicate_id', pred_id)}"}}


@command("predicate.trash.delete", description="Permanently delete a trashed predicate",
         params=[{"name": "predicate_id", "type": "string", "required": True}])
def cmd_predicate_trash_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    pred_id = flags.get("predicate_id") or (remaining[0] if remaining else "") or ""
    if not pred_id:
        raise CommandValidationError("Specify a predicate ID")
    svc["predicate"].delete(pred_id, soft=False)
    return {"type": "status", "data": {"message": f"Permanently deleted predicate {pred_id}"}}


@command("predicate.trash.purge", description="Empty the predicate trash permanently",
         permission_level=PermissionLevel.DESTRUCTIVE)
def cmd_predicate_trash_purge(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    count = svc["predicate"].empty_trash()
    return {"type": "status", "data": {"message": f"Purged {count} predicate(s) from trash"}}
