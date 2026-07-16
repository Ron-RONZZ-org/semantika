"""Command handlers for node management: list, search, view, add, update, delete, rename, merge.

Typed subcommands live in sibling modules:
- ``node_attachment.py``: ``!node add attachment photo|video|file|code``
- ``node_media.py``: ``!node add media book|film|song|game|podcast``
- ``node_scholarly.py``: ``!node add scholarly paper|patent|conference``
"""

from __future__ import annotations

import json
import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.handlers.node_helpers import (
    _ARC_PREDICATES,
    create_arc_triples,
    ensure_predicate,
    resolve_arc_target,
)
from semantika.server.command.helpers import parse_lang_tag_pairs
from semantika.server.command.registry import command, group_command

logger = logging.getLogger(__name__)


# ── Node commands ────────────────────────────────────────────────────────


@command("node.list", description="List all nodes",
         permission_level=PermissionLevel.READ,
         params=[{"name": "limit", "type": "number", "default": 100}],
         flags=[
             {"name": "order_by", "type": "string", "help": "Sort column (created_at, node_id)"},
             {"name": "direction", "type": "string", "help": "Sort direction (asc, desc)"},
             {"name": "offset", "type": "number", "help": "Row offset for pagination"},
         ],
         list_id_key="nodes")
def cmd_node_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all non-trashed nodes.

    Supports sorting via ``--order_by`` (default ``node_id``) and
    ``--direction`` (default ``asc``). Supports pagination via ``--offset``.
    """
    svc = get_services()
    limit = int(flags.get("limit", 100))
    offset = int(flags.get("offset", 0))
    order_by = flags.get("order_by", "node_id") or "node_id"
    direction = flags.get("direction", "asc") or "asc"
    # Validate sort column to prevent SQL injection
    allowed_columns = {"node_id", "created_at", "updated_at", "label_text"}
    if order_by not in allowed_columns:
        order_by = "node_id"
    direction = "ASC" if direction.lower() == "asc" else "DESC"
    nodes = svc["node"].list(
        limit=limit, offset=offset,
        order_by=order_by, direction=direction,
    )
    total = svc["node"].count()
    return {"type": "node-list", "data": {"nodes": nodes, "total": total}}


@command("node.search", description="Search nodes by label",
         permission_level=PermissionLevel.READ,
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
         permission_level=PermissionLevel.READ,
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_node_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a single node by ID or prefix.

    If the node has a built-in type (PHOTO, VIDEO, DOCUMENT,
    SOURCE_CODE) and a file attachment, returns ``node-view`` response
    with file serving URLs for rich frontend rendering.
    """
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if remaining else "")
    if not node_id:
        raise CommandValidationError("Specify a node ID")
    node = svc["node"].resolve_node_id_prefix(node_id)
    if not node:
        raise CommandValidationError(f"Node not found: {node_id}")
    triples = svc["triple"].get_by_subject(node["node_id"])
    node["triples"] = triples

    # Detect built-in type → switch to node-view response
    builtin_type = _detect_builtin_type(triples)
    if builtin_type:
        file_path = _get_file_path(triples)
        if file_path:
            node["node_type"] = builtin_type
            node["file_url"] = f"/api/v1/files/{node['node_id']}"
            node["file_path"] = file_path
            return {"type": "node-view", "data": node}

    return {"type": "status", "data": node}


def _detect_builtin_type(triples: list[dict]) -> str | None:
    """Check triples for an ``rdf:type`` pointing to a file-attachment type node.

    Returns one of ``"photo"``, ``"video"``, ``"document"``, ``"code"``,
    or ``None``.
    """
    type_map = {
        "PHOTO": "photo",
        "VIDEO": "video",
        "DOCUMENT": "document",
        "SOURCE_CODE": "code",
    }
    for t in triples:
        if t.get("predicate_id") == "rdf:type" and t.get("object_type") == "node":
            mapped = type_map.get(t["object_value"])
            if mapped:
                return mapped
    return None


def _get_file_path(triples: list[dict]) -> str | None:
    """Extract ``:hasFilePath`` value from triples."""
    for t in triples:
        if t.get("predicate_id") == ":hasFilePath":
            return t.get("object_value")
    return None


@group_command("node.add", description="Create nodes in the knowledge graph")
def cmd_node_add_root(remaining: list[str], flags: dict[str, str]) -> dict:
    """Node creation group — use subcommands.

    Available:
      !node add concept                   — Create a generic entity node
      !node add attachment photo|video|file|code  — File-attachment nodes
      !node add media book|film|song|game|podcast — Media/creative works
      !node add scholarly paper|patent|conference — Scholarly works
    """
    return {"type": "status", "title": "Node Add Commands", "data": {
        "_summary": (
            "Available !node add commands:\n"
            "  !node add concept                   — Generic entity with arc shortcuts\n"
            "  !node add attachment photo|video|file|code  — File-attachment nodes\n"
            "  !node add media book|film|song|game|podcast — Media/creative works\n"
            "  !node add scholarly paper|patent|conference — Scholarly works"
        )
    }}


@command("node.add.concept", description="Create a new entity node in the knowledge graph",
         interactive=True,
         form_type="node-add",
         params=[{"name": "labels", "type": "string",
               "required": True,
               "help": "Labels as LANG::TEXT pairs or JSON",
               "placeholder": "en::physicist, eo::fizikisto, fr::physicien"}],
          flags=[
              {"name": "id", "type": "string",
               "help": "Explicit node ID (overrides auto-derivation from label)",
               "placeholder": "PHYSICIST"},
              {"name": "canonical", "type": "string",
               "help": "Custom canonical IRI (overrides the configured template)",
               "placeholder": "https://example.org/node/physicist"},
              {"name": "copy", "type": "flag", "help": "Copy node ID to clipboard"},
              # Arc shortcuts
             {"name": "type", "type": "string",
              "help": "rdf:type target node ID",
              "placeholder": "PROFESSION"},
             {"name": "superclass", "type": "string",
              "help": "rdfs:subClassOf target node ID",
              "placeholder": "SCIENTIST"},
             {"name": "disjoint", "type": "string",
              "help": "owl:disjointWith target node ID",
              "placeholder": "PSEUDOSCIENTIST"},
         ])
def cmd_node_add_concept(remaining: list[str], flags: dict[str, str]) -> dict:
    """Add a new node with optional arc shortcuts.

    Arc shortcuts:
    ``--type <id>``, ``--superclass <id>``, ``--disjoint <id>``
    create ``rdf:type``, ``rdfs:subClassOf``, ``owl:disjointWith`` arcs.

    ``owl:inverseOf`` has been removed from this command — it is a predicate
    property, not a node property.  Use ``!predicate add --inverse`` instead.

    For file attachments and typed nodes, use the group commands:
    ``!node add attachment photo|video|file|code``
    ``!node add media book|film|song|game|podcast``
    ``!node add scholarly paper|patent|conference``

    Deprecated flags ``--img``, ``--attachment``, ``--file``, ``--in-place``,
    ``--move`` have been removed. Use the attachment subcommands instead.
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")

    # Check for removed flags and point to replacement
    _check_removed_flags(flags)

    if labels_raw:
        try:
            labels_dict = json.loads(labels_raw) if labels_raw.startswith("{") else None
        except (json.JSONDecodeError, TypeError):
            labels_dict = None
        payload = {"labels": labels_dict} if labels_dict else {"labels": {"en": labels_raw}}
    else:
        payload = {"labels": {}}
    if explicit_id:
        payload["node_id"] = explicit_id
    canonical = flags.get("canonical", "")
    if canonical:
        payload["iri"] = canonical

    # ── Resolve arc shortcuts ─────────────────────────────────────────
    arc_targets: list[tuple[str, str]] = []
    for flag_name, pred in _ARC_PREDICATES.items():
        val = flags.get(flag_name) or ""
        if val:
            target_id = resolve_arc_target(svc, val, flag_name)
            if target_id:
                arc_targets.append((target_id, pred))

    try:
        node = svc["node"].create(payload)
    except ValueError as e:
        raise CommandValidationError(str(e))

    node_id_val = node["node_id"]
    msg_parts = [f"Created node {node_id_val}"]
    if labels_raw:
        msg_parts.append(f"with label \"{labels_raw}\"")

    created_arcs: list[dict] = []

    # ── Ensure required predicates exist ─────────────────────────────
    if arc_targets:
        ensure_predicate(svc, "rdf:type")
        ensure_predicate(svc, "rdfs:subClassOf")
        ensure_predicate(svc, "owl:disjointWith")

    # ── Create arc triples ───────────────────────────────────────────
    try:
        if arc_targets:
            created_arcs = create_arc_triples(svc, node_id_val, arc_targets)
            msg_parts.append(f"with {len(created_arcs)} arc(s)")
    except Exception:
        logger.warning("Rolling back node %s after post-creation failure", node_id_val)
        try:
            svc["node"].delete(node_id_val, soft=False)
        except Exception as rb_err:
            logger.error("Rollback delete of node %s also failed: %s", node_id_val, rb_err)
        raise

    result: dict = {"message": ". ".join(msg_parts), "node": node}
    if arc_targets:
        result["arcs"] = created_arcs

    copy_flag = "copy" in flags or flags.get("copy", "").lower() in ("true", "1", "yes")
    if copy_flag:
        result["copy_clipboard"] = node_id_val

    return {"type": "status", "data": result}


def _check_removed_flags(flags: dict[str, str]) -> None:
    """Raise a clear error if any removed file-attachment flag is used."""
    removed = {
        "img": "!node add attachment photo",
        "attachment": "!node add attachment video",
        "file": "!node add attachment file",
        "in-place": "!node add attachment photo/video/file --no-copy",
        "move": "!node add attachment photo/video/file with --no-copy",
    }
    for flag_name, replacement in removed.items():
        if flag_name in flags and flags.get(flag_name, ""):
            raise CommandValidationError(
                f"The --{flag_name} flag has been removed. "
                f"Use {replacement} instead."
            )


# ── CRUD commands ────────────────────────────────────────────────────────


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
    """Delete (soft) one or more nodes, moving them to trash.

    Accepts explicit IDs, numbered args (``_1``, ``_2``), or ``--prefix``
    to match all nodes with a given ID prefix.  Uses batched operations
    internally for efficiency.
    """
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
    placeholders = ", ".join(["?"] * len(ids))
    rows = svc["node"].db.execute(
        f"SELECT node_id, "
        f"(SELECT COUNT(*) FROM triples WHERE subject_id = nodes.node_id) AS subject_cnt, "
        f"(SELECT COUNT(*) FROM triples "
        f" WHERE object_type = 'node' AND object_value = nodes.node_id) AS object_cnt "
        f"FROM nodes WHERE node_id IN ({placeholders})",
        tuple(ids),
    )
    for r in rows:
        total = (r["subject_cnt"] or 0) + (r["object_cnt"] or 0)
        if total > 0 and not force:
            raise CommandValidationError(
                f"Deleting '{r['node_id']}' will also remove {total} triple(s). "
                f"Use --force to confirm."
            )

    deleted, errors = svc["node"].batch_delete(ids, soft=True)
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
