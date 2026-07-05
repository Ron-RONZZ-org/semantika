"""Command handlers for graph-level operations: stats, export, import, search, view."""

from __future__ import annotations

import logging
from pathlib import Path

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command, group_command

logger = logging.getLogger(__name__)


# ── Group root ────────────────────────────────────────────────────────────


@group_command("graph", description="Graph-level operations: stats, export, import, search, view")
def cmd_graph_root(remaining: list[str], flags: dict[str, str]) -> dict:
    """Graph group help."""
    return {"type": "status", "title": "Graph Commands", "data": {
        "_summary": "Available !graph commands:\n  !graph stats — Graph statistics\n  !graph export — Export as Turtle\n  !graph import — Import Turtle data\n  !graph search — Full-text search\n  !graph view — View all triples for a node"}}


# ── Stats ─────────────────────────────────────────────────────────────────


@command("graph.stats", description="Graph statistics")
def cmd_stats(remaining: list[str], flags: dict[str, str]) -> dict:
    """Show graph statistics."""
    svc = get_services()
    return {"type": "status", "data": svc["triple"].get_stats()}


# ── Export ────────────────────────────────────────────────────────────────


@command("graph.export", description="Export as Turtle",
         flags=[{"name": "output", "type": "string", "help": "Output file path"},
                {"name": "base_uri", "type": "string", "help": "Base URI"}])
def cmd_export(remaining: list[str], flags: dict[str, str]) -> dict:
    """Export the graph in Turtle (.ttl) format."""
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


@command("graph.import", description="Import Turtle data",
         params=[{"name": "data", "type": "string", "required": False}],
         flags=[{"name": "file", "type": "string", "help": "Path to .ttl file to import (alternative to data=)"}])
def cmd_import(remaining: list[str], flags: dict[str, str]) -> dict:
    """Import Turtle (.ttl) data into the graph.

    Provide inline content via ``data=`` or a file path via ``--file``.
    """
    svc = get_services()
    file_path = flags.get("file", "")
    if file_path:
        try:
            ttl_content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise CommandValidationError(f"Cannot read file '{file_path}': {e}")
    else:
        ttl_content = flags.get("data") or (remaining[0] if remaining else "")
    if not ttl_content:
        raise CommandValidationError("Provide TTL content via data= or --file= flag")
    from semantika.graph.triple_turtle import import_turtle as _import

    stats = _import(ttl_content)
    return {"type": "status", "data": stats}


# ── Search ────────────────────────────────────────────────────────────────


def _annotate_triples_with_proofs(
    svc: dict,
    triples: list[dict],
) -> list[dict]:
    """Annotate triples with proof count and proof UUIDs via batch query."""
    if not triples:
        return triples
    arc_keys = [
        (t["subject_id"], t["predicate_id"], t["object_value"])
        for t in triples
    ]
    proof_map = svc["proof"].get_proofs_for_arcs_batch(arc_keys)
    annotated = []
    for t in triples:
        key = (t["subject_id"], t["predicate_id"], t["object_value"])
        proofs = proof_map.get(key, [])
        t["_proof_count"] = len(proofs)
        t["_proof_uuids"] = proofs
        annotated.append(t)
    return annotated


@command("graph.search", description="Full-text search",
         params=[{"name": "q", "type": "string", "required": True}],
         flags=[{"name": "date_from", "type": "string", "help": "Start date"},
                {"name": "date_to", "type": "string", "help": "End date"},
                {"name": "limit", "type": "number", "help": "Max results"}])
def cmd_search(remaining: list[str], flags: dict[str, str]) -> dict:
    """Full-text search across nodes and predicates.

    Results include proof annotations on triples (proof count and UUIDs)
    when proofs exist.
    """
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
    all_triples = list({(t["subject_id"], t["predicate_id"], t["object_value"]): t for t in triples + pred_triples}.values())
    annotated = _annotate_triples_with_proofs(svc, all_triples[:limit])
    return {"type": "status", "data": {"nodes": nodes, "predicates": predicates, "triples": annotated,
                                        "_summary": f"Nodes: {len(nodes)}, Predicates: {len(predicates)}, Triples: {len(annotated)}"}}


# ── View ──────────────────────────────────────────────────────────────────


@command("graph.view", description="View all triples for a node",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a node, predicate, or triple by ID."""
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
