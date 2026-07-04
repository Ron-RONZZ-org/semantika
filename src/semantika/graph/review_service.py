"""ReviewService — spaced-repetition flashcard review of triples.

Ported from A-semantika's ``_reczeni_helpers.py`` and ``_recenzi_cmd.py``.
"""

from __future__ import annotations

import random
import uuid as _uuid
from typing import Any

from semantika.core import SemantikaDB
from semantika.core.crud import now


class ReviewService:
    """Service for reviewing triples via spaced repetition (flashcard mode)."""

    def __init__(self, db: SemantikaDB) -> None:
        self.db = db

    # ── Session management ─────────────────────────────────────────────

    def create_session(self) -> dict:
        """Create a new review session, pre-populated with triples."""
        sessions = self.db.execute("SELECT uuid FROM review_sessions")
        # Unfinished session? Return it
        for s in sessions:
            results = self.db.execute(
                "SELECT COUNT(*) AS cnt FROM review_results WHERE session_uuid = ?",
                (s["uuid"],),
            )
            if results and results[0]["cnt"] == 0:
                return {"session": self._get_session(s["uuid"]), "resumed": True}

        session = {
            "uuid": str(_uuid.uuid4()),
            "created_at": now(),
            "total": 0,
            "correct": 0,
        }
        self.db.execute(
            "INSERT INTO review_sessions (uuid, created_at, total, correct) "
            "VALUES (:uuid, :created_at, :total, :correct)",
            session,
        )

        # Get all triples for this session
        triples = self.db.execute(
            "SELECT subject_id, predicate_id, object_value, object_type "
            "FROM triples ORDER BY RANDOM() LIMIT 50"
        )
        session["total"] = len(triples)
        self.db.execute(
            "UPDATE review_sessions SET total = ? WHERE uuid = ?",
            (len(triples), session["uuid"]),
        )

        for t in triples:
            result = {
                "uuid": str(_uuid.uuid4()),
                "session_uuid": session["uuid"],
                "subject_id": t["subject_id"],
                "predicate_id": t["predicate_id"],
                "object_value": t["object_value"],
                "object_type": t["object_type"],
                "is_correct": 0,
                "answered_at": "",
            }
            self.db.execute(
                "INSERT INTO review_results (uuid, session_uuid, subject_id, "
                "predicate_id, object_value, object_type, is_correct, answered_at) "
                "VALUES (:uuid, :session_uuid, :subject_id, :predicate_id, "
                ":object_value, :object_type, :is_correct, :answered_at)",
                result,
            )

        return {"session": self._get_session(session["uuid"]), "resumed": False}

    def _get_session(self, session_uuid: str) -> dict:
        """Get session with its results."""
        session = self.db.execute_one(
            "SELECT * FROM review_sessions WHERE uuid = ?", (session_uuid,)
        )
        if not session:
            raise ValueError(f"Session not found: {session_uuid}")
        results = self.db.execute(
            "SELECT * FROM review_results WHERE session_uuid = ? ORDER BY rowid",
            (session_uuid,),
        )
        session = dict(session)
        session["results"] = results
        return session

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """List recent review sessions."""
        return self.db.execute(
            "SELECT * FROM review_sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        )

    def get_session(self, session_uuid: str) -> dict | None:
        """Get a session with results."""
        try:
            return self._get_session(session_uuid)
        except ValueError:
            return None

    def delete_session(self, session_uuid: str) -> bool:
        """Delete a session and its results."""
        self.db.execute(
            "DELETE FROM review_results WHERE session_uuid = ?", (session_uuid,)
        )
        self.db.execute(
            "DELETE FROM review_sessions WHERE uuid = ?", (session_uuid,)
        )
        return True

    def record_answer(self, result_uuid: str, is_correct: bool) -> dict:
        """Record an answer for a review question."""
        self.db.execute(
            "UPDATE review_results SET is_correct = ?, answered_at = ? WHERE uuid = ?",
            (1 if is_correct else 0, now(), result_uuid),
        )
        result = self.db.execute_one(
            "SELECT * FROM review_results WHERE uuid = ?", (result_uuid,)
        )

        # Update session totals
        if result:
            session_uuid = result["session_uuid"]
            stats = self.db.execute_one(
                "SELECT COUNT(*) AS total, SUM(is_correct) AS correct "
                "FROM review_results WHERE session_uuid = ?",
                (session_uuid,),
            )
            if stats:
                self.db.execute(
                    "UPDATE review_sessions SET total = ?, correct = ? WHERE uuid = ?",
                    (stats["total"] or 0, stats["correct"] or 0, session_uuid),
                )

        return dict(result) if result else {}

    def get_next_question(self, session_uuid: str) -> dict | None:
        """Get the next unanswered question in a session."""
        result = self.db.execute_one(
            "SELECT * FROM review_results WHERE session_uuid = ? "
            "AND answered_at = '' ORDER BY rowid LIMIT 1",
            (session_uuid,),
        )
        if not result:
            return None

        question = dict(result)
        # Get display labels
        node = self.db.execute_one(
            "SELECT labels FROM nodes WHERE node_id = ?", (result["subject_id"],)
        )
        if node:
            question["subject_label"] = self._label_from_json(node["labels"], result["subject_id"])

        pred = self.db.execute_one(
            "SELECT labels FROM predicates WHERE predicate_id = ?",
            (result["predicate_id"],),
        )
        if pred:
            question["predicate_label"] = self._label_from_json(pred["labels"], result["predicate_id"])

        return question

    def _label_from_json(self, json_str: str, fallback: str) -> str:
        """Extract a display label from a JSON labels dict."""
        import json
        try:
            labels = json.loads(json_str) if isinstance(json_str, str) else json_str
            if isinstance(labels, dict):
                for val in labels.values():
                    if val and isinstance(val, str):
                        return val
        except (json.JSONDecodeError, TypeError):
            pass
        return fallback
