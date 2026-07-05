"""Command handlers for graph-level operations: stats, export, import, search, view."""

from __future__ import annotations

import logging
from pathlib import Path

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)


# ── Stats ─────────────────────────────────────────────────────────────────


@command("stats", description="Graph statistics")
def cmd_stats(remaining: list[str], flags: dict[str, str]) -> dict:
    """Show graph statistics."""
    svc = get_services()
    return {"type": "status", "data": svc["triple"].get_stats()}


# ── Export ────────────────────────────────────────────────────────────────


@command("export", description="Export as Turtle",
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


@command("import", description="Import Turtle data",
         params=[{"name": "data", "type": "string", "required": True}])
def cmd_import(remaining: list[str], flags: dict[str, str]) -> dict:
    """Import Turtle (.ttl) data into the graph."""
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
    """Full-text search across nodes and predicates."""
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
    return {"type": "status", "data": {"nodes": nodes, "predicates": predicates, "triples": all_triples[:limit],
                                        "_summary": f"Nodes: {len(nodes)}, Predicates: {len(predicates)}, Triples: {len(all_triples)}"}}


# ── View ──────────────────────────────────────────────────────────────────


@command("view", description="View all triples for a node",
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
