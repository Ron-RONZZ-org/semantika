"""E2E functional tests for Semantika API routes.

Tests the full HTTP API layer as the frontend would interact with it,
including CRUD operations, command dispatch, export, stats, and LLM chat.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

# Must override data dir before importing app
TEST_DATA_DIR = Path("/tmp/semantika-e2e-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Node CRUD ────────────────────────────────────────────────────────────


class TestNodeAPI:
    """Test the /api/v1/graph/nodes endpoints."""

    def test_create_node(self, client: TestClient):
        resp = client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TESTNODE", "labels": {"en": "Test Node"}, "definitions": {"en": "A test node"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["node"]["node_id"] == "TESTNODE"
        assert "Test Node" in data["node"]["label_text"]

    def test_create_node_auto_id(self, client: TestClient):
        resp = client.post(
            "/api/v1/graph/nodes",
            json={"labels": {"en": "Auto ID Node"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["node"]["node_id"]) > 8  # UUID

    def test_create_duplicate_node(self, client: TestClient):
        resp = client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TESTNODE", "labels": {"en": "Duplicate"}},
        )
        assert resp.status_code == 400

    def test_list_nodes(self, client: TestClient):
        resp = client.get("/api/v1/graph/nodes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(n["node_id"] == "TESTNODE" for n in data["nodes"])

    def test_search_nodes(self, client: TestClient):
        resp = client.get("/api/v1/graph/nodes/search?q=Test")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    def test_get_node(self, client: TestClient):
        resp = client.get("/api/v1/graph/nodes/TESTNODE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["node"]["node_id"] == "TESTNODE"
        assert "triples" in data

    def test_get_node_not_found(self, client: TestClient):
        resp = client.get("/api/v1/graph/nodes/DOESNOTEXIST")
        assert resp.status_code == 404

    def test_update_node(self, client: TestClient):
        resp = client.patch(
            "/api/v1/graph/nodes/TESTNODE",
            json={"labels": {"en": "Updated Node", "fr": "Noeud de test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Updated Node" in data["node"]["label_text"]
        assert "Noeud" in data["node"]["label_text"]

    def test_delete_node(self, client: TestClient):
        # First create a node that has no triples referencing it
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TODELETE", "labels": {"en": "To Delete"}},
        )
        resp = client.delete("/api/v1/graph/nodes/TODELETE?soft=true")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_node_prefix_resolution(self, client: TestClient):
        resp = client.get("/api/v1/graph/nodes/TEST")
        assert resp.status_code == 200
        assert resp.json()["node"]["node_id"] == "TESTNODE"


# ── Predicate CRUD ───────────────────────────────────────────────────────


class TestPredicateAPI:
    """Test the /api/v1/graph/predicates endpoints."""

    def test_list_default_predicates(self, client: TestClient):
        resp = client.get("/api/v1/graph/predicates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 7  # Default predicates
        ids = [p["predicate_id"] for p in data["predicates"]]
        assert "rdf:type" in ids

    def test_create_predicate(self, client: TestClient):
        resp = client.post(
            "/api/v1/graph/predicates",
            json={
                "predicate_id": "ex:testPred",
                "labels": {"en": "test predicate"},
                "descriptions": {"en": "A predicate for testing"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["predicate"]["predicate_id"] == "ex:testPred"

    def test_create_duplicate_predicate(self, client: TestClient):
        resp = client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:testPred"},
        )
        assert resp.status_code == 400

    def test_search_predicates(self, client: TestClient):
        resp = client.get("/api/v1/graph/predicates/search?q=test")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1


# ── Triple CRUD ──────────────────────────────────────────────────────────


class TestTripleAPI:
    """Test the /api/v1/graph/triples endpoints."""

    def _setup(self, client: TestClient):
        """Ensure nodes and predicates exist for triple tests."""
        for nid in ["SUBJ", "OBJ"]:
            client.post(
                "/api/v1/graph/nodes",
                json={"node_id": nid, "labels": {"en": nid}},
            )
        if not any(
            p["predicate_id"] == "ex:rel"
            for p in client.get("/api/v1/graph/predicates").json()["predicates"]
        ):
            client.post(
                "/api/v1/graph/predicates",
                json={"predicate_id": "ex:rel", "labels": {"en": "relation"}},
            )

    def test_add_triple_uri(self, client: TestClient):
        self._setup(client)
        resp = client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "SUBJ",
                "predicate_id": "ex:rel",
                "object_value": "OBJ",
                "object_type": "uri",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["triple"]["subject_id"] == "SUBJ"
        assert data["triple"]["object_type"] == "uri"

    def test_add_triple_literal(self, client: TestClient):
        resp = client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "SUBJ",
                "predicate_id": "ex:rel",
                "object_value": "Hello World",
                "object_type": "literal",
                "object_lang": "en",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["triple"]["object_type"] == "literal"

    def test_list_triples(self, client: TestClient):
        """Verify triples list endpoint works (was 500 due to WITHOUT ROWID)."""
        resp = client.get("/api/v1/graph/triples?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_get_triples_by_subject(self, client: TestClient):
        resp = client.get("/api/v1/graph/triples/by-subject/SUBJ")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["triples"]) >= 1

    def test_delete_triple(self, client: TestClient):
        resp = client.delete(
            "/api/v1/graph/triples",
            params={
                "subject_id": "SUBJ",
                "predicate_id": "ex:rel",
                "object_value": "Hello World",
                "object_type": "literal",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] >= 1


# ── Query endpoints ──────────────────────────────────────────────────────


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
            json={"tokens": ["export"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ttl" in data["data"]
        assert "@prefix" in data["data"]["ttl"]

    def test_search_via_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["search", "TEST"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "table"
        assert len(data["data"]) >= 1

    def test_stats_via_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["stats"], "flags": {}},
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
        assert data["type"] == "table"

    def test_triple_list_via_command(self, client: TestClient):
        """Verify triple.list command works (was 500 due to WITHOUT ROWID)."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "table"

    def test_command_not_found(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["nonexistent"], "flags": {}},
        )
        assert resp.status_code == 400


# ── Command tree ─────────────────────────────────────────────────────────


class TestCommandTree:
    """Test the command tree endpoint."""

    def test_command_tree(self, client: TestClient):
        resp = client.get("/api/v1/command/tree")
        assert resp.status_code == 200
        data = resp.json()
        assert any(cmd["name"] == "node" for cmd in data)
        assert any(cmd["name"] == "predicate" for cmd in data)
        assert any(cmd["name"] == "triple" for cmd in data)
        assert any(cmd["name"] == "search" for cmd in data)
        assert any(cmd["name"] == "export" for cmd in data)
        assert any(cmd["name"] == "stats" for cmd in data)

    def test_help_text(self, client: TestClient):
        resp = client.get("/api/v1/command/help")
        assert resp.status_code == 200
        data = resp.json()
        assert "commands" in data


# ── LLM Chat ─────────────────────────────────────────────────────────────


class TestLLMAPI:
    """Test the /api/v1/llm/chat endpoint."""

    def test_chat_stats_keyword(self, client: TestClient):
        resp = client.post(
            "/api/v1/llm/chat",
            json={"message": "how many nodes do I have?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data["reply"]
        assert "predicates" in data["reply"]
        assert "triples" in data["reply"]

    def test_chat_search_keyword(self, client: TestClient):
        resp = client.post(
            "/api/v1/llm/chat",
            json={"message": "search for TESTNODE"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "test" in data["reply"].lower() or "TESTNODE" in data["reply"]

    def test_chat_help_keyword(self, client: TestClient):
        resp = client.post(
            "/api/v1/llm/chat",
            json={"message": "what can you do?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "help" in data["reply"].lower()

    def test_chat_generic(self, client: TestClient):
        resp = client.post(
            "/api/v1/llm/chat",
            json={"message": "Hello!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data


# ── Unit ontology ────────────────────────────────────────────────────────


class TestUnitAPI:
    """Test the /api/v1/units endpoint."""

    def test_list_units(self, client: TestClient):
        resp = client.get("/api/v1/units")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["units"]) > 0

    def test_get_unit(self, client: TestClient):
        resp = client.get("/api/v1/units/unit:METER")
        assert resp.status_code == 200
        data = resp.json()
        assert data["unit"]["unit_symbol"] == "m"

    def test_resolve_unit(self, client: TestClient):
        resp = client.post(
            "/api/v1/units/resolve",
            params={"expr": "J"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["node_id"] == "unit:JOULE"

    def test_create_singleton_unit(self, client: TestClient):
        resp = client.post(
            "/api/v1/units",
            json={"node_id": "TESTUNIT", "label": "Test Unit", "symbol": "tu"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["unit"] is not None


# ── Review ────────────────────────────────────────────────────────────────


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


# ── Node delete with FK cascading ────────────────────────────────────────


class TestNodeDeleteCascade:
    """Test that deleting a node cascades to triples."""

    def test_delete_node_removes_triples(self, client: TestClient):
        # Create a node that is referenced by a triple
        resp = client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "FKSOURCE", "labels": {"en": "FK Source"}},
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "FKTARGET", "labels": {"en": "FK Target"}},
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "FKSOURCE",
                "predicate_id": "ex:rel",
                "object_value": "FKTARGET",
                "object_type": "uri",
            },
        )
        assert resp.status_code == 200

        # Delete the target node (FK constraint would fail without cascade fix)
        resp = client.delete("/api/v1/graph/nodes/FKTARGET?soft=true")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify triple referencing the deleted node was also removed
        triples_resp = client.get("/api/v1/graph/triples/by-subject/FKSOURCE").json()
        assert len(triples_resp["triples"]) == 0
