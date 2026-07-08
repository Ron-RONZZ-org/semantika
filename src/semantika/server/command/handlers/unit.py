"""Command handlers for unit ontology commands."""

from __future__ import annotations

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command


@command("unit.list", description="List all units",
         permission_level=PermissionLevel.READ)
def cmd_unit_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all units in the ontology."""
    svc = get_services()
    from semantika.graph.unit_service import UnitService
    us = UnitService(svc["node"].db, svc["node"], svc["triple"])
    units = us.list_units()
    return {"type": "table", "data": units, "label": "Units"}


@command("unit.view", description="View unit info",
         permission_level=PermissionLevel.READ,
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_unit_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View detailed info for a unit by ID."""
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if remaining else "") or ""
    from semantika.graph.unit_service import UnitService
    us = UnitService(svc["node"].db, svc["node"], svc["triple"])
    info = us.get_unit_info(node_id)
    if not info:
        raise CommandValidationError(f"Unit not found: {node_id}")
    return {"type": "status", "data": info}


@command("unit.resolve", description="Resolve a unit expression",
         permission_level=PermissionLevel.READ,
         params=[{"name": "expr", "type": "string", "required": True}])
def cmd_unit_resolve(remaining: list[str], flags: dict[str, str]) -> dict:
    """Resolve a unit expression (e.g. 'm/s^2') to a unit node."""
    svc = get_services()
    expr = flags.get("expr") or (remaining[0] if remaining else "") or ""
    from semantika.graph.unit_service import UnitService
    us = UnitService(svc["node"].db, svc["node"], svc["triple"])
    nid = us.resolve_unit(expr)
    info = us.get_unit_info(nid)
    return {"type": "status", "data": {"resolved": nid, "info": info}}


@command("unit.decompose", description="Decompose a compound unit",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_unit_decompose(remaining: list[str], flags: dict[str, str]) -> dict:
    """Show the decomposition of a compound unit."""
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if remaining else "") or ""
    from semantika.graph.unit_service import UnitService
    us = UnitService(svc["node"].db, svc["node"], svc["triple"])
    info = us.get_unit_info(node_id)
    if not info:
        raise CommandValidationError(f"Unit not found: {node_id}")
    return {"type": "status", "data": {"decomposition": info.get("decomposition", "")}}


@command("unit.add", description="Create a new unit", interactive=True,
         params=[{"name": "node_id", "type": "string"},
                {"name": "labels", "type": "string"},
                {"name": "symbol", "type": "string"}])
def cmd_unit_add(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a new unit in the ontology."""
    svc = get_services()
    node_id = flags.get("node_id") or (remaining[0] if remaining else "") or ""
    labels = flags.get("labels") or (remaining[1] if len(remaining) > 1 else "") or ""
    symbol = flags.get("symbol") or (remaining[2] if len(remaining) > 2 else "") or ""
    from semantika.graph.unit_service import UnitService
    us = UnitService(svc["node"].db, svc["node"], svc["triple"])
    try:
        nid = us.create_singleton(node_id, labels, symbol)
        return {"type": "status", "data": {"message": f"Created unit {nid}"}}
    except ValueError as e:
        raise CommandValidationError(str(e))
