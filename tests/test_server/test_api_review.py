"""Tests for review session API routes — /api/v1/review/*.

Covers starting sessions, CRUD, quiz mode, date filters, next question,
and review commands via the dispatch system.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Must override data dir before importing app
TEST_DATA_DIR = Path("/tmp/semantika-review-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Review via command ─────────────────────────────────────────────────


class TestReviewAPI:
    """Test the review endpoints."""

    def test_review_start(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["review", "start"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"


# ── Review session CRUD ────────────────────────────────────────────────


class TestReviewSessionAPI:
    """Test review session CRUD beyond just starting."""

    def test_start_and_get_session(self, client: TestClient):
        # Create with default mode
        resp = client.post("/api/v1/review/sessions", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        session_uuid = data["session"]["uuid"]
        assert session_uuid

        # Get by UUID
        resp = client.get(f"/api/v1/review/sessions/{session_uuid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        assert data["session"]["uuid"] == session_uuid

    def test_delete_session(self, client: TestClient):
        resp = client.post("/api/v1/review/sessions", json={})
        assert resp.status_code == 200
        session_uuid = resp.json()["session"]["uuid"]

        resp = client.delete(f"/api/v1/review/sessions/{session_uuid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_next_question(self, client: TestClient):
        # Need a triple for questions to exist
        resp = client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "SUBJ1", "predicate_id": "ex:testPred1", "object_value": "OBJ1", "object_type": "uri"},
        )
        # may be duplicate - that's OK
        resp = client.post("/api/v1/review/sessions", json={"mode": "view", "limit": 10})
        assert resp.status_code == 200
        session_uuid = resp.json()["session"]["uuid"]

        resp = client.get(f"/api/v1/review/sessions/{session_uuid}/next")
        assert resp.status_code == 200


# ── Review modes and filters ───────────────────────────────────────────


class TestReviewModes:
    """Test review quiz mode with distractor generation."""

    def test_quiz_mode(self, client: TestClient):
        """Start a quiz-mode review session."""
        # Ensure at least one triple exists
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "Q_SUBJ", "labels": {"en": "Quiz Subject"}},
        )
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "Q_OBJ", "labels": {"en": "Quiz Object"}},
        )
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:quizPred", "labels": {"en": "quiz predicate"}},
        )
        client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "Q_SUBJ", "predicate_id": "ex:quizPred",
                "object_value": "Q_OBJ", "object_type": "uri",
            },
        )

        resp = client.post(
            "/api/v1/review/sessions",
            json={"mode": "quiz", "limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        assert data["session"]["mode"] == "quiz"

        # Check next question has options (quiz mode)
        sess_uuid = data["session"]["uuid"]
        q_resp = client.get(f"/api/v1/review/sessions/{sess_uuid}/next")
        assert q_resp.status_code == 200
        q_data = q_resp.json()
        if not q_data.get("done"):
            assert "options" in q_data["question"]

    def test_date_filter(self, client: TestClient):
        """Start a review session with date filter."""
        resp = client.post(
            "/api/v1/review/sessions",
            json={"mode": "view", "date_from": "2020-01-01", "limit": 5},
        )
        assert resp.status_code == 200


# ── Review commands via dispatch ───────────────────────────────────────


class TestReviewCommands:
    """Test !review view and !review delete commands (Tier 3f)."""

    def test_review_sessions_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["review", "sessions"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "table"

    def test_review_view_and_delete_via_command(self, client: TestClient):
        """View and delete a review session via !command."""
        sess_resp = client.post("/api/v1/review/sessions", json={})
        assert sess_resp.status_code == 200
        session_uuid = sess_resp.json()["session"]["uuid"]

        # View via command
        v_resp = client.post(
            "/api/v1/command",
            json={"tokens": ["review", "view"], "flags": {"uuid": session_uuid}},
        )
        assert v_resp.status_code == 200

        # Delete via command
        d_resp = client.post(
            "/api/v1/command",
            json={"tokens": ["review", "delete"], "flags": {"uuid": session_uuid}},
        )
        assert d_resp.status_code == 200
        assert "Deleted" in str(d_resp.json())


# ── Edge cases ─────────────────────────────────────────────────────────


class TestReviewEdgeCases:
    """Review-specific edge cases."""

    def test_review_start_invalid_mode(self, client: TestClient):
        """Review with invalid mode returns 400."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["review", "start"], "flags": {"mode": "invalid_mode"}},
        )
        assert resp.status_code == 400
