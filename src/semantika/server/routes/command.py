"""Command bar API — handles !command parsing and dispatch."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/tree")
async def command_tree():
    """Return the command tree metadata for autocomplete."""
    return {"commands": []}


@router.post("/execute")
async def execute_command():
    """Parse and execute a !command."""
    return {"result": {}, "type": "status"}
