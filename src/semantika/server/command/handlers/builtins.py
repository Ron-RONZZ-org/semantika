"""Command handler for built-in ontology management (``!builtins``).

Provides a ``!builtins reload`` command to re-read the YAML seed files
(``builtins.yaml``, ``units.yaml``) and re-seed the ontology without
restarting the server.
"""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.builtin_loader import invalidate_caches
from semantika.graph.db import get_services
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)


@command("builtins.reload",
         description="Re-read YAML seed files and re-seed built-in ontology",
         permission_level=PermissionLevel.SYSTEM,
         params=[],
         flags=[
             {"name": "quiet", "type": "flag",
              "help": "Suppress status output"},
         ])
def cmd_builtins_reload(remaining: list[str], flags: dict[str, str]) -> dict:
    """Re-read ``builtins.yaml`` and ``units.yaml`` and re-seed the database.

    Uses ``INSERT OR IGNORE`` so:
    - New entries from YAML are seeded
    - Existing entries are never overwritten
    - User-created data is never touched

    Run this after editing ``~/.config/semantika/builtins.yaml`` or
    ``~/.config/semantika/units.yaml`` to apply changes without a
    server restart.

    Warnings:
        If a predicate required by built-in commands is missing from the
        YAML file, the system falls back to hardcoded Python defaults and
        logs a warning.  Check the server log for such warnings.
    """
    svc = get_services()

    # Invalidate all caches so the YAML is re-read
    invalidate_caches()

    # Re-seed builtins (predicates + type nodes)
    builtin_svc = svc["builtin_type"]
    counts = builtin_svc.reload()

    # Re-seed units
    unit_svc = svc.get("unit")
    unit_count = 0
    if unit_svc is not None and hasattr(unit_svc, "reload_units"):
        unit_count = unit_svc.reload_units()

    quiet = "quiet" in flags or flags.get("quiet", "").lower() in ("true", "1", "yes")
    if quiet:
        return {"type": "status", "data": {"message": "Builtins reloaded."}}

    return {"type": "status", "data": {
        "message": (
            f"Builtins reloaded: {counts.get('predicates', 0)} predicates, "
            f"{counts.get('type_nodes', 0)} type nodes, "
            f"{unit_count} unit entries from YAML."
        ),
    }}
