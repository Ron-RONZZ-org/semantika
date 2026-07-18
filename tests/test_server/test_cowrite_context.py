"""Tests for server/cowrite/context.py — writing samples context gathering."""

from __future__ import annotations

import json

import pytest

from semantika.server.cowrite.context import gather_context, _recent_samples_only


class _MockDB:
    """A minimal mock DB that returns preset query results."""

    def __init__(self, rows=None):
        self._rows = rows or []

    def execute(self, sql, params=None):
        class MockCursor:
            def __init__(self, rows):
                self._rows = rows
            def __iter__(self):
                return iter(self._rows)

        return MockCursor(self._rows)


class TestGatherContext:
    """Test the gather_context() function."""

    def test_returns_empty_dict_when_no_samples(self, monkeypatch):
        """No writing samples in DB → empty dict."""
        monkeypatch.setattr("semantika.graph.db.get_db", lambda: _MockDB([]))
        result = gather_context("node-add-concept", {"label": "Test"})
        assert result == {}

    def test_returns_recent_samples(self, monkeypatch):
        """With samples in DB, returns samples."""
        monkeypatch.setattr("semantika.graph.db.get_db", lambda: _MockDB([
            {"uuid": "s1", "form_type": "node-add-concept", "instruction": "improve",
             "original": json.dumps({"label": "Old"}), "revised": json.dumps({"label": "New"}),
             "word_count": 2, "source_domain": "semantika", "created_at": "2026-01-01T00:00:00"},
        ]))
        result = gather_context("node-add-concept", {"label": "Test"})
        assert "writing_samples" in result
        assert len(result["writing_samples"]) == 1
        assert result["writing_samples"][0]["uuid"] == "s1"

    def test_returns_empty_when_no_text_in_fields(self, monkeypatch):
        """No text values in fields → skip context gathering."""
        monkeypatch.setattr("semantika.graph.db.get_db", lambda: _MockDB())
        result = gather_context("node-add-concept", {"label": "", "def": "  "})
        assert result == {}

    def test_returns_multiple_samples_ordered_by_date(self, monkeypatch):
        """Multiple samples returned in reverse chronological order."""
        monkeypatch.setattr("semantika.graph.db.get_db", lambda: _MockDB([
            {"uuid": "s2", "form_type": "node-add-concept", "instruction": "edit",
             "original": json.dumps({"label": "Old 2"}), "revised": json.dumps({"label": "New 2"}),
             "word_count": 2, "source_domain": "semantika", "created_at": "2026-01-03T00:00:00"},
            {"uuid": "s1", "form_type": "node-add-concept", "instruction": "edit",
             "original": json.dumps({"label": "Old 1"}), "revised": json.dumps({"label": "New 1"}),
             "word_count": 2, "source_domain": "semantika", "created_at": "2026-01-02T00:00:00"},
            {"uuid": "s0", "form_type": "node-add-concept", "instruction": "edit",
             "original": json.dumps({"label": "Old 0"}), "revised": json.dumps({"label": "New 0"}),
             "word_count": 2, "source_domain": "semantika", "created_at": "2026-01-01T00:00:00"},
        ]))
        result = gather_context("node-add-concept", {"label": "Test"})
        assert len(result["writing_samples"]) == 3
        originals = [s["original"]["label"] for s in result["writing_samples"]]
        assert originals == ["Old 2", "Old 1", "Old 0"]

    def test_handles_db_error_gracefully(self, monkeypatch):
        """DB access error → returns empty dict."""
        def _broken_db():
            raise RuntimeError("DB unavailable")
        monkeypatch.setattr("semantika.graph.db.get_db", _broken_db)
        result = gather_context("node-add-concept", {"label": "Test"})
        assert result == {}


class TestRecentSamplesOnly:
    """Test the internal _recent_samples_only() helper."""

    def test_returns_empty_when_no_rows(self):
        """No rows → empty dict."""
        result = _recent_samples_only(_MockDB([]))
        assert result == {}

    def test_returns_samples_in_db_order(self):
        """Returns whatever the DB returns (ordering is the DB's job)."""
        mock = _MockDB([
            {"uuid": "a", "form_type": "t", "instruction": "i",
             "original": json.dumps({"l": "A.old"}), "revised": json.dumps({"l": "A.new"}),
             "word_count": 2, "source_domain": "semantika", "created_at": "2026-01-03T00:00:00"},
            {"uuid": "b", "form_type": "t", "instruction": "i2",
             "original": json.dumps({"l": "B.old"}), "revised": json.dumps({"l": "B.new"}),
             "word_count": 2, "source_domain": "semantika", "created_at": "2026-01-01T00:00:00"},
        ])
        result = _recent_samples_only(mock)
        assert len(result["writing_samples"]) == 2
        assert result["writing_samples"][0]["uuid"] == "a"
        assert result["writing_samples"][1]["uuid"] == "b"

    def test_returns_empty_on_db_error(self):
        """Non-DB object passed → returns empty dict."""
        result = _recent_samples_only(None)
        assert result == {}
