"""LLM tools for graph-level operations.

Provides graph-wide statistics so the LLM can answer high-level questions
about the knowledge graph size and structure.
"""

from __future__ import annotations

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services, get_sparql_engine
from semantika.server.llm.tools import llm_tool


@llm_tool(
    name="graph.stats",
    description="Get statistics about the knowledge graph: total node count, "
    "predicate count, triple count, and SPARQL engine sync status. "
    "Use this before deciding which tools to call for a complex query.",
    permission_level=PermissionLevel.READ,
)
def llm_graph_stats(**kwargs) -> dict:
    """Return aggregate statistics for the entire knowledge graph."""
    svc = get_services()
    node_count = 0
    pred_count = 0
    triple_count = 0

    try:
        node_svc = svc.get("node")
        if node_svc:
            node_count = node_svc.count() if hasattr(node_svc, "count") else 0
    except Exception:
        pass

    try:
        pred_svc = svc.get("predicate")
        if pred_svc:
            pred_count = pred_svc.count() if hasattr(pred_svc, "count") else 0
    except Exception:
        pass

    try:
        triple_svc = svc.get("triple")
        if triple_svc:
            triple_count = triple_svc.count() if hasattr(triple_svc, "count") else 0
    except Exception:
        pass

    engine = get_sparql_engine()
    sparql_available = engine is not None

    return {
        "success": True,
        "data": {
            "nodes": node_count,
            "predicates": pred_count,
            "triples": triple_count,
            "sparql_available": sparql_available,
        },
    }
