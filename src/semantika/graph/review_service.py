"""ReviewService — interactive triple review with view and quiz modes.

Ported from A-semantika's ``_reczeni_helpers.py`` and ``_recenzi_cmd.py``.

Two modes:
  - **view**: show subject-predicate-object, ask "Correct? [Y/n]"
  - **quiz**: show subject-predicate, pick correct object from 4 options
    (distractors auto-generated via FTS5 label similarity / LIKE on literals)
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
import uuid as _uuid

from semantika.core import SemantikaDB
from semantika.core.crud import now

logger = logging.getLogger(__name__)


class ReviewService:
    """Service for reviewing triples with view and quiz modes."""

    def __init__(self, db: SemantikaDB) -> None:
        self.db = db

    # ── Session creation ────────────────────────────────────────────────

    def create_session(
        self,
        mode: str = "view",
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Create a new review session, pre-populated with triples.

        Args:
            mode: ``'view'`` (show SPO, confirm) or ``'quiz'`` (multiple choice).
            date_from: Optional ISO date — only triple from this date onward.
            date_to: Optional ISO date — only triples up to this date.
            limit: Max number of questions.

        Returns:
            Dict with ``session`` and ``resumed`` flag.
        """
        ts = now()
        session_uuid = str(_uuid.uuid4())
        self.db.execute(
            "INSERT INTO review_sessions "
            "(uuid, mode, date_from, date_to, created_at, total, correct, finished) "
            "VALUES (?, ?, ?, ?, ?, 0, 0, 0)",
            (session_uuid, mode, date_from, date_to, ts),
        )

        # Fetch triples within date range
        clauses: list[str] = ["1=1"]
        params: list = []
        if date_from:
            clauses.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("created_at <= ?")
            params.append(date_to)

        _max_fetch = 10000  # prevent OOM on very large graphs
        fetch_limit = min(limit * 3, _max_fetch)
        triples = self.db.execute(
            f"SELECT * FROM triples WHERE {' AND '.join(clauses)} "
            f"ORDER BY subject_id LIMIT ?",
            (*params, fetch_limit),
        )
        random.shuffle(triples)
        triples = triples[:limit]

        total = len(triples)
        self.db.execute(
            "UPDATE review_sessions SET total = ? WHERE uuid = ?",
            (total, session_uuid),
        )

        for i, t in enumerate(triples):
            result_uuid = str(_uuid.uuid4())
            self.db.execute(
                "INSERT INTO review_results "
                "(uuid, session_uuid, subject_id, predicate_id, object_value, "
                "object_type, is_correct, response, position, answered_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, '')",
                (result_uuid, session_uuid,
                 t["subject_id"], t["predicate_id"],
                 t["object_value"], t["object_type"],
                 i + 1),
            )

        return {"session": self._get_session(session_uuid, enrich=False), "resumed": False}

    # ── Session queries ────────────────────────────────────────────────

    def get_session(self, session_uuid: str, enrich: bool = False) -> dict | None:
        """Get a session with results, optionally with resolved labels."""
        try:
            return self._get_session(session_uuid, enrich=enrich)
        except ValueError:
            return None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """List past review sessions, most recent first."""
        return self.db.execute(
            "SELECT * FROM review_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    def delete_session(self, session_uuid: str) -> bool:
        """Delete a session and its results."""
        self.db.execute(
            "DELETE FROM review_results WHERE session_uuid = ?", (session_uuid,)
        )
        self.db.execute(
            "DELETE FROM review_sessions WHERE uuid = ?", (session_uuid,)
        )
        return True

    # ── Questions / answers ────────────────────────────────────────────

    def get_next_question(self, session_uuid: str) -> dict | None:
        """Get the next unanswered question, with labels and optional distractors."""
        result = self.db.execute_one(
            "SELECT r.*, s.mode FROM review_results r "
            "JOIN review_sessions s ON r.session_uuid = s.uuid "
            "WHERE r.session_uuid = ? AND r.answered_at = '' "
            "ORDER BY r.position LIMIT 1",
            (session_uuid,),
        )
        if not result:
            return None

        question = dict(result)
        question["subject_label"] = self._resolve_label("nodes", result["subject_id"])
        question["predicate_label"] = self._resolve_label("predicates", result["predicate_id"])
        question["object_label"] = self._resolve_object_label(result)

        # Quiz mode: generate distractors
        if result["mode"] == "quiz":
            distractors = self._generate_distractors(
                result["object_value"],
                result["object_type"],
                count=3,
            )
            options = [result["object_value"], *distractors]
            random.shuffle(options)
            question["options"] = options

        return question

    def record_answer(
        self,
        result_uuid: str,
        is_correct: bool,
        response: str | None = None,
    ) -> dict:
        """Record an answer for a review question."""
        self.db.execute(
            "UPDATE review_results SET is_correct = ?, response = ?, answered_at = ? "
            "WHERE uuid = ?",
            (1 if is_correct else 0, response, now(), result_uuid),
        )
        result = self.db.execute_one(
            "SELECT * FROM review_results WHERE uuid = ?", (result_uuid,)
        )

        # Update session totals
        if result:
            session_uuid = result["session_uuid"]
            stats = self.db.execute_one(
                "SELECT COUNT(*) AS total, COALESCE(SUM(is_correct), 0) AS correct "
                "FROM review_results WHERE session_uuid = ?",
                (session_uuid,),
            )
            if stats:
                all_answered = self.db.execute_one(
                    "SELECT COUNT(*) AS cnt FROM review_results "
                    "WHERE session_uuid = ? AND answered_at = ''",
                    (session_uuid,),
                )
                finished = 1 if (all_answered and all_answered["cnt"] == 0) else 0
                self.db.execute(
                    "UPDATE review_sessions SET total = ?, correct = ?, finished = ? "
                    "WHERE uuid = ?",
                    (stats["total"], stats["correct"], finished, session_uuid),
                )

        return dict(result) if result else {}

    # ── Distractor generation ──────────────────────────────────────────

    def _generate_distractors(
        self,
        correct_value: str,
        correct_type: str,
        count: int = 3,
    ) -> list[str]:
        """Generate wrong-answer options for quiz mode.

        For URI objects: finds other nodes with similar labels via FTS5.
        For literal objects: finds other literal values via LIKE.
        """
        distractors: list[str] = []

        if correct_type == "uri":
            node = self.db.execute_one(
                "SELECT labels FROM nodes WHERE node_id = ?", (correct_value,)
            )
            if node:
                label_text = self._extract_first_label(node["labels"])
                if label_text and len(label_text) >= 2:
                    try:
                        related = self.db.execute(
                            "SELECT n.node_id FROM nodes n "
                            "JOIN nodes_fts f ON n.node_id = f.node_id "
                            "WHERE nodes_fts MATCH ? AND n.node_id != ? "
                            "LIMIT ?",
                            (f"{self._fts_escape(label_text)}*", correct_value, count + 5),
                        )
                        for r in related:
                            if r["node_id"] not in distractors:
                                distractors.append(r["node_id"])
                            if len(distractors) >= count:
                                break
                    except sqlite3.DatabaseError:
                        logger.debug(
                            "FTS query failed for distractor generation (correct=%s), "
                            "falling back to LIKE",
                            correct_value,
                        )
        else:
            if len(correct_value) >= 2:
                escaped = correct_value[:10].replace(
                    "\\", "\\\\"
                ).replace("%", "\\%").replace("_", "\\_")
                similar = self.db.execute(
                    "SELECT object_value FROM triples "
                    "WHERE object_type = 'literal' AND object_value LIKE ? "
                    "AND object_value != ? LIMIT ?",
                    (f"%{escaped}%", correct_value, count + 5),
                )
                for t in similar:
                    if t["object_value"] not in distractors:
                        distractors.append(t["object_value"])
                    if len(distractors) >= count:
                        break

        return distractors[:count]

    # ── Internal helpers ───────────────────────────────────────────────

    def _get_session(self, session_uuid: str, enrich: bool = False) -> dict:
        """Get a session dict with its results."""
        session = self.db.execute_one(
            "SELECT * FROM review_sessions WHERE uuid = ?", (session_uuid,)
        )
        if not session:
            raise ValueError(f"Session not found: {session_uuid}")

        results = self.db.execute(
            "SELECT * FROM review_results WHERE session_uuid = ? "
            "ORDER BY position",
            (session_uuid,),
        )
        session = dict(session)
        session["results"] = results

        if enrich:
            for r in session["results"]:
                r["subject_label"] = self._resolve_label("nodes", r["subject_id"])
                r["predicate_label"] = self._resolve_label("predicates", r["predicate_id"])
                r["object_label"] = self._resolve_object_label(r)

        return session

    _LABEL_TABLES: dict[str, tuple[str, str]] = {
        "nodes": ("node_id", "labels"),
        "predicates": ("predicate_id", "labels"),
    }

    def _resolve_label(self, table: str, pk: str) -> str:
        """Resolve a display label from nodes or predicates table."""
        lookup = self._LABEL_TABLES.get(table)
        if lookup is None:
            return pk
        pk_col, label_col = lookup
        row = self.db.execute_one(
            f"SELECT {label_col} FROM {table} WHERE {pk_col} = ?",
            (pk,),
        )
        if row:
            return self._extract_first_label(row[label_col]) or pk
        return pk

    def _resolve_object_label(self, result: dict) -> str:
        """Get display label for a triple's object."""
        if result["object_type"] == "uri":
            return self._resolve_label("nodes", result["object_value"])
        return result["object_value"]

    def _extract_first_label(self, json_str: str) -> str:
        """Extract first non-empty value from a JSON labels dict."""
        try:
            labels = json.loads(json_str) if isinstance(json_str, str) else json_str
            if isinstance(labels, dict):
                for val in labels.values():
                    if val and isinstance(val, str):
                        return val
        except (json.JSONDecodeError, TypeError):
            pass
        return ""

    @staticmethod
    def _fts_escape(text: str) -> str:
        """Escape text for FTS5 prefix query, handling special chars."""
        cleaned = "".join(c for c in text if c.isalnum() or c in " _-")
        return cleaned.strip()[:50]
