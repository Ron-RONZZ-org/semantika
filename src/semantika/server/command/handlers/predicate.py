"""Command handlers for predicate and predicate-group management."""

from __future__ import annotations

import json
import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.helpers import parse_lang_tag_pairs, safe_json_loads
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)


# ── Predicate commands ──────────────────────────────────────────────────


@command("predicate.list", description="List all predicates",
         permission_level=PermissionLevel.READ,
         params=[{"name": "limit", "type": "number", "default": 100}],
         flags=[
             {"name": "order_by", "type": "string", "help": "Sort column (predicate_id, created_at, updated_at)"},
             {"name": "direction", "type": "string", "help": "Sort direction (asc, desc)"},
             {"name": "offset", "type": "number", "help": "Row offset for pagination"},
         ],
         list_id_key="predicates")
def cmd_predicate_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all predicates.

    Supports sorting via ``--order_by`` (default ``predicate_id``) and
    ``--direction`` (default ``asc``). Supports pagination via ``--offset``.
    """
    svc = get_services()
    limit = int(flags.get("limit", 100))
    offset = int(flags.get("offset", 0))
    order_by = flags.get("order_by", "predicate_id") or "predicate_id"
    direction = flags.get("direction", "asc") or "asc"
    # Validate sort column to prevent SQL injection
    allowed_columns = {"predicate_id", "created_at", "updated_at"}
    if order_by not in allowed_columns:
        order_by = "predicate_id"
    direction = "ASC" if direction.lower() == "asc" else "DESC"
    preds = svc["predicate"].list(
        limit=limit, offset=offset,
        order_by=order_by, direction=direction,
    )
    total = svc["predicate"].count()
    return {"type": "predicate-list", "data": {"predicates": preds, "total": total}}


@command("predicate.search", description="Search predicates",
         permission_level=PermissionLevel.READ,
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
    return {"type": "predicate-list", "data": results}


@command("predicate.view", description="View predicate details",
         permission_level=PermissionLevel.READ,
         params=[{"name": "predicate_id", "type": "string", "required": True}])
def cmd_predicate_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a single predicate by ID, including triples that use it."""
    svc = get_services()
    pred_id = flags.get("predicate_id") or (remaining[0] if remaining else "") or ""
    if not pred_id:
        raise CommandValidationError("Specify a predicate_id")
    pred = svc["predicate"].get(pred_id)
    if not pred:
        raise CommandValidationError(f"Predicate not found: {pred_id}")
    triples = svc["triple"].get_by_predicate(pred["predicate_id"])
    pred["triples"] = triples
    return {"type": "status", "data": pred}


@command("predicate.add", description="Create a predicate", interactive=True,
         params=[{"name": "predicate_id", "type": "string", "required": True,
                  "placeholder": "ex:knows or knows"}],
         flags=[{"name": "labels", "type": "string",
                 "help": "Labels as LANG::TEXT pairs",
                 "placeholder": "en::knows, fr::connaître, eo::konas"},
                {"name": "descriptions", "type": "string",
                 "help": "Descriptions as LANG::TEXT pairs",
                 "placeholder": "en::A predicate that represents knowing someone"},
                {"name": "wikidata", "type": "flag",
                 "help": "Auto-fetch labels from Wikidata"}])
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


@command("predicate.update", description="Update a predicate", interactive=True,
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


@command("predicate.rename", description="Rename a predicate", interactive=True,
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
         flags=[{"name": "prefix", "type": "string", "help": "Delete all predicates with this ID prefix"},
                {"name": "force", "type": "flag", "help": "Bypass core-predicate protection"}])
def cmd_predicate_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    """Delete a predicate."""
    svc = get_services()
    force = "force" in flags or flags.get("force", "").lower() in ("true", "1", "yes")
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
            svc["predicate"].delete(pid, soft=True, force=force)
            deleted += 1
        except Exception as e:
            errors.append(f"{pid}: {e}")
    msg = f"Moved {deleted} predicate(s) to trash"
    if errors:
        msg += f" ({len(errors)} error(s))"
    return {"type": "status", "data": {"message": msg, "errors": errors}}
