"""Turtle (.ttl) export for the triple store.

Ported from A-semantika's ``_triple_turtle.py``.
"""

from __future__ import annotations

import json
import logging
import urllib.parse

from rdflib import BNode, Graph, Literal, URIRef

from semantika.core import SemantikaDB

logger = logging.getLogger(__name__)

from semantika.graph.constants import KNOWN_PREFIXES as _KNOWN_PREFIXES


def _format_turtle_uri(val: str, prefix_uris: dict[str, str], base_uri: str) -> str:
    """Format a value as a Turtle URI (prefixed name or full URI).

    Handles three cases:
    1. Full URI (starts with http:// etc.) → map to known prefix or emit full <URI>
    2. Prefixed name (contains ``:``, e.g. ``rdf:type``) → emit as-is
    3. Plain name (no ``:``, e.g. ``DOG``) → emit as ``:name``
    """
    for prefix, uri in prefix_uris.items():
        if val.startswith(uri):
            local = val[len(uri):]
            if local:
                return f"{prefix}:{local}"
    for prefix, uri in _KNOWN_PREFIXES.items():
        if val.startswith(uri):
            local = val[len(uri):]
            if local:
                return f"{prefix}:{local}"
    if val.startswith("http://") or val.startswith("https://"):
        # Full URI that wasn't caught by known prefixes — emit as-is
        return f"<{val}>"
    if ":" in val:
        # Prefixed name (e.g. rdf:type, custom:predicate) — emit as-is.
        # These are already valid Turtle prefixed names.
        return val
    if val and val[0].isdigit():
        # Digit-prefixed names need full URI
        cleaned = urllib.parse.quote(val, safe="")
        return f"<{base_uri}{cleaned}>"
    return f":{val}"


def _format_literal(value: str, datatype: str | None, lang: str | None) -> str:
    """Format a literal value for Turtle output."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    if lang:
        return f'"{escaped}"@{lang}'
    if datatype:
        type_uri = _KNOWN_PREFIXES.get("xsd", "") + datatype
        return f'"{escaped}"^^<{type_uri}>'
    return f'"{escaped}"'


def import_turtle(turtle_content: str) -> dict[str, int]:
    """Import Turtle (.ttl) content into the triple store.

    Uses a two-phase approach:
    1. Parse the graph, collect all triples and extract labels from ``rdfs:label``
    2. Create nodes/predicates/triples in bulk with proper labels

    Args:
        turtle_content: Raw Turtle format string.

    Returns:
        Dict with counts: nodes_created, predicates_created, triples_added.
    """
    from semantika.graph.db import get_services

    svc = get_services()
    g = Graph()
    g.parse(data=turtle_content, format="turtle")

    stats: dict[str, int] = {
        "nodes_created": 0,
        "predicates_created": 0,
        "triples_added": 0,
    }

    # ── Phase 1: Collect triples and build label map ────────────────────

    RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
    triples_to_add: list[dict] = []
    all_uris: set[str] = set()
    label_map: dict[str, dict[str, str]] = {}  # node_uri -> {lang: label}

    for s, p, o in g:
        subject_id = str(s)
        predicate_id = str(p)
        all_uris.add(subject_id)

        if isinstance(o, URIRef):
            object_value = str(o)
            object_type = "uri"
            object_lang: str | None = None
            object_datatype: str | None = None
            all_uris.add(object_value)
        elif isinstance(o, Literal):
            object_value = str(o)
            object_type = "literal"
            object_lang = o.language
            object_datatype = str(o.datatype) if o.datatype else None
        elif isinstance(o, BNode):
            object_value = str(o)
            object_type = "uri"
            object_lang = None
            object_datatype = None
            all_uris.add(object_value)
        else:
            continue

        # Extract rdfs:label triples for node label map
        if predicate_id == RDFS_LABEL and object_type == "literal":
            lang = object_lang or "en"
            label_map.setdefault(subject_id, {})[lang] = object_value

        triples_to_add.append({
            "subject_id": subject_id,
            "predicate_id": predicate_id,
            "object_value": object_value,
            "object_type": object_type,
            "object_lang": object_lang,
            "object_datatype": object_datatype,
        })

    # ── Phase 2: Create nodes with proper labels ────────────────────────

    for uri in sorted(all_uris):
        labels = label_map.get(uri, {"en": uri})
        try:
            svc["node"].create({"node_id": uri, "labels": labels})
            stats["nodes_created"] += 1
        except ValueError:
            logger.debug("Node %s already exists (Turtle import)", uri)

    # ── Phase 3: Create predicates ──────────────────────────────────────

    seen_predicates: set[str] = set()
    for t in triples_to_add:
        pid = t["predicate_id"]
        if pid not in seen_predicates:
            seen_predicates.add(pid)
            try:
                svc["predicate"].create({"predicate_id": pid, "labels": {"en": pid}})
                stats["predicates_created"] += 1
            except ValueError:
                logger.debug("Predicate %s already exists (Turtle import)", pid)

    # ── Phase 4: Add triples ────────────────────────────────────────────

    for t in triples_to_add:
        try:
            svc["triple"].add(
                t["subject_id"],
                t["predicate_id"],
                t["object_value"],
                object_type=t["object_type"],
                object_lang=t["object_lang"],
                object_datatype=t["object_datatype"],
            )
            stats["triples_added"] += 1
        except ValueError as exc:
            logger.debug("Triple (%s, %s, %s) skipped (Turtle import): %s",
                         t["subject_id"], t["predicate_id"], t["object_value"], exc)

    return stats


def export_turtle(db: SemantikaDB, base_uri: str = "https://example.org/") -> str:
    """Export triple store as Turtle.

    Args:
        db: Database instance.
        base_uri: Base URI for un-prefixed node IDs.

    Returns:
        Turtle (.ttl) format string.
    """
    lines: list[str] = []

    # Prefix declarations
    for prefix, uri in _KNOWN_PREFIXES.items():
        lines.append(f"@prefix {prefix}: <{uri}> .")
    lines.append("")

    # Get all nodes with labels
    nodes = db.execute("SELECT node_id, labels FROM nodes")

    # Build label map
    label_map: dict[str, dict[str, str]] = {}
    for node in nodes:
        try:
            labels = json.loads(node["labels"]) if isinstance(node["labels"], str) else node["labels"]
            if isinstance(labels, dict):
                label_map[node["node_id"]] = labels
        except (json.JSONDecodeError, TypeError):
            pass

    # Get all triples
    triples = db.execute(
        "SELECT subject_id, predicate_id, object_value, object_type, "
        "object_lang, object_datatype FROM triples ORDER BY subject_id, predicate_id"
    )

    # Group triples by subject
    subjects: dict[str, list[dict]] = {}
    seen_subjects: set[str] = set()
    seen_objects: set[str] = set()

    for t in triples:
        subj = t["subject_id"]
        subjects.setdefault(subj, []).append(t)
        seen_subjects.add(subj)
        if t["object_type"] == "uri":
            seen_objects.add(t["object_value"])

    # Emit triples grouped by subject
    for subj in sorted(subjects):
        subj_triples = subjects[subj]
        # Subject line
        lines.append(f"{_format_turtle_uri(subj, {}, base_uri)}")
        for i, t in enumerate(subj_triples):
            pred = _format_turtle_uri(t["predicate_id"], {}, base_uri)
            if t["object_type"] == "uri":
                obj = _format_turtle_uri(t["object_value"], {}, base_uri)
            else:
                obj = _format_literal(
                    t["object_value"],
                    t.get("object_datatype"),
                    t.get("object_lang"),
                )
            separator = " ." if i == len(subj_triples) - 1 else " ;"
            lines.append(f"    {pred} {obj}{separator}")
        lines.append("")

    # Nodes without outgoing triples but with labels
    all_node_ids = set(n["node_id"] for n in nodes)
    orphan_ids = all_node_ids - seen_subjects - seen_objects
    for nid in sorted(orphan_ids):
        if label_map.get(nid):
            lines.append(f"{_format_turtle_uri(nid, {}, base_uri)}")
            labels = label_map[nid]
            label_lines = []
            for lang, val in labels.items():
                if val:
                    escaped = val.replace("\\", "\\\\").replace('"', '\\"')
                    label_lines.append(f'"{escaped}"@{lang}')
            if label_lines:
                lines.append(f"    rdfs:label {', '.join(label_lines)} .")
                lines.append("")

    return "\n".join(lines)
