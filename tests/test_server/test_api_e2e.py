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

# Clear any leftover LLM config from keyring before tests
import keyring as _kr
import keyring.errors as _kr_err
try:
    _kr.delete_password("semantika-llm", "active-profile")
except (_kr_err.KeyringError, Exception):
    pass


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


# ── TTL Import ───────────────────────────────────────────────────────────


SAMPLE_TTL = """@prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Dog a ex:Animal ;
    rdfs:label "Dog"@en .

ex:Cat a ex:Animal ;
    rdfs:label "Cat"@en .
"""


class TestTTLImport:
    """Test TTL import via API and command."""

    def test_import_via_api(self, client: TestClient):
        resp = client.post("/api/v1/query/import", json={"data": SAMPLE_TTL})
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["nodes_created"] >= 2
        assert stats["predicates_created"] >= 2
        assert stats["triples_added"] >= 2

    def test_import_via_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["import"], "flags": {"data": SAMPLE_TTL}},
        )
        assert resp.status_code == 200

    def test_import_triples_persisted(self, client: TestClient):
        nodes = client.get("/api/v1/graph/nodes").json()
        node_ids = [n["node_id"] for n in nodes["nodes"]]
        assert any("Cat" in nid or "Animal" in nid for nid in node_ids)


# ── Predicate Update/Delete via API ──────────────────────────────────────


class TestPredicateUpdateDeleteAPI:
    """Test predicate update and delete via REST API."""

    def test_update_predicate(self, client: TestClient):
        resp = client.patch(
            "/api/v1/graph/predicates/rdf:type",
            json={"labels": {"en": "updated type", "eo": "ĝisdatigita tipo"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        labels = json.loads(data["predicate"]["labels"]) if isinstance(data["predicate"]["labels"], str) else data["predicate"]["labels"]
        assert "updated type" in labels.get("en", "")

    def test_delete_predicate(self, client: TestClient):
        # Create a temporary predicate
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:tempPred", "labels": {"en": "temp"}})
        resp = client.delete("/api/v1/graph/predicates/ex:tempPred")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_predicate_not_found(self, client: TestClient):
        resp = client.delete("/api/v1/graph/predicates/ex:nonexistent")
        assert resp.status_code == 404


# ── Predicate Update/Delete via Command ──────────────────────────────────


class TestPredicateCommand:
    """Test predicate update/delete via !command dispatch."""

    def test_predicate_update_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "update"], "flags": {"predicate_id": "rdf:type", "labels": "cmd updated"}},
        )
        assert resp.status_code == 200

    def test_predicate_delete_command(self, client: TestClient):
        # Create a predicate to delete via command
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:cmdDel", "labels": {"en": "cmd delete me"}})
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "delete", "ex:cmdDel"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Deleted" in str(data)


# ── LLM Config ───────────────────────────────────────────────────────────


class TestLLMConfigAPI:
    """Test LLM configuration routes."""

    def test_llm_config_default(self, client: TestClient):
        resp = client.get("/api/v1/llm/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data

    def test_llm_configure(self, client: TestClient):
        resp = client.post(
            "/api/v1/llm/configure",
            json={
                "provider_type": "deepseek",
                "api_key": "test-key-123",
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "temperature": 0.7,
                "max_tokens": 2048,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "configured"

    def test_llm_config_after_setup(self, client: TestClient):
        resp = client.get("/api/v1/llm/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True

    def test_llm_profiles(self, client: TestClient):
        resp = client.get("/api/v1/llm/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data

    def test_llm_chat_with_keyword_fallback(self, client: TestClient):
        # After configure with a fake key, the provider will try to use it
        # but the API call will fail. We test the chat route still responds.
        resp = client.post(
            "/api/v1/llm/chat",
            json={"message": "how many nodes?"},
        )
        assert resp.status_code == 200
        assert "reply" in resp.json()
