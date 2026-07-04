"""LLM integration routes — chat, completion, cowriting."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/chat")
async def chat():
    """Free-form conversation with the LLM, which may query the graph."""
    return {"reply": ""}


@router.post("/complete")
async def complete():
    """Inline completion / suggestion for the command bar."""
    return {"suggestions": []}
