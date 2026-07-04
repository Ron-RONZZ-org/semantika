"""Command handlers for node, predicate, predicate-group, triple, search, view, stats, export, import, trash."""

from __future__ import annotations

import json
from pathlib import Path

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.helpers import parse_lang_tag_pairs, resolve_group, safe_json_loads
from semantika.server.command.registry import command


# ── Stats ─────────────────────────────────────────────────────────────────


@command("stats", description="Graph statistics")
def cmd_stats(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    return {"type": "status", "data": svc["triple"].get_stats()}


# ── Export ────────────────────────────────────────────────────────────────


@command("export", description="Export as Turtle",
         flags=[{"name": "output", "type": "string", "help": "Output file path"},
                {"name": "base_uri", "type": "string", "help": "Base URI"}])
def cmd_export(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
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


# ── Import ────────────────────────────────────────────────────────────────


@command("import", description="Import Turtle data",
         params=[{"name": "data", "type": "string", "required": True}])
def cmd_import(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    ttl_content = flags.get("data") or (remaining[0] if remaining else "")
    if not ttl_content:
        raise CommandValidationError("Provide TTL content via data= flag")
    from semantika.graph.triple_turtle import import_turtle as _import
    stats = _import(ttl_content)
    return {"type": "status", "data": stats}


# ── Search ────────────────────────────────────────────────────────────────


@command("search", description="Full-text search",
         params=[{"name": "q", "type": "string", "required": True}],
         flags=[{"name": "date_from", "type": "string", "help": "Start date"},
                {"name": "date_to", "type": "string", "help": "End date"},
                {"name": "limit", "type": "number", "help": "Max results"}])
def cmd_search(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    q = flags.get("q") or (remaining[0] if remaining else "")
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
    triples = svc["triple"].search_by_labels(subject=q, limit=limit, created_after=date_from, created_before=date_to) or []
    pred_triples = svc["triple"].search_by_labels(predicate=q, limit=limit, created_after=date_from, created_before=date_to) or []
    all_triples = list({t["subject_id"] + t["predicate_id"] + t["object_value"]: t for t in triples + pred_triples}.values())
    return {"type": "status", "data": {"nodes": nodes, "predicates": predicates, "triples": all_triples[:limit],
                                        "_summary": f"Nodes: {len(nodes)}, Predicates: {len(predicates)}, Triples: {len(all_triples)}"}}


# ── View ──────────────────────────────────────────────────────────────────


@command("view", description="View all triples for a node",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_view(remaining: list[str], flags: dict[str, str]) -> dict:
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


# ── Node commands ─────────────────────────────────────────────────────────


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
         flags=[{"name": "prefix", "type": "string", "help": "Delete all nodes with this ID prefix"}])
def cmd_node_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    ids: list[str] = []
    pos_id = flags.get("id") or ""
    if pos_id:
        ids.append(pos_id)
    for k, v in flags.items():
        if k.startswith("_") and v:
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


# ── Predicate commands ────────────────────────────────────────────────────


@command("predicate.list", description="List all predicates")
def cmd_predicate_list(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    preds = svc["predicate"].list()
    return {"type": "table", "data": preds, "label": "Predicates"}


@command("predicate.search", description="Search predicates",
         params=[{"name": "q", "type": "string", "required": True}],
         flags=[{"name": "wikidata", "type": "flag", "help": "Also search Wikidata"}])
def cmd_predicate_search(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    q = flags.get("q", "")
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
            pass
    return {"type": "table", "data": results, "label": f"Predicates matching '{q}'"}


@command("predicate.view", description="View predicate details",
         params=[{"name": "predicate_id", "type": "string", "required": True}])
def cmd_predicate_view(remaining: list[str], flags: dict[str, str]) -> dict:
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
            from semantika.graph.node_helpers import fetch_wikidata_details
            wd = fetch_wikidata_details(pred_id)
            if wd:
                data.setdefault("labels", {}).update(wd.get("labels", {}))
                data.setdefault("descriptions", {}).update(wd.get("descriptions", {}))
        except Exception:
            pass
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
            svc["predicate"].delete(pid, soft=True)
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
    svc = get_services()
    groups = svc["predicate_group"].list()
    return {"type": "table", "data": groups, "label": "Predicate Groups"}


@command("predicate-group.view", description="View a predicate group and its members",
         params=[{"name": "name", "type": "string", "required": True}])
def cmd_predicate_group_view(remaining: list[str], flags: dict[str, str]) -> dict:
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


# ── Triple commands ───────────────────────────────────────────────────────


@command("triple.list", description="List all triples")
def cmd_triple_list(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    triples = svc["triple"].db.execute("SELECT * FROM triples ORDER BY subject_id, predicate_id LIMIT ?", (100,))
    return {"type": "table", "data": triples, "label": "Triples"}


@command("triple.view", description="View triples for a node",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_triple_view(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if remaining else "") or ""
    if not node_id:
        raise CommandValidationError("Specify a node ID")
    triples = svc["triple"].get_by_subject(node_id)
    if not triples:
        return {"type": "status", "data": {"message": f"No triples found for {node_id}", "triples": []}}
    return {"type": "table", "data": triples, "label": f"Triples for {node_id}"}


@command("triple.add", description="Add a triple", interactive=True,
         params=[{"name": "subject_id", "type": "string", "required": True},
                 {"name": "predicate_id", "type": "string", "required": True},
                 {"name": "object_value", "type": "string", "required": True}],
         flags=[{"name": "str", "type": "flag", "help": "Treat object as string literal"},
                {"name": "int", "type": "flag", "help": "Treat object as integer literal"},
                {"name": "float", "type": "flag", "help": "Treat object as float literal"},
                {"name": "bool", "type": "flag", "help": "Treat object as boolean literal"},
                {"name": "lang", "type": "string", "help": "Language tag"},
                {"name": "unit", "type": "string", "help": "Unit for numeric literals"},
                {"name": "katex", "type": "string", "help": "KaTeX math expression"},
                {"name": "str-dosiero", "type": "string", "help": "Read content from file"}])
def cmd_triple_add(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    subject_id = flags.get("subject_id") or (remaining[0] if remaining else "") or ""
    predicate_id = flags.get("predicate_id") or (remaining[1] if len(remaining) > 1 else "") or ""
    object_value = flags.get("object_value") or (remaining[2] if len(remaining) > 2 else "") or ""
    if not subject_id or not predicate_id or not object_value:
        raise CommandValidationError("Specify subject_id, predicate_id, and object_value")
    str_flag = "str" in flags or flags.get("str", "").lower() in ("true", "1", "yes")
    int_flag = "int" in flags or flags.get("int", "").lower() in ("true", "1", "yes")
    float_flag = "float" in flags or flags.get("float", "").lower() in ("true", "1", "yes")
    bool_flag = "bool" in flags or flags.get("bool", "").lower() in ("true", "1", "yes")
    lang = flags.get("lang", None)
    unit = flags.get("unit", None)
    katex = flags.get("katex", None)
    str_dosiero = flags.get("str_dosiero", None) or flags.get("str-dosiero", None)
    kodlingvo = flags.get("kodlingvo", None)
    object_type = "uri"
    object_datatype = None
    object_lang = None
    str_dosiero_used = False
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
        str_dosiero_used = True
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
    effective_str = str_flag or str_dosiero_used
    object_lang = lang if effective_str else None
    if object_type == "uri":
        try:
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
            subject_id=subject_id, predicate_id=predicate_id, object_value=object_value,
            object_type=object_type, object_lang=object_lang, object_datatype=object_datatype, object_unit=unit)
        return {"type": "status", "data": {"message": f"Added triple: {subject_id} → {predicate_id} → {object_value}", "triple": triple}}
    except ValueError as e:
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
                svc["triple"].update_metadata(subject_id, predicate_id, object_value, object_type, **changes)
                return {"type": "status", "data": {"message": "Triple already existed — metadata updated", "changes": changes}}
            return {"type": "status", "data": {"message": "Triple already exists with identical metadata"}}
        raise CommandValidationError(str(e))


@command("triple.delete", description="Delete a triple", interactive=True,
         params=[{"name": "subject", "type": "string", "required": True},
                 {"name": "predicate", "type": "string"},
                 {"name": "object", "type": "string"}])
def cmd_triple_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    subject = flags.get("subject") or (remaining[0] if remaining else "") or ""
    predicate = flags.get("predicate") or (remaining[1] if len(remaining) > 1 else "") or ""
    object_val = flags.get("object") or (remaining[2] if len(remaining) > 2 else "") or ""
    if not subject:
        raise CommandValidationError("Specify a subject")
    if predicate and object_val:
        triple = svc["triple"].get_one(subject, predicate, object_val, object_type="literal")
        if not triple:
            triple = svc["triple"].get_one(subject, predicate, object_val, object_type="uri")
        if not triple:
            try:
                obj_node = svc["node"].resolve_node_id_prefix(object_val)
                if obj_node:
                    triple = svc["triple"].get_one(subject, predicate, obj_node["node_id"], object_type="uri")
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
        triples = svc["triple"].get_by_sp(subject, predicate)
        count = 0
        for t in triples:
            svc["proof"].cascade_delete_proofs(t["subject_id"], t["predicate_id"], t["object_value"])
            svc["triple"].remove(subject_id=t["subject_id"], predicate_id=t["predicate_id"],
                                 object_value=t["object_value"], object_type=t.get("object_type", "uri"))
            count += 1
        return {"type": "status", "data": {"message": f"Deleted {count} triple(s)"}}
    else:
        triples = svc["triple"].get_by_subject(subject)
        count = 0
        for t in triples:
            svc["proof"].cascade_delete_proofs(t["subject_id"], t["predicate_id"], t["object_value"])
            svc["triple"].remove(subject_id=t["subject_id"], predicate_id=t["predicate_id"],
                                 object_value=t["object_value"], object_type=t.get("object_type", "uri"))
            count += 1
        return {"type": "status", "data": {"message": f"Deleted {count} triple(s)"}}


@command("triple.modify", description="Modify a triple", interactive=True,
         params=[{"name": "subject", "type": "string", "required": True},
                 {"name": "predicate", "type": "string"},
                 {"name": "object", "type": "string"}],
         flags=[{"name": "new-subject", "type": "string"}, {"name": "new-predicate", "type": "string"},
                {"name": "new-object", "type": "string"}, {"name": "str", "type": "flag"},
                {"name": "int", "type": "flag"}, {"name": "float", "type": "flag"},
                {"name": "bool", "type": "flag"}, {"name": "lang", "type": "string"},
                {"name": "katex", "type": "string"}, {"name": "str-dosiero", "type": "string"}])
def cmd_triple_modify(remaining: list[str], flags: dict[str, str]) -> dict:
    svc = get_services()
    subject = flags.get("subject") or (remaining[0] if remaining else "") or ""
    predicate = flags.get("predicate") or (remaining[1] if len(remaining) > 1 else "") or ""
    object_val = flags.get("object") or (remaining[2] if len(remaining) > 2 else "") or ""
    if not subject:
        raise CommandValidationError("Specify a subject")
    triple = None
    if predicate and object_val:
        triple = svc["triple"].get_one(subject, predicate, object_val, object_type="literal")
        if not triple:
            triple = svc["triple"].get_one(subject, predicate, object_val, object_type="uri")
        if not triple:
            try:
                obj_node = svc["node"].resolve_node_id_prefix(object_val)
                if obj_node:
                    triple = svc["triple"].get_one(subject, predicate, obj_node["node_id"], object_type="uri")
                    if triple:
                        object_val = obj_node["node_id"]
            except Exception:
                pass
    if not triple:
        raise CommandValidationError("Triple not found")
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
    noop = (triple["subject_id"] == new_subject and triple["predicate_id"] == new_predicate
            and triple["object_value"] == new_object and triple.get("object_type", "uri") == new_type
            and triple.get("object_unit") == new_unit)
    if noop:
        return {"type": "status", "data": {"message": "No change — triple remains unchanged"}}
    old_type = triple.get("object_type", "uri")
    svc["proof"].cascade_delete_proofs(triple["subject_id"], triple["predicate_id"], triple["object_value"])
    svc["triple"].remove(subject_id=triple["subject_id"], predicate_id=triple["predicate_id"],
                         object_value=triple["object_value"], object_type=old_type)
    svc["triple"].add(subject_id=new_subject, predicate_id=new_predicate, object_value=new_object,
                      object_type=new_type, object_lang=new_lang, object_datatype=new_datatype, object_unit=new_unit)
    return {"type": "status", "data": {"message": f"Triple modified"}}
