"""Command handler for system-level operations (reindex, etc.)."""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_sparql_engine
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)


@command("system.reindex", description="Rebuild the SPARQL RocksDB cache from SQLite data",
         permission_level=PermissionLevel.DESTRUCTIVE,
         params=[],
         flags=[{"name": "confirmed", "type": "flag", "help": "Confirm reindex"}])
def cmd_system_reindex(remaining: list[str], flags: dict[str, str]) -> dict:
    """Clear the SPARQL cache and re-sync all triples from SQLite.

    Run after changing the ``node_iri`` / ``predicate_iri`` templates in
    ``semantika.jsonc`` to ensure the RocksDB store uses the new IRIs.

    Requires ``--confirmed`` to proceed.
    """
    confirmed = flags.get("confirmed", "").lower() in ("true", "1", "yes")
    if not confirmed:
        return {"type": "form-required", "title": "Confirm Reindex", "data": {
            "form": "confirm-reindex",
            "fields": [],
            "message": (
                "This will clear the SPARQL cache and re-sync all triples "
                "from SQLite.  This may take a while for large datasets.  "
                "Run again with --confirmed to proceed."
            ),
        }}

    engine = get_sparql_engine()
    if engine is None:
        return {"type": "status", "data": {"message": "SPARQL engine is not available."}}

    from semantika.core.config import reload_config

    reload_config()  # Pick up any template changes
    engine.clear_iri_cache()
    engine.clear_cache()
    count = engine.sync_all()

    return {"type": "status", "data": {
        "message": f"SPARQL cache rebuilt: {count} triples re-synced.",
    }}
