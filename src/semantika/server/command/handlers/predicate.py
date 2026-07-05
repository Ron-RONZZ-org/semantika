"""Command handlers for predicate and predicate-group management."""

from __future__ import annotations

import json
import logging

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.helpers import parse_lang_tag_pairs, resolve_group, safe_json_loads
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)


# ── Predicate commands ──────────────────────────────────────────────────


@command("predicate.list", description="List all predicates")
def cmd_predicate_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all predicates."""
    svc = get_services()
    preds = svc["predicate"].list()
    return {"type": "table", "data": preds, "label": "Predicates"}


@command("predicate.search", description="Search predicates",
         params=[{"name": "q", "type": "string", "required": True}],
         flags=[{"name": "wikidata", "type": "flag", "help": "Also search Wikidata"}])
def cmd_predicate_search(remaining: list[str], flags: dict[str, str]) -> dict:
    """Search predicates by label."""
    svc = get_services()
    q = flags.get("q", "")
    results = svc["predicate"].search(q)
    wikidata_flag = "wikidata" in flags or flags.get("wikidata", "").lower() in ("true", "1", "yes")
    if wikidata_flag:
        try:
            from semantika.graph.node_helpers import search_wikidata as _search_wikidata
            wd_results = _search_wikidata(q)
            local_ids = {r["predicate_id"] for r in results}
            for wd in wd_results:
                if wd["predicate_id"] not in local_ids:
                    results.append(wd)
        except Exception as exc:
            logger.warning("Wikidata predicate search failed: %s", exc)
    return {"type": "table", "data": results, "label": f"Predicates matching '{q}'"}


@command("predicate.view", description="View predicate details",
         params=[{"name": "predicate_id", "type": "string", "required": True}])
def cmd_predicate_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a single predicate by ID."""
    svc = get_services()
    pred_id = flags.get("predicate_id") or (remaining[0] if remaining else "") or ""
    if not pred_id:
        raise CommandValidationError("Specify a predicate_id")
    pred = svc["predicate"].get(pred_id)
    if not pred:
        raise CommandValidationError(f"Predicate not found: {pred_id}")
    return {"type": "status", "data": pred}


@command("predicate.add", description="Create a predicate", interactive=True,
         params=[{"name": "predicate_id", "type": "string", "required": True}],
         flags=[{"name": "labels", "type": "string", "help": "Labels as LANG::TEXT"},
                {"name": "descriptions", "type": "string", "help": "Descriptions"},
                {"name": "wikidata", "type": "flag", "help": "Auto-fetch labels from Wikidata"}])
def cmd_predicate_add(remaining: list[str], flags: dict[str, str]) -> dict:
    """Add a new predicate."""
    svc = get_services()
    pred_id = flags.get("predicate_id") or (remaining[0] if remaining else "") or ""
    if not pred_id:
        raise CommandValidationError("Specify a predicate_id")
    labels_raw = flags.get("labels") or ""
    descs_raw = flags.get("descriptions") or ""
    wikidata_flag = "wikidata" in flags or flags.get("wikidata", "").lower() in ("true", "1", "yes")
    data: dict = {"predicate_id": pred_id}
    if labels_raw:
        try:
            data["labels"] = json.loads(labels_raw) if labels_raw.startswith("{") else parse_lang_tag_pairs(labels_raw)
        except json.JSONDecodeError:
            data["labels"] = {"en": labels_raw}
    if descs_raw:
        try:
            data["descriptions"] = json.loads(descs_raw) if descs_raw.startswith("{") else parse_lang_tag_pairs(descs_raw)
        except json.JSONDecodeError:
            data["descriptions"] = {"en": descs_raw}
    if wikidata_flag:
        data["source"] = "wikidata"
        try:
            from semantika.graph.node_helpers import fetch_wikidata_details as _fetch_wd
            wd = _fetch_wd(pred_id)
            if wd:
                data.setdefault("labels", {}).update(wd.get("labels", {}))
                data.setdefault("descriptions", {}).update(wd.get("descriptions", {}))
        except Exception as exc:
            logger.warning("Wikidata detail fetch failed for %s: %s", pred_id, exc)
    try:
        pred = svc["predicate"].create(data)
        return {"type": "status", "data": {"message": f"Created predicate {pred['predicate_id']}", "predicate": pred}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate.update", description="Update a predicate",
         params=[{"name": "predicate_id", "type": "string", "required": True}],
         flags=[{"name": "labels", "type": "string", "help": "Labels as LANG::TEXT"},
                {"name": "descriptions", "type": "string", "help": "Descriptions"},
                {"name": "replace", "type": "flag", "help": "Replace instead of merging"},
                {"name": "new-id", "type": "string", "help": "Rename to new ID"}])
def cmd_predicate_update(remaining: list[str], flags: dict[str, str]) -> dict:
    """Update a predicate's labels or description."""
    svc = get_services()
    pred_id = flags.get("predicate_id") or ""
    if not pred_id:
        raise CommandValidationError("Specify a predicate_id")
    existing = svc["predicate"].get(pred_id)
    if not existing:
        raise CommandValidationError(f"Predicate not found: {pred_id}")
    payload = {}
    labels_raw = flags.get("labels") or ""
    descs_raw = flags.get("descriptions") or ""
    replace = "replace" in flags or flags.get("replace", "").lower() in ("true", "1", "yes")
    if labels_raw:
        parsed = parse_lang_tag_pairs(labels_raw)
        if replace:
            payload["labels"] = parsed
        else:
            merged_labels = safe_json_loads(existing.get("labels", "{}"))
            merged_labels.update(parsed)
            payload["labels"] = merged_labels
    if descs_raw:
        parsed = parse_lang_tag_pairs(descs_raw)
        if replace:
            payload["descriptions"] = parsed
        else:
            merged_descs = safe_json_loads(existing.get("descriptions", "{}"))
            merged_descs.update(parsed)
            payload["descriptions"] = merged_descs
    new_id = flags.get("new_id") or flags.get("new-id") or ""
    try:
        if new_id:
            svc["predicate"].update_predicate_id(pred_id, new_id, data=payload if payload else None)
            return {"type": "status", "data": {"message": f"Renamed {pred_id} → {new_id}"}}
        elif payload:
            svc["predicate"].update(pred_id, payload)
            return {"type": "status", "data": {"message": f"Updated {pred_id}"}}
        else:
            raise CommandValidationError("No changes specified (use --labels, --descriptions, or --new-id)")
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate.rename", description="Rename a predicate",
         params=[{"name": "predicate_id", "type": "string", "required": True},
                 {"name": "new_id", "type": "string", "required": True}])
def cmd_predicate_rename(remaining: list[str], flags: dict[str, str]) -> dict:
    """Rename a predicate."""
    svc = get_services()
    pred_id = flags.get("predicate_id") or (remaining[0] if remaining else "") or ""
    new_id = flags.get("new_id") or (remaining[1] if len(remaining) > 1 else "") or ""
    if not pred_id or not new_id:
        raise CommandValidationError("Specify current and new predicate ID")
    try:
        result = svc["predicate"].update_predicate_id(pred_id, new_id)
        return {"type": "status", "data": {"message": f"Renamed {pred_id} → {new_id}", "predicate": result}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate.delete", description="Delete predicates", interactive=True,
         params=[{"name": "predicate_id", "type": "string"}],
         flags=[{"name": "prefix", "type": "string", "help": "Delete all predicates with this ID prefix"}])
def cmd_predicate_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    """Delete a predicate."""
    svc = get_services()
    ids: list[str] = []
    pos_id = flags.get("predicate_id") or ""
    if pos_id:
        ids.append(pos_id)
    for k, v in flags.items():
        if k.startswith("_") and v:
            ids.append(v)
    prefix = flags.get("prefix") or ""
    if prefix:
        prefix_preds = svc["predicate"].db.execute(
            "SELECT * FROM predicates WHERE predicate_id LIKE ? ORDER BY predicate_id", (f"{prefix}%",))
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
            svc["predicate"].delete(pid)
            deleted += 1
        except Exception as e:
            errors.append(f"{pid}: {e}")
    msg = f"Deleted {deleted} predicate(s)"
    if errors:
        msg += f" ({len(errors)} error(s))"
    return {"type": "status", "data": {"message": msg, "errors": errors}}


# ── Predicate Group commands ──────────────────────────────────────────────


@command("predicate-group.list", description="List all predicate groups")
def cmd_predicate_group_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all predicate groups."""
    svc = get_services()
    groups = svc["predicate_group"].list()
    return {"type": "table", "data": groups, "label": "Predicate Groups"}


@command("predicate-group.view", description="View a predicate group and its members",
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


@command("predicate-group.add", description="Create a predicate group", interactive=True,
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


@command("predicate-group.rename", description="Rename a predicate group",
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
        return {"type": "status", "data": {"message": f"Renamed '{name}' → '{new_name}'"}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate-group.delete", description="Delete a predicate group",
         params=[{"name": "name", "type": "string", "required": True}])
def cmd_predicate_group_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    """Delete a predicate group."""
    svc = get_services()
    name = flags.get("name") or (remaining[0] if remaining else "") or ""
    if not name:
        raise CommandValidationError("Specify a group name")
    group = resolve_group(svc, name)
    try:
        svc["predicate_group"].db.execute("DELETE FROM predicate_group_members WHERE group_uuid = ?", (group["uuid"],))
        svc["predicate_group"].delete(group["uuid"])
        return {"type": "status", "data": {"message": f"Deleted group '{name}'"}}
    except ValueError as e:
        raise CommandValidationError(str(e))


@command("predicate-group.search", description="Search predicate groups",
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


@command("predicate-group.add-member", description="Add a predicate to a group",
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


@command("predicate-group.remove-member", description="Remove a predicate from a group",
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
