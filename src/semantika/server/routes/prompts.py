"""API routes for prompt file management (``!llm prompt`` GUI backend).

Uses query params for ``name`` instead of path params because names like
``template/turn1`` contain slashes that break FastAPI path matching.

Endpoints:
- GET  /api/v1/llm/prompts/list          — list all prompt files with diff status
- GET  /api/v1/llm/prompts/view?name=…   — view a specific prompt file
- POST /api/v1/llm/prompts/reset          — reset a prompt to default
- POST /api/v1/llm/prompts/save           — save edited content
- GET  /api/v1/llm/prompts/modified-count — count of modified prompts (for banner)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from semantika.server.llm.prompt_defaults import get_prompt_files_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/llm/prompts", tags=["prompts"])


@router.get("/list")
async def list_prompts_endpoint() -> list[dict[str, Any]]:
    """Return all prompt files with metadata and modification status."""
    mgr = get_prompt_files_manager()
    return mgr.list_all()


@router.get("/modified-count")
async def modified_count_endpoint() -> dict[str, Any]:
    """Return the count of modified prompt files.

    Used by the frontend to decide whether to show the banner.
    """
    mgr = get_prompt_files_manager()
    return {
        "modified_count": mgr.modified_count(),
        "total": len(mgr.list_all()),
    }


@router.get("/view")
async def view_prompt_endpoint(name: str) -> dict[str, Any]:
    """Return the current and default content for a prompt file.

    Query param: ``name`` — logical prompt name (e.g. ``system-prompt``,
    ``template/turn1``).
    """
    if not name:
        raise HTTPException(status_code=400, detail="'name' query parameter is required.")

    mgr = get_prompt_files_manager()

    default_content = mgr.get_default(name)
    if default_content is None:
        all_entries = mgr.list_all()
        known = [e["name"] for e in all_entries]
        raise HTTPException(
            status_code=404,
            detail=f"Unknown prompt '{name}'. Available: {', '.join(known)}",
        )

    entry = next((e for e in mgr.list_all() if e["name"] == name), {})
    content = mgr.get_content(name)

    return {
        "name": name,
        "relative_path": entry.get("relative_path", ""),
        "category": entry.get("category", ""),
        "current": content or "",
        "default": default_content,
        "exists": entry.get("exists", False),
        "is_modified": entry.get("is_modified", False),
    }


@router.post("/reset")
async def reset_prompt_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Reset a prompt file to its shipped default.

    Expects ``{"name": "..."}`` in the request body.
    """
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="'name' is required in request body.")

    mgr = get_prompt_files_manager()

    default_content = mgr.get_default(name)
    if default_content is None:
        all_entries = mgr.list_all()
        known = [e["name"] for e in all_entries]
        raise HTTPException(
            status_code=404,
            detail=f"Unknown prompt '{name}'. Available: {', '.join(known)}",
        )

    result = mgr.reset(name)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset prompt '{name}' — check file permissions.",
        )

    return {
        "message": f"Prompt '{name}' reset to default",
        "name": name,
    }


@router.post("/save")
async def save_prompt_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Save edited prompt file content.

    Expects ``{"name": "...", "content": "..."}``.
    """
    name = (data.get("name") or "").strip()
    content = (data.get("content") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="'name' is required in request body.")
    if not content:
        raise HTTPException(status_code=400, detail="'content' is required.")

    mgr = get_prompt_files_manager()

    default_content = mgr.get_default(name)
    if default_content is None:
        all_entries = mgr.list_all()
        known = [e["name"] for e in all_entries]
        raise HTTPException(
            status_code=404,
            detail=f"Unknown prompt '{name}'. Available: {', '.join(known)}",
        )

    success = mgr.save(name, content)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save prompt '{name}' — check file permissions.",
        )

    return {
        "message": f"Prompt '{name}' saved",
        "name": name,
        "is_modified": next(
            (e["is_modified"] for e in mgr.list_all() if e["name"] == name),
            False,
        ),
    }
