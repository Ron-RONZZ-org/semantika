"""Helper functions for node command handlers — arc shortcuts, file attachments, semantic triples."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from semantika.core.exceptions import AmbiguousIDError
from semantika.server.command.errors import CommandValidationError

logger = logging.getLogger(__name__)

# ── Arc shortcut helpers ────────────────────────────────────────────────

_ARC_PREDICATES: dict[str, str] = {
    "type": "rdf:type",
    "superclass": "rdfs:subClassOf",
    "disjoint": "owl:disjointWith",
    "inverse": "owl:inverseOf",
}


def ensure_predicate(svc: dict, pred_id: str) -> None:
    """Create a predicate if it does not exist (idempotent)."""
    if not svc["predicate"].get(pred_id):
        svc["predicate"].create({"predicate_id": pred_id, "source": "auto"})


def resolve_arc_target(
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


def create_arc_triples(
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


def handle_file_attachment(
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


# ── Specialised node add helpers ────────────────────────────────────────


def resolve_node_refs(svc: dict, raw: str, flag_name: str) -> list[str]:
    """Resolve a comma-separated string of node references to node IDs.

    Each token is resolved via prefix or label search.  Raises
    ``CommandValidationError`` if any token is unresolvable.

    Args:
        svc: Service dict.
        raw: Comma-separated node IDs or labels.
        flag_name: Flag name for error messages.

    Returns:
        List of resolved node IDs.
    """
    if not raw:
        return []
    ids: list[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            node = svc["node"].resolve_node_id_prefix(token)
            if node:
                ids.append(node["node_id"])
                continue
        except AmbiguousIDError:
            raise CommandValidationError(
                f"Ambiguous {flag_name} target: '{token}' matches multiple nodes"
            )
        # Fallback: label search
        results = svc["node"].search(token, limit=1)
        if results:
            ids.append(results[0]["node_id"])
        else:
            raise CommandValidationError(
                f"{flag_name.title()} target not found: '{token}'"
            )
    return ids


def parse_dimension(raw: str) -> str | None:
    """Validate and normalise a dimension string (e.g. ``1920x1080``).

    Returns the normalised form (width x height with lowercase 'x'),
    or ``None`` if the input is empty.

    Raises:
        CommandValidationError: If the format is invalid.
    """
    if not raw:
        return None
    raw = raw.strip()
    m = re.match(r"^(\d+)\s*[xX×]\s*(\d+)$", raw)
    if not m:
        raise CommandValidationError(
            f"Invalid dimension '{raw}'. Use format like '1920x1080'"
        )
    return f"{m.group(1)}x{m.group(2)}"


def create_semantic_triples(
    svc: dict,
    subject_id: str,
    predicate_id: str,
    object_ids: list[str],
) -> list[dict]:
    """Create ``subject predicate object`` triples for each object ID.

    Args:
        svc: Service dict.
        subject_id: The subject node ID.
        predicate_id: The predicate ID (e.g. ``"sm:depicts"``).
        object_ids: List of object node IDs.

    Returns:
        List of created triple dicts.
    """
    created = []
    for obj_id in object_ids:
        try:
            triple = svc["triple"].add(
                subject_id=subject_id,
                predicate_id=predicate_id,
                object_value=obj_id,
                object_type="uri",
            )
            created.append(triple)
        except ValueError:
            pass  # Duplicate — skip silently
    return created


def attach_file_and_create_node(
    svc: dict,
    labels_raw: str,
    file_path: str,
    attachment_type: str,
    node_type: str,
    explicit_id: str = "",
    no_copy: bool = False,
    canonical_link: str = "",
    extra_fields: list[tuple[str, str, str, str]] | None = None,
) -> dict:
    """Create a node with file attachment, type triple, and optional canonical link.

    This is the shared workflow for ``!node add photo|video|file|code``.

    Args:
        svc: Service dict.
        labels_raw: Label string (JSON or LANG::TEXT) for the node.
        file_path: Path or URL to the file.
        attachment_type: ``"img"``, ``"vid"``, or ``"doc"``.
        node_type: The builtin type node ID (e.g. ``"sm:Photo"``).
        explicit_id: Optional explicit node ID.
        no_copy: If True, store reference only (do not copy file).
        canonical_link: Optional canonical URL.
        extra_fields: Optional list of ``(predicate_id, object_value, object_type, object_datatype)``
            tuples to create as additional triples on the node.

    Returns:
        Dict with ``node``, ``message_parts``, ``file_triples``, ``semantic_triples``.
    """
    import json

    # 1. Ensure builtins exist
    svc["builtin_type"].ensure_builtins()

    # 2. Parse labels
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

    # 3. Create the node
    try:
        node = svc["node"].create(payload)
    except ValueError as e:
        raise CommandValidationError(str(e))

    node_id_val = node["node_id"]
    msg_parts = [f"Created node {node_id_val}"]
    if labels_raw:
        msg_parts.append(f"with label \"{labels_raw}\"")

    created_file_triples: list[dict] = []
    semantic_triples: list[dict] = []
    combined_arcs: list[tuple[str, str]] = []

    try:
        # 4. Handle file attachment
        use_in_place = no_copy
        file_triple_list = handle_file_attachment(
            svc, file_path, attachment_type, node_id_val,
            in_place=use_in_place, do_move=False,
        )
        if file_triple_list:
            created_file_triples = file_triple_list
            msg_parts.append("with file attachment")
            # File metadata triples have object_type='literal' — create
            # them directly (not through create_arc_triples which forces 'uri').
            for ft in file_triple_list:
                try:
                    svc["triple"].add(
                        subject_id=node_id_val,
                        predicate_id=ft["predicate"],
                        object_value=ft["object"],
                        object_type=ft.get("object_type", "literal"),
                        object_datatype=ft.get("object_datatype"),
                    )
                except ValueError:
                    pass

        # rdf:type and canonical-link are URI-type arcs — use create_arc_triples
        arc_targets: list[tuple[str, str]] = []
        arc_targets.append((node_type, "rdf:type"))

        if canonical_link:
            svc["builtin_type"].ensure_predicates(["sm:canonicalLink"])
            arc_targets.append((canonical_link, "sm:canonicalLink"))

        # 5. Create URI arc triples
        if arc_targets:
            create_arc_triples(svc, node_id_val, arc_targets)
            msg_parts.append(f"with {len(arc_targets)} triple(s)")

        # 6. Extra semantic triples
        if extra_fields:
            svc["builtin_type"].ensure_predicates([ef[0] for ef in extra_fields])
            for pred_id, obj_val, obj_type, obj_dt in extra_fields:
                try:
                    triple = svc["triple"].add(
                        subject_id=node_id_val,
                        predicate_id=pred_id,
                        object_value=obj_val,
                        object_type=obj_type,
                        object_datatype=obj_dt or None,
                    )
                    semantic_triples.append(triple)
                except ValueError:
                    pass

    except Exception:
        # Roll back node creation on failure
        logger.warning("Rolling back node %s after post-creation failure", node_id_val)
        try:
            svc["node"].delete(node_id_val, soft=False)
        except Exception as rb_err:
            logger.error("Rollback delete of node %s also failed: %s", node_id_val, rb_err)
        raise

    return {
        "node": node,
        "message_parts": msg_parts,
        "file_triples": created_file_triples,
        "semantic_triples": semantic_triples,
    }
