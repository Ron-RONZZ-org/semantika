"""Tests for query/search/export/import API routes — /api/v1/query/*.

Covers stats, export (Turtle), import (TTL), search, raw SQL queries,
and date-filtered search via both REST and command dispatch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app
from semantika.server.routes.query import MAX_RAW_QUERY_LENGTH


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Query endpoints ────────────────────────────────────────────────────


class TestQueryAPI:
    """Test /api/v1/query/* endpoints."""

    def test_stats(self, client: TestClient):
        resp = client.get("/api/v1/query/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "predicates" in data
        assert "triples" in data

    def test_export_turtle(self, client: TestClient):
        resp = client.get("/api/v1/query/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "turtle"
        assert "@prefix" in data["data"]

    def test_export_via_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "export"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ttl" in data["data"]
        assert "@prefix" in data["data"]["ttl"]

    def test_search_via_command(self, client: TestClient):
        # Create a node first so the search has something to find
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TESTNODE", "labels": {"en": "Test Node"}},
        )
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "search", "TEST"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "nodes" in data["data"]
        assert "predicates" in data["data"]
        assert len(data["data"]["nodes"]) >= 1

    def test_stats_via_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "stats"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "nodes" in data["data"]

    def test_predicate_search_via_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "search"], "flags": {"q": "test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "predicate-list"

    def test_triple_list_via_command(self, client: TestClient):
        """Verify triple.list command works (was 500 due to WITHOUT ROWID)."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "triple-list"

    def test_command_not_found(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["nonexistent"], "flags": {}},
        )
        assert resp.status_code == 400


# ── Search API ─────────────────────────────────────────────────────────


class TestSearchAPI:
    """Test the unified search endpoint."""

    def test_search_all(self, client: TestClient):
        resp = client.get("/api/v1/query/search", params={"q": "Test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data["results"]
        assert "predicates" in data["results"]

    def test_triple_search_by_labels(self, client: TestClient):
        """Search triples by partial subject/predicate/object labels/IDs."""
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TS_SUBJ", "labels": {"en": "TripleSearchSubject"}},
        )
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TS_OBJ", "labels": {"en": "TripleSearchObject"}},
        )
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:tsPred", "labels": {"en": "triple search pred"}},
        )
        client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "TS_SUBJ",
                "predicate_id": "ex:tsPred",
                "object_value": "TS_OBJ",
                "object_type": "uri",
            },
        )

        # Search by subject ID (exact match)
        resp = client.get(
            "/api/v1/query/triples/search",
            params={"subject": "TS_SUBJ", "limit": 10},
        )
        assert resp.status_code == 200
        assert len(resp.json()["triples"]) >= 1

        # Search by predicate ID prefix
        resp = client.get(
            "/api/v1/query/triples/search",
            params={"predicate": "ex:tsPred", "limit": 10},
        )
        assert resp.status_code == 200
        assert len(resp.json()["triples"]) >= 1


# ── Raw SQL queries ────────────────────────────────────────────────────


class TestRawQueryAPI:
    """Test the read-only SQL query endpoint."""

    def test_raw_select(self, client: TestClient):
        resp = client.post("/api/v1/query/raw", json={"query": "SELECT * FROM nodes LIMIT 5"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "count" in data

    def test_raw_rejects_non_select(self, client: TestClient):
        resp = client.post("/api/v1/query/raw", json={"query": "DROP TABLE nodes"})
        assert resp.status_code == 400

    def test_raw_readonly_system_tables(self, client: TestClient):
        # System table queries are allowed — the read-only connection
        # prevents any modification regardless of query content.
        resp = client.post("/api/v1/query/raw", json={"query": "SELECT * FROM sqlite_master"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_raw_rejects_excessive_length(self, client: TestClient):
        """Queries exceeding MAX_RAW_QUERY_LENGTH are rejected."""
        long_query = "SELECT 1" + (" " * MAX_RAW_QUERY_LENGTH)
        resp = client.post("/api/v1/query/raw", json={"query": long_query})
        assert resp.status_code == 400
        assert "exceeds maximum length" in resp.json()["detail"].lower()

    def test_raw_accepts_boundary_length(self, client: TestClient):
        """Query at exactly MAX_RAW_QUERY_LENGTH is accepted (if valid)."""
        # Build a valid query that reaches the limit
        padding = MAX_RAW_QUERY_LENGTH - len("SELECT 1")
        boundary_query = "SELECT 1" + (" " * padding)
        resp = client.post("/api/v1/query/raw", json={"query": boundary_query})
        # Should be 200 (valid query within length limit)
        if resp.status_code != 200:
            # Could be 400 if SQLite rejects it, but NOT 400 for length
            assert "maximum length" not in resp.json().get("detail", "").lower()


# ── Search with date filter ────────────────────────────────────────────


class TestSearchDateFilter:
    """Test !search with date filtering (Tier 1e)."""

    def test_search_with_date_from(self, client: TestClient):
        """Search with --date-from filter."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "search"], "flags": {"q": "Subject", "date-from": "2026-01-01"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data.get("data", {})

    def test_search_without_date(self, client: TestClient):
        """Search without date filter (should still work)."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "search"], "flags": {"q": "Subject"}},
        )
        assert resp.status_code == 200


# ── Export with output file ────────────────────────────────────────────


class TestExportWithOutput:
    """Test !export with --output flag (Tier 3d)."""

    def test_export_with_output(self, client: TestClient, tmp_path):
        """Export Turtle to a file via !command."""
        out_file = tmp_path / "export-test.ttl"
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "export"], "flags": {"output": str(out_file)}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Exported" in str(data) or "exported" in str(data).lower()


# ── Edge cases ─────────────────────────────────────────────────────────


class TestQueryEdgeCases:
    """Query/search-specific edge cases."""

    def test_search_invalid_limit(self, client: TestClient):
        """Search with non-numeric limit defaults to 50."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "search"], "flags": {"q": "Subject", "limit": "abc"}},
        )
        assert resp.status_code == 200

    def test_import_missing_data(self, client: TestClient):
        """Import without data raises validation error."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "import"], "flags": {}},
        )
        assert resp.status_code == 400

    def test_search_missing_query(self, client: TestClient):
        """Search without query raises validation error."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "search"], "flags": {}},
        )
        assert resp.status_code == 400


