"""Review API routes — interactive triple review with view and quiz modes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from semantika.graph.db import get_services

router = APIRouter()


class StartSessionRequest(BaseModel):
    mode: str = "view"
    date_from: str | None = None
    date_to: str | None = None
    limit: int = 50


class AnswerRecord(BaseModel):
    result_uuid: str
    is_correct: bool
    response: str | None = None


@router.post("/sessions")
def start_session(req: StartSessionRequest):
    """Start a new review session.

    *mode* is ``'view'`` (show SPO, confirm) or ``'quiz'`` (multiple choice).
    Optional *date_from*/*date_to* filter triples by creation date.
    """
    if req.mode not in ("view", "quiz"):
        raise HTTPException(400, f"Invalid mode: {req.mode}. Use 'view' or 'quiz'.")
    session = get_services()["review"].create_session(
        mode=req.mode,
        date_from=req.date_from,
        date_to=req.date_to,
        limit=req.limit,
    )
    return session


@router.get("/sessions")
def list_sessions(limit: int = 20):
    """List recent review sessions."""
    sessions = get_services()["review"].list_sessions(limit=limit)
    return {"sessions": sessions}


@router.get("/sessions/{session_uuid}")
def get_session(session_uuid: str, enrich: bool = False):
    """Get a review session with results.

    If *enrich=true*, each result includes resolved labels.
    """
    svc = get_services()["review"]
    session = svc.get_session(session_uuid, enrich=enrich)
    if not session:
        raise HTTPException(404, f"Session not found: {session_uuid}")
    return {"session": session}


@router.get("/sessions/{session_uuid}/next")
def next_question(session_uuid: str):
    """Get the next unanswered question.

    Returns labels and, for quiz mode, shuffled multiple-choice *options*.
    """
    question = get_services()["review"].get_next_question(session_uuid)
    if not question:
        return {"done": True}
    return {"question": question, "done": False}


@router.post("/answer")
def record_answer(data: AnswerRecord):
    """Record an answer for a review question.

    Optionally store the user's *response* text (e.g. their chosen option
    or 'yes'/'no' for view mode).
    """
    result = get_services()["review"].record_answer(
        data.result_uuid,
        data.is_correct,
        response=data.response,
    )
    return {"result": result}


@router.delete("/sessions/{session_uuid}")
def delete_session(session_uuid: str):
    """Delete a review session."""
    get_services()["review"].delete_session(session_uuid)
    return {"deleted": True}
