"""Tests for ReviewService — review sessions, answering, distractors."""

from __future__ import annotations


class TestReviewService:
    def test_create_session(self, services: dict):
        # Need at least one triple for a session
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        ns.create({"node_id": "X", "labels": {"en": "X"}})
        ps.create({"predicate_id": "ex:p", "labels": {"en": "p"}})
        # No triple referencing X as object — create with URI pointing to self
        ts.add("X", "ex:p", "X", object_type="node")

        rs = services["review"]
        session = rs.create_session()
        assert "session" in session

    def test_create_session_with_date_filter(self, services: dict):
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        ns.create({"node_id": "Y", "labels": {"en": "Y"}})
        ps.create({"predicate_id": "ex:q", "labels": {"en": "q"}})
        ts.add("Y", "ex:q", "Y", object_type="node")

        rs = services["review"]
        session = rs.create_session(date_from="2020-01-01", date_to="2020-12-31")
        assert "session" in session

    def test_list_sessions_empty(self, services: dict):
        sessions = services["review"].list_sessions()
        assert isinstance(sessions, list)

    def test_get_session_nonexistent(self, services: dict):
        result = services["review"].get_session("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_delete_session_nonexistent(self, services: dict):
        """Deleting a nonexistent session should not raise."""
        services["review"].delete_session("00000000-0000-0000-0000-000000000000")

    def test_answer_review(self, services: dict):
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        rs = services["review"]
        ns.create({"node_id": "QA", "labels": {"en": "Q"}})
        ps.create({"predicate_id": "ex:pa", "labels": {"en": "pa"}})
        ts.add("QA", "ex:pa", "QA", object_type="node")

        session = rs.create_session()
        session_uuid = session["session"]["uuid"]
        # Get first result from the session
        results = session.get("results", [])
        if results:
            result_uuid = results[0]["uuid"]
            result = rs.answer_review(result_uuid, is_correct=True, response="test answer")
            assert result is not None
            if result:
                assert "uuid" in result

    def test_generate_distractors(self, services: dict):
        ns = services["node"]
        rs = services["review"]
        ns.create({"node_id": "CORRECT", "labels": {"en": "Correct answer"}})
        ns.create({"node_id": "D1", "labels": {"en": "Distractor one"}})
        ns.create({"node_id": "D2", "labels": {"en": "Distractor two"}})
        distractors = rs._generate_distractors("CORRECT", correct_type="node", count=2)
        assert len(distractors) <= 2
        assert "CORRECT" not in distractors

    def test_extract_first_label(self, services: dict):
        rs = services["review"]
        label = rs._extract_first_label('{"en": "Hello"}')
        assert label == "Hello"

    def test_extract_first_label_invalid_json(self, services: dict):
        rs = services["review"]
        label = rs._extract_first_label("not-json")
        assert label == ""

    def test_extract_first_label_invalid_type(self, services: dict):
        rs = services["review"]
        label = rs._extract_first_label(12345)
        assert label == ""

    def test_extract_first_label_empty_string(self, services: dict):
        rs = services["review"]
        label = rs._extract_first_label("")
        assert label == ""
