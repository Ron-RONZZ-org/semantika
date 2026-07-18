"""Quote-type node creation subcommand.

This module provides the ``!node add quote`` command for creating quotation
nodes with semantic metadata. Quotes are textual excerpts attributed to a
source, optionally linked to a chapter and an ``sm:attributedTo`` entity.

Accessible as::

    !node add quote --labels "en::To be or not to be..."

Auto-created triples:
    - ``rdf:type QUOTE``
    - ``{SOURCE} sm:hasExcerpt {quote_id}``
    - ``{quote_id} sm:attributedTo {ATTRIBUTED_TO}`` (if ``--attributed-to``)
    - ``{quote_id} sm:partOf {CHAPTER}`` (if ``--chapter``)

Node ID auto-generation:
    When ``--source`` is given, the node ID is computed as
    ``{SOURCE_ID}_QUOTE_{n}`` where ``n`` is the next sequential number
    (1, 2, 3, …).  Without ``--source``, the default label-based
    auto-ID logic applies.
"""

from __future__ import annotations

import logging
import sqlite3

from semantika.graph.db import get_services
from semantika.server.command.handlers.node_helpers import (
    create_typed_node,
    resolve_node_refs,
)
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)

_QUOTE_TYPE = "QUOTE"


# ── Helper ──────────────────────────────────────────────────────────────


def _next_quote_sequence(svc: dict, source_id: str) -> int:
    """Return the next sequence number for a quote from the given source.

    Queries existing nodes whose ``node_id`` matches the pattern
    ``{source_id}_QUOTE_<n>`` and returns ``max(n) + 1``.
    Defaults to 1 when no quotes exist yet.

    Args:
        svc: Service dict.
        source_id: The source node's ID.

    Returns:
        The next sequence number (1-based).
    """
    prefix = f"{source_id}_QUOTE_"
    try:
        rows = svc["node"].db.execute(
            "SELECT node_id FROM nodes WHERE node_id LIKE ?",
            (f"{prefix}%",),
        )
    except sqlite3.Error as e:
        logger.warning("DB error in _next_quote_sequence: %s", e)
        return 1

    max_n = 0
    for row in rows:
        suffix = row["node_id"].removeprefix(prefix)
        if suffix.isdigit():
            n = int(suffix)
            if n > max_n:
                max_n = n
    return max_n + 1


def _ensure_source_node(svc: dict, source_id: str) -> dict | None:
    """Validate and return the source node, raising if not found.

    Args:
        svc: Service dict.
        source_id: The source node ID.

    Returns:
        The source node dict.

    Raises:
        CommandValidationError: If the source node does not exist.
    """
    source = svc["node"].get(source_id)
    return source


# ── Handler ─────────────────────────────────────────────────────────────


@command("node.add.quote",
         description="Create a quote node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "labels", "type": "string",
              "help": "Quote text as LANG::TEXT pairs or JSON (required)",
              "placeholder": "en::To be or not to be..."},
             {"name": "source", "type": "string",
              "help": "Source node ID — enables auto-ID (SOURCE_QUOTE_n) and creates sm:hasExcerpt triple",
              "placeholder": "HAMLET"},
             {"name": "chapter", "type": "string",
              "help": "Chapter node ID (creates sm:partOf triple)",
              "placeholder": "ACT_3"},
             {"name": "attributed-to", "type": "string",
              "help": "Attributed-to node ID (creates sm:attributedTo triple)",
              "placeholder": "HAMLET"},
         ])
def cmd_node_add_quote(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a quote node with semantic metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``QUOTE``
    - ``{SOURCE} sm:hasExcerpt {quote_id}`` if ``--source`` is provided
    - ``sm:attributedTo`` triple if ``--attributed-to`` is provided
    - ``sm:partOf`` triple if ``--chapter`` is provided

    Node ID is auto-generated as ``{SOURCE}_QUOTE_n`` when ``--source`` is
    provided, with the serial number ``n`` determined by existing quotes
    for that source.
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    source_raw = (flags.get("source") or "").strip()
    chapter_raw = (flags.get("chapter") or "").strip()
    attributed_raw = (flags.get("attributed-to") or "").strip()

    # ── Resolve source node ──────────────────────────────────────────
    node_id_override = ""
    source_id = ""
    if source_raw:
        source_nodes = resolve_node_refs(svc, source_raw, "source")
        source_id = source_nodes[0]
        seq = _next_quote_sequence(svc, source_id)
        node_id_override = f"{source_id}_QUOTE_{seq}"

    # ── Resolve attributed-to and chapter ────────────────────────────
    attributed_nodes = resolve_node_refs(svc, attributed_raw, "attributed-to") if attributed_raw else []
    chapter_nodes = resolve_node_refs(svc, chapter_raw, "chapter") if chapter_raw else []

    # ── Build extra triples for the quote node itself ────────────────
    extra_fields: list[tuple[str, str, str, str]] = []

    for attr_id in attributed_nodes:
        extra_fields.append(("sm:attributedTo", attr_id, "node", ""))
    for ch_id in chapter_nodes:
        extra_fields.append(("sm:partOf", ch_id, "node", ""))

    # ── Create the quote node ────────────────────────────────────────
    result = create_typed_node(svc, labels_raw, node_id_override, _QUOTE_TYPE, extra_fields)
    quote_node = result["node"]
    quote_id = quote_node["node_id"]

    # ── Add SOURCE sm:hasExcerpt quote_id triple ─────────────────────
    # This triple is on the SOURCE node, not on the quote node.
    # It must be added separately from create_typed_node.
    sm_arcs_created: list[dict] = []
    if source_id:
        try:
            svc["builtin_type"].ensure_predicates(["sm:hasExcerpt"])
            excerpt_triple = svc["triple"].add(
                subject_id=source_id,
                predicate_id="sm:hasExcerpt",
                object_value=quote_id,
                object_type="node",
            )
            sm_arcs_created.append(excerpt_triple)
        except ValueError:
            pass  # Duplicate triple — skip silently

    # ── Build response ───────────────────────────────────────────────
    all_triples = list(result.get("semantic_triples", [])) + sm_arcs_created

    return {
        "type": "status",
        "data": {
            **result,
            "semantic_triples": all_triples,
        },
    }
