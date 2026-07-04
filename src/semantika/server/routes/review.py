"""Review API routes — spaced-repetition flashcard review."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from semantika.graph.db import get_services

router = APIRouter()


class AnswerRecord(BaseModel):
    result_uuid: str
    is_correct: bool


@router.post("/sessions")
async def start_session():
    """Start a new review session."""
    session = get_services()["review"].create_session()
    return session


@router.get("/sessions")
async def list_sessions(limit: int = 20):
    """List recent review sessions."""
    sessions = get_services()["review"].list_sessions(limit=limit)
    return {"sessions": sessions}


@router.get("/sessions/{session_uuid}")
async def get_session(session_uuid: str):
    """Get a review session with results."""
    svc = get_services()["review"]
    session = svc.get_session(session_uuid)
    if not session:
        raise HTTPException(404, f"Session not found: {session_uuid}")
    return session


@router.get("/sessions/{session_uuid}/next")
async def next_question(session_uuid: str):
    """Get the next unanswered question."""
    question = get_services()["review"].get_next_question(session_uuid)
    if not question:
        return {"done": True}
    return {"question": question, "done": False}


@router.post("/answer")
async def record_answer(data: AnswerRecord):
    """Record an answer for a review question."""
    result = get_services()["review"].record_answer(data.result_uuid, data.is_correct)
    return {"result": result}


@router.delete("/sessions/{session_uuid}")
async def delete_session(session_uuid: str):
    """Delete a review session."""
    get_services()["review"].delete_session(session_uuid)
    return {"deleted": True}
