"""Command handlers for SPARQL queries — !sparql command."""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_sparql_engine, init_sparql_engine
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command, group_command

logger = logging.getLogger(__name__)


def _ensure_engine():
    """Get the SPARQL engine, lazy-initializing if needed."""
    engine = get_sparql_engine()
    if engine is not None:
        return engine
    engine = init_sparql_engine()
    if engine is None:
        raise CommandValidationError(
            "SPARQL engine is not available. "
            "The pyoxigraph library is required (pip install pyoxigraph)."
        )
    return engine


@group_command("sparql", description="Execute SPARQL queries against the triple store")
def cmd_sparql_root(remaining: list[str], flags: dict[str, str]) -> dict:
    """SPARQL command group help."""
    return {"type": "status", "title": "SPARQL Commands", "data": {
        "_summary": (
            "Available !sparql commands:\n"
            "  !sparql query 'SELECT ...' — Run a SPARQL SELECT query\n"
            "  !sparql status — Show SPARQL engine status\n"
        )
    }}


@command("sparql.query", description="Run a SPARQL SELECT/ASK query",
         permission_level=PermissionLevel.READ,
         params=[{"name": "query", "type": "string", "required": True}],
         flags=[{"name": "format", "type": "string", "help": "Response format: json, table (default: table)"}])
def cmd_sparql_query(remaining: list[str], flags: dict[str, str]) -> dict:
    """Execute a SPARQL query and display results.

    The query can be provided as a positional argument or via the ``query=`` flag.

    Examples::

        !sparql query 'SELECT * WHERE { ?s ?p ?o } LIMIT 10'
        !sparql query --query 'ASK { ?s :hasAuthor ?o }'
    """
    engine = _ensure_engine()

    query = flags.get("query") or (remaining[0] if remaining else "")
    if not query:
        return {"type": "form-required", "title": "SPARQL Query", "data": {"form": "sparql-editor"}}

    try:
        result = engine.execute(query)
    except ValueError as exc:
        raise CommandValidationError(f"SPARQL query failed: {exc}")

    # Format the response
    if "results" in result:
        # SELECT
        bindings = result.get("results", {}).get("bindings", [])
        vars_list = result.get("head", {}).get("vars", [])
        count = len(bindings)
        if not bindings:
            return {"type": "status", "data": {"message": "SPARQL query returned no results."}}

        # Build table rows
        rows = []
        for b in bindings:
            row = {}
            for var in vars_list:
                entry = b.get(var, {})
                if isinstance(entry, dict):
                    label = entry.get("_label", "")
                    val = entry.get("value", "")
                    # Show label if available, otherwise value
                    display = label if label else val
                    if entry.get("type") == "uri":
                        display = f"{display} <{val}>" if label else val
                    row[var] = display
                else:
                    row[var] = str(entry)
            rows.append(row)
        return {"type": "table", "data": {"columns": list(vars_list), "rows": rows,
                                            "_summary": f"{count} result(s)"}}
    elif "boolean" in result:
        # ASK
        return {"type": "status", "data": {
            "message": "Yes" if result["boolean"] else "No",
        }}
    elif "data" in result:
        # CONSTRUCT/DESCRIBE
        ttl = result.get("data", "")
        preview = ttl[:500] + "..." if len(ttl) > 500 else ttl
        return {"type": "status", "data": {"message": "CONSTRUCT result", "ttl": preview}}
    return {"type": "status", "data": result}


@command("sparql.status", description="Show SPARQL engine status",
         permission_level=PermissionLevel.READ)
def cmd_sparql_status(remaining: list[str], flags: dict[str, str]) -> dict:
    """Show SPARQL engine status: backlog size, cache info."""
    try:
        engine = _ensure_engine()
    except CommandValidationError:
        return {"type": "status", "data": {
            "available": False,
            "message": "SPARQL engine not available (pyoxigraph not installed).",
        }}
    return {"type": "status", "data": {
        "available": True,
        "backlog_size": engine.backlog_size,
    }}


@command("sparql.update", description="Execute a SPARQL UPDATE query (experimental)",
         permission_level=PermissionLevel.WRITE,
         params=[{"name": "query", "type": "string", "required": True}])
def cmd_sparql_update(remaining: list[str], flags: dict[str, str]) -> dict:
    """Execute a SPARQL UPDATE query (INSERT DATA / DELETE DATA).

    **Experimental.**  The recommended way to modify data is through
    the existing ``!triple add/remove`` commands, which are also
    synced to the SPARQL cache.
    """
    # For now, redirect to the standard triple commands
    return {"type": "status", "data": {
        "message": (
            "SPARQL UPDATE is not yet implemented. "
            "Use !triple add or !triple remove to modify data. "
            "Changes are automatically synced to the SPARQL cache."
        ),
    }}
