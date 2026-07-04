"""Query API routes — natural-language and structured query."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/ask")
async def ask_llm():
    """Natural language query over the knowledge graph."""
    return {"answer": "", "triples": []}


@router.get("/search")
async def search():
    """Full-text search across nodes and triples."""
    return {"results": []}


@router.get("/export")
async def export():
    """Export graph in Turtle/JSON format."""
    return {"data": ""}
