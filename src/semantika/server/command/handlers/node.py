"""Command handlers for node management: list, search, view, add, update, delete, rename, merge."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lightercore.permissions import PermissionLevel

from semantika.core.exceptions import AmbiguousIDError
from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.helpers import parse_lang_tag_pairs
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)

# ── Arc shortcut helpers ────────────────────────────────────────────────

_ARC_PREDICATES: dict[str, str] = {
    "type": "rdf:type",
    "superclass": "rdfs:subClassOf",
    "disjoint": "owl:disjointWith",
    "inverse": "owl:inverseOf",
}


def _ensure_predicate(svc: dict, pred_id: str) -> None:
    """Create a predicate if it does not exist (idempotent)."""
    if not svc["predicate"].get(pred_id):
        svc["predicate"].create({"predicate_id": pred_id, "source": "auto"})


def _resolve_arc_target(
    svc: dict,
    user_input: str,
    flag_name: str,
) -> str | None:
    """Resolve a user-supplied node reference to an exact node_id."""
    try:
        node = svc["node"].resolve_node_id_prefix(user_input)
    except AmbiguousIDError:
        raise CommandValidationError(
            f"Ambiguous {flag_name} target: '{user_input}' matches multiple nodes"
        )
    if node:
        return node["node_id"]
    # Fallback: exact label search
    results = svc["node"].search(user_input, limit=1)
    if results:
        return results[0]["node_id"]
    raise CommandValidationError(
        f"{flag_name.title()} target not found: '{user_input}'"
    )


def _create_arc_triples(
    svc: dict,
    subject_id: str,
    arc_targets: list[tuple[str, str]],
) -> list[dict]:
    """Create arc triples for the given subject.

    Returns the list of created triple dicts.
    Skips duplicates silently (triple_service handles ``ValueError``).
    """
    created = []
    for target_id, pred in arc_targets:
        try:
            triple = svc["triple"].add(
                subject_id=subject_id,
                predicate_id=pred,
                object_value=target_id,
                object_type="uri",
            )
            created.append(triple)
        except ValueError:
            pass  # Duplicate triple — skip silently
    return created


# ── File attachment helpers ──────────────────────────────────────────────


def _handle_file_attachment(
    svc: dict,
    source: str,
    attachment_type: str,
    node_id_val: str,
    in_place: bool = False,
    do_move: bool = False,
) -> list[dict]:
    """Process a file attachment and return file metadata triples.

    Args:
        svc: Service dict.
        source: Local path or HTTP(S) URL.
        attachment_type: ``"img"``, ``"vid"``, or ``"doc"``.
        node_id_val: The node ID (used as filename stem).
        in_place: If True, store reference path instead of copying.
        do_move: If True, move the file instead of copying.

    Returns:
        List of triple dicts (predicate, object, object_type, …).
    """
    from semantika.graph.file_helpers import (
        classify_attachment,
        copy_file,
        detect_mime,
        download_file,
        get_file_size,
        move_file,
    )

    triples: list[dict[str, Any]] = []

    if in_place:
        triples.append({
            "predicate": ":hasFilePath",
            "object": source,
            "object_type": "literal",
        })
        return triples

    is_url = source.strip().lower().startswith(("http://", "https://"))

    try:
        if is_url:
            stored_path = download_file(source, node_id_val, attachment_type)
            source_path = source  # Original URL
        elif do_move:
            stored_path = move_file(Path(source), node_id_val, attachment_type)
            source_path = None  # Original moved — no source to record
        else:
            dest_type = attachment_type or classify_attachment(Path(source))
            stored_path = copy_file(Path(source), node_id_val, dest_type)
            source_path = source
    except (FileNotFoundError, OSError, ValueError) as e:
        raise CommandValidationError(f"File error: {e}")

    mime_type = detect_mime(stored_path)
    file_size = get_file_size(stored_path)

    triples.append({
        "predicate": ":hasFilePath",
        "object": str(stored_path),
        "object_type": "literal",
    })
    triples.append({
        "predicate": ":hasFileMime",
        "object": mime_type,
        "object_type": "literal",
    })
    triples.append({
        "predicate": ":hasFileSize",
        "object": str(file_size),
        "object_type": "literal",
        "object_datatype": "xsd:integer",
    })
    if source_path:
        triples.append({
            "predicate": ":hasFileSource",
            "object": source_path,
            "object_type": "literal",
        })
    return triples


# ── Node commands ────────────────────────────────────────────────────────


@command("node.list", description="List all nodes",
         params=[{"name": "limit", "type": "number", "default": 100}])
def cmd_node_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all non-trashed nodes."""
    svc = get_services()
    nodes = svc["node"].list(limit=int(flags.get("limit", 100)))
    return {"type": "node-list", "data": nodes}


@command("node.search", description="Search nodes by label",
         params=[{"name": "q", "type": "string", "required": True}])
def cmd_node_search(remaining: list[str], flags: dict[str, str]) -> dict:
    """Search nodes by label or definition text."""
    svc = get_services()
    q = flags.get("q", "")
    if not q:
        raise CommandValidationError("Enter a search term")
    nodes = svc["node"].search(q)
    return {"type": "node-list", "data": nodes}


@command("node.view", description="View a node and its triples",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_node_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a single node by ID or prefix."""
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


@command("node.add", description="Create a new node with optional arc shortcuts and file attachments",
         interactive=True,
         params=[{"name": "labels", "type": "string"}],
         flags=[
             {"name": "copy", "type": "flag", "help": "Copy node ID to clipboard"},
             # Arc shortcuts
             {"name": "type", "type": "string", "help": "rdf:type target node ID"},
             {"name": "superclass", "type": "string", "help": "rdfs:subClassOf target node ID"},
             {"name": "disjoint", "type": "string", "help": "owl:disjointWith target node ID"},
             {"name": "inverse", "type": "string", "help": "owl:inverseOf target node ID"},
             # File attachments
             {"name": "img", "type": "string", "help": "Attach image (path or URL)"},
             {"name": "attachment", "type": "string", "help": "Attach video (path or URL)"},
             {"name": "file", "type": "string", "help": "Attach arbitrary file (path or URL)"},
             {"name": "in-place", "type": "flag", "help": "Store reference only, do not copy file"},
             {"name": "move", "type": "flag", "help": "Move file instead of copying (local only)"},
         ])
def cmd_node_add(remaining: list[str], flags: dict[str, str]) -> dict:
    """Add a new node with optional arc shortcuts and file attachments.

    Arc shortcuts:
    ``--type <id>``, ``--superclass <id>``, ``--disjoint <id>``, ``--inverse <id>``
    create ``rdf:type``, ``rdfs:subClassOf``, ``owl:disjointWith``, ``owl:inverseOf`` arcs.

    File attachments:
    ``--img``, ``--attachment``, ``--file`` accept local paths or URLs.
    ``--in-place`` stores a reference without copying; ``--move`` moves instead of copying.
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    payload = {"labels": {"en": labels_raw}} if labels_raw else {"labels": {}}

    # ── Resolve arc shortcuts ─────────────────────────────────────────
    arc_targets: list[tuple[str, str]] = []
    for flag_name, pred in _ARC_PREDICATES.items():
        val = flags.get(flag_name) or ""
        if val:
            target_id = _resolve_arc_target(svc, val, flag_name)
            if target_id:
                arc_targets.append((target_id, pred))

    # ── File attachment ───────────────────────────────────────────────
    file_attachment_type: str | None = None
    file_source: str | None = None
    for ft, atype in [("img", "img"), ("attachment", "vid"), ("file", "doc")]:
        val = flags.get(ft) or ""
        if val:
            file_attachment_type = atype
            file_source = val
            break

    in_place = "in-place" in flags or "in_place" in flags or flags.get("in-place", "").lower() in ("true", "1", "yes")
    do_move = "move" in flags or flags.get("move", "").lower() in ("true", "1", "yes")

    try:
        node = svc["node"].create(payload)
    except ValueError as e:
        raise CommandValidationError(str(e))

    node_id_val = node["node_id"]
    msg_parts = [f"Created node {node_id_val}"]
    if labels_raw:
        msg_parts.append(f"with label \"{labels_raw}\"")

    created_arcs: list[dict] = []
    file_triples: list[dict] = []

    # ── Ensure required predicates exist ─────────────────────────────
    if arc_targets or file_source:
        _ensure_predicate(svc, "rdf:type")
        _ensure_predicate(svc, "rdfs:subClassOf")
        _ensure_predicate(svc, "owl:disjointWith")
        _ensure_predicate(svc, "owl:inverseOf")
        for fp in (":hasFilePath", ":hasFileMime", ":hasFileSize", ":hasFileSource"):
            _ensure_predicate(svc, fp)

    # ── Create arc triples + handle file attachment ──────────────────
    # Both are inside the try block so that any failure rolls back
    # the entire post-creation operation (node hard-delete cascades FK).
    try:
        if arc_targets:
            created_arcs = _create_arc_triples(svc, node_id_val, arc_targets)
            msg_parts.append(f"with {len(created_arcs)} arc(s)")

        if file_source:
            file_triples = _handle_file_attachment(
                svc, file_source, file_attachment_type, node_id_val,
                in_place=in_place, do_move=do_move,
            )
            if file_triples:
                # Create file metadata triples
                file_arcs = [
                    (node_id_val, ft["predicate"], ft["object"])
                    for ft in file_triples
                ]
                _create_arc_triples(svc, node_id_val, [(o, p) for _, p, o in file_arcs])
                msg_parts.append("with file attachment")
    except CommandValidationError:
        # Roll back node creation if any post-creation step fails.
        # The schema has REFERENCES without ON DELETE CASCADE, so
        # hard-deleting the node removes orphan triples too.
        svc["node"].delete(node_id_val, soft=False)
        raise

    result: dict = {"message": ". ".join(msg_parts), "node": node}
    if arc_targets:
        result["arcs"] = created_arcs
    if file_triples:
        result["file_triples"] = file_triples

    copy_flag = "copy" in flags or flags.get("copy", "").lower() in ("true", "1", "yes")
    if copy_flag:
        result["copy_clipboard"] = node_id_val

    return {"type": "status", "data": result}


@command("node.update", description="Update node labels/definitions",
         params=[{"name": "id", "type": "string", "required": True}],
         flags=[{"name": "labels", "type": "string", "help": "New labels (JSON or LANG::TEXT)"},
                {"name": "definitions", "type": "string", "help": "New definitions"},
                {"name": "new-id", "type": "string", "help": "Rename to new ID"}])
def cmd_node_update(remaining: list[str], flags: dict[str, str]) -> dict:
    """Update a node's labels, definitions, or ID."""
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
            labels_dict = json.loads(labels_raw)
        except json.JSONDecodeError:
            labels_dict = parse_lang_tag_pairs(labels_raw)
        payload["labels"] = labels_dict
    defs_raw = flags.get("definitions") or flags.get("defs") or ""
    if defs_raw:
        try:
            defs_dict = json.loads(defs_raw)
        except json.JSONDecodeError:
            defs_dict = parse_lang_tag_pairs(defs_raw)
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
    """Delete (soft) a node, moving it to trash."""
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
    force = flags.get("force", "").lower() in ("true", "1", "yes")
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
    """Rename a node (change its ID)."""
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
         permission_level=PermissionLevel.DESTRUCTIVE,
         params=[{"name": "source", "type": "string", "required": True},
                 {"name": "target", "type": "string", "required": True}],
         flags=[{"name": "force", "type": "flag", "help": "Skip preview and merge immediately"}])
def cmd_node_merge(remaining: list[str], flags: dict[str, str]) -> dict:
    """Merge a source node into a target node.

    Without ``--force``, shows a preview of label diffs and triple collision
    counts before applying the merge.
    """
    svc = get_services()
    source = flags.get("source") or (remaining[0] if len(remaining) > 0 else "") or ""
    target = flags.get("target") or (remaining[1] if len(remaining) > 1 else "") or ""
    if not source or not target:
        raise CommandValidationError("Specify source and target node IDs")

    if source == target:
        raise CommandValidationError("Source and target must be different nodes")

    src_node = svc["node"].resolve_node_id_prefix(source)
    if not src_node:
        raise CommandValidationError(f"Source node not found: {source}")
    tgt_node = svc["node"].resolve_node_id_prefix(target)
    if not tgt_node:
        raise CommandValidationError(f"Target node not found: {target}")

    # Build preview
    import json as _json
    try:
        src_labels = _json.loads(src_node["labels"]) if isinstance(src_node["labels"], str) else src_node.get("labels", {})
    except (_json.JSONDecodeError, TypeError):
        src_labels = {}
    try:
        tgt_labels = _json.loads(tgt_node["labels"]) if isinstance(tgt_node["labels"], str) else tgt_node.get("labels", {})
        if not isinstance(tgt_labels, dict):
            tgt_labels = {}
    except (_json.JSONDecodeError, TypeError):
        tgt_labels = {}

    src_triples = svc["triple"].get_by_subject(src_node["node_id"])
    tgt_triples = svc["triple"].get_by_subject(tgt_node["node_id"])
    subject_collisions = sum(
        1 for st in src_triples
        if any(
            tt["predicate_id"] == st["predicate_id"]
            and tt["object_value"] == st["object_value"]
            and tt["object_type"] == st["object_type"]
            for tt in tgt_triples
        )
    )

    preview = {
        "source": source,
        "target": target,
        "source_labels": src_labels,
        "target_labels": tgt_labels,
        "added_labels": {k: v for k, v in src_labels.items() if k not in tgt_labels},
        "source_triple_count": len(src_triples),
        "target_triple_count": len(tgt_triples),
        "triple_collisions": subject_collisions,
    }

    force_flag = "force" in flags or flags.get("force", "").lower() in ("true", "1", "yes")
    if not force_flag:
        return {"type": "status", "data": {"message": "Merge preview — use --force to proceed", "preview": preview}}

    try:
        result = svc["node"].merge_nodes(source, target)
        return {"type": "status", "data": {"message": f"Merged {source} into {target}", "node": result}}
    except ValueError as e:
        raise CommandValidationError(str(e))
