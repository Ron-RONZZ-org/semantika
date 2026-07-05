"""Turtle (.ttl) export for the triple store.

Ported from A-semantika's ``_triple_turtle.py``.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any

from semantika.core import SemantikaDB

logger = logging.getLogger(__name__)

_KNOWN_PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "owl": "http://www.w3.org/2002/07/owl#",
}


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

    Args:
        turtle_content: Raw Turtle format string.

    Returns:
        Dict with counts: nodes_created, predicates_created, triples_added.
    """
    from rdflib import BNode, Graph, Literal, URIRef
    from semantika.graph.db import get_services

    svc = get_services()
    g = Graph()
    g.parse(data=turtle_content, format="turtle")

    stats: dict[str, int] = {
        "nodes_created": 0,
        "predicates_created": 0,
        "triples_added": 0,
    }

    for s, p, o in g:
        subject_id = str(s)
        predicate_id = str(p)

        if isinstance(o, URIRef):
            object_value = str(o)
            object_type = "uri"
            object_lang = None
            object_datatype = None
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
        else:
            continue

        for node_id in {subject_id, object_value} if object_type == "uri" else {subject_id}:
            try:
                svc["node"].create({"node_id": node_id, "labels": {"en": node_id}})
                stats["nodes_created"] += 1
            except ValueError:
                logger.debug("Node %s already exists (Turtle import)", node_id)

        try:
            svc["predicate"].create({"predicate_id": predicate_id, "labels": {"en": predicate_id}})
            stats["predicates_created"] += 1
        except ValueError:
            logger.debug("Predicate %s already exists (Turtle import)", predicate_id)

        try:
            svc["triple"].add(
                subject_id,
                predicate_id,
                object_value,
                object_type=object_type,
                object_lang=object_lang,
                object_datatype=object_datatype,
            )
            stats["triples_added"] += 1
        except ValueError as exc:
            logger.debug("Triple (%s, %s, %s) skipped (Turtle import): %s",
                         subject_id, predicate_id, object_value, exc)

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
        if nid in label_map and label_map[nid]:
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
