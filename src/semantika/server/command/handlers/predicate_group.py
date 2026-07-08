"""Command handlers for predicate group management.

Extracted from predicate.py to follow "one concern, one root command" principle.
"""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.helpers import resolve_group
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)


# ── Predicate Group commands ──────────────────────────────────────────────


@command("predicate.group.list", description="List all predicate groups",
         permission_level=PermissionLevel.READ)
def cmd_predicate_group_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all predicate groups."""
    svc = get_services()
    groups = svc["predicate_group"].list()
    return {"type": "table", "data": groups, "label": "Predicate Groups"}


@command("predicate.group.view", description="View a predicate group and its members",
         permission_level=PermissionLevel.READ,
         params=[{"name": "name", "type": "string", "required": True}])
def cmd_predicate_group_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a predicate group and its members."""
    svc = get_services()
    name = flags.get("name") or (remaining[0] if remaining else "") or ""
    if not name:
        raise CommandValidationError("Specify a group name")
    group = resolve_group(svc, name)
    members = svc["predicate_group"].list_members(group["uuid"])
    group["members"] = members
    return {"type": "status", "data": group}


@command("predicate.group.add", description="Create a predicate group", interactive=True,
         params=[{"name": "name", "type": "string", "required": True}])
def cmd_predicate_group_add(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a new predicate group."""
    svc = get_services()
    name = flags.get("name") or (remaining[0] if remaining else "") or ""
    if not name:
        raise CommandValidationError("Specify a group name")
    try:
        svc["predicate_group"].create({"group_name": name})
        return {"type": "status", "data": {"message": f"Created group '{name}'"}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate.group.rename", description="Rename a predicate group",
         params=[{"name": "name", "type": "string", "required": True},
                 {"name": "new_name", "type": "string", "required": True}])
def cmd_predicate_group_rename(remaining: list[str], flags: dict[str, str]) -> dict:
    """Rename a predicate group."""
    svc = get_services()
    name = flags.get("name") or (remaining[0] if remaining else "") or ""
    new_name = flags.get("new_name") or (remaining[1] if len(remaining) > 1 else "") or ""
    if not name or not new_name:
        raise CommandValidationError("Specify current and new group name")
    group = resolve_group(svc, name)
    try:
        svc["predicate_group"].update(group["uuid"], {"group_name": new_name})
        return {"type": "status", "data": {"message": f"Renamed '{name}' \u2192 '{new_name}'"}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate.group.delete", description="Delete a predicate group",
         params=[{"name": "name", "type": "string", "required": True}])
def cmd_predicate_group_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    """Delete a predicate group."""
    svc = get_services()
    name = flags.get("name") or (remaining[0] if remaining else "") or ""
    if not name:
        raise CommandValidationError("Specify a group name")
    group = resolve_group(svc, name)
    try:
        svc["predicate_group"].db.execute(
            "DELETE FROM predicate_group_members WHERE group_uuid = ?", (group["uuid"],))
        svc["predicate_group"].delete(group["uuid"])
        return {"type": "status", "data": {"message": f"Deleted group '{name}'"}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate.group.search", description="Search predicate groups",
         permission_level=PermissionLevel.READ,
         params=[{"name": "q", "type": "string", "required": True}])
def cmd_predicate_group_search(remaining: list[str], flags: dict[str, str]) -> dict:
    """Search predicate groups by name."""
    svc = get_services()
    q = flags.get("q") or (remaining[0] if remaining else "") or ""
    if not q:
        raise CommandValidationError("Enter a search term")
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    results = svc["predicate_group"].db.execute(
        "SELECT * FROM predicate_groups WHERE group_name LIKE ? ESCAPE '\\'", (f"%{escaped}%",))
    return {"type": "table", "data": results, "label": f"Groups matching '{q}'"}


@command("predicate.group.add-member", description="Add a predicate to a group",
         params=[{"name": "group", "type": "string", "required": True},
                 {"name": "predicate_id", "type": "string", "required": True}])
def cmd_predicate_group_add_member(remaining: list[str], flags: dict[str, str]) -> dict:
    """Add a predicate to a group."""
    svc = get_services()
    group_name = flags.get("group") or (remaining[0] if remaining else "") or ""
    pred_id = flags.get("predicate_id") or (remaining[1] if len(remaining) > 1 else "") or ""
    if not group_name or not pred_id:
        raise CommandValidationError("Specify group name and predicate_id")
    group = resolve_group(svc, group_name)
    try:
        svc["predicate_group"].add_member(group["uuid"], pred_id)
        return {"type": "status", "data": {"message": f"Added {pred_id} to '{group_name}'"}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate.group.remove-member", description="Remove a predicate from a group",
         params=[{"name": "group", "type": "string", "required": True},
                 {"name": "predicate_id", "type": "string", "required": True}])
def cmd_predicate_group_remove_member(remaining: list[str], flags: dict[str, str]) -> dict:
    """Remove a predicate from a group."""
    svc = get_services()
    group_name = flags.get("group") or (remaining[0] if remaining else "") or ""
    pred_id = flags.get("predicate_id") or (remaining[1] if len(remaining) > 1 else "") or ""
    if not group_name or not pred_id:
        raise CommandValidationError("Specify group name and predicate_id")
    group = resolve_group(svc, group_name)
    try:
        svc["predicate_group"].remove_member(group["uuid"], pred_id)
        return {"type": "status", "data": {"message": f"Removed {pred_id} from '{group_name}'"}}
    except ValueError as e:
        raise CommandValidationError(str(e))
