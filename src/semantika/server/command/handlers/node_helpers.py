"""Helper functions for node command handlers — arc shortcuts and file attachments."""

from __future__ import annotations

import logging
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
