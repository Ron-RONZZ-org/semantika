"""Unit API routes — unit CRUD and expression resolution."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from semantika.graph.db import get_services

router = APIRouter()


def _unit_svc() -> Any:
    """Get UnitService from service singletons."""
    svc = get_services()
    from semantika.graph.unit_service import UnitService
    return UnitService(
        db=svc["node"].db,
        node_svc=svc["node"],
        triple_svc=svc["triple"],
    )


class UnitCreate(BaseModel):
    node_id: str
    label: str = ""
    symbol: str = ""


@router.get("/units")
async def list_units():
    """List all unit nodes."""
    units = _unit_svc().list_units()
    return {"units": units}


@router.get("/units/{node_id}")
async def get_unit(node_id: str):
    """Get detailed info for a unit."""
    info = _unit_svc().get_unit_info(node_id)
    if not info:
        raise HTTPException(404, f"Unit not found: {node_id}")
    return {"unit": info}


@router.post("/units")
async def create_unit(data: UnitCreate):
    """Create a custom singular unit."""
    us = _unit_svc()
    try:
        node_id = us.create_singleton(data.node_id, data.label, data.symbol)
        return {"unit": us.get_unit_info(node_id)}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/units/resolve")
async def resolve_unit(expr: str):
    """Resolve a unit expression to a node_id."""
    us = _unit_svc()
    try:
        node_id = us.resolve_unit(expr)
        return {"node_id": node_id, "info": us.get_unit_info(node_id)}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/units/decompose")
async def decompose_unit(node_id: str):
    """Get human-readable decomposition for a compound unit."""
    us = _unit_svc()
    info = us.get_unit_info(node_id)
    if not info:
        raise HTTPException(404, f"Unit not found: {node_id}")
    return {"decomposition": info.get("decomposition", "")}
