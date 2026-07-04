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

    def test_rename_node(self, client: TestClient):
        """Rename a node's node_id, cascading to triples."""
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "OLDNAME", "labels": {"en": "Old Name"}},
        )
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:rel", "labels": {"en": "rel"}},
        )
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TARGET", "labels": {"en": "Target"}},
        )
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "OLDNAME", "predicate_id": "ex:rel", "object_value": "TARGET", "object_type": "uri"},
        )

        resp = client.patch(
            "/api/v1/graph/nodes/OLDNAME/rename",
            json={"new_id": "RENAMED"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["node"]["node_id"] == "RENAMED"

        # Verify triple was cascaded
        triples = client.get("/api/v1/graph/triples/by-subject/RENAMED")
        assert triples.status_code == 200
        assert len(triples.json()["triples"]) == 1

    def test_merge_nodes(self, client: TestClient):
        """Merge source node into target node."""
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "SOURCE_N", "labels": {"en": "Source Node"}},
        )
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TARGET_N", "labels": {"en": "Target Node"}},
        )
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:mergeRel", "labels": {"en": "merge rel"}},
        )
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "SOURCE_N", "predicate_id": "ex:mergeRel", "object_value": "TARGET_N", "object_type": "uri"},
        )

        resp = client.post(
            "/api/v1/graph/nodes/merge",
            params={"source_id": "SOURCE_N", "target_id": "TARGET_N"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["node"]["node_id"] == "TARGET_N"

        # Source should be deleted
        get_resp = client.get("/api/v1/graph/nodes/SOURCE_N")
        assert get_resp.status_code == 404

    def test_trash_list_restore_purge(self, client: TestClient):
        """Test trash lifecycle: create → soft-delete → list → restore."""
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TRASHABLE", "labels": {"en": "Trashable"}},
        )

        # Soft-delete
        resp = client.delete("/api/v1/graph/nodes/TRASHABLE?soft=true")
        assert resp.status_code == 200

        # List trash
        resp = client.get("/api/v1/graph/trash")
        assert resp.status_code == 200
        assert any(item.get("node_id") == "TRASHABLE" for item in resp.json()["items"])

        # Restore
        resp = client.post("/api/v1/graph/trash/TRASHABLE/restore")
        assert resp.status_code == 200
        assert resp.json()["node"]["node_id"] == "TRASHABLE"

        # Verify restored
        resp = client.get("/api/v1/graph/nodes/TRASHABLE")
        assert resp.status_code == 200


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

    def test_rename_predicate(self, client: TestClient):
        """Rename a predicate's predicate_id, cascading to triples."""
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:oldPred", "labels": {"en": "old pred"}},
        )
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "PRED_SUBJ", "labels": {"en": "PS"}},
        )
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "PRED_OBJ", "labels": {"en": "PO"}},
        )
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "PRED_SUBJ", "predicate_id": "ex:oldPred", "object_value": "PRED_OBJ", "object_type": "uri"},
        )

        resp = client.patch(
            "/api/v1/graph/predicates/ex:oldPred/rename",
            params={"new_id": "ex:renamedPred"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["predicate"]["predicate_id"] == "ex:renamedPred"

        # Verify triple was cascaded
        triples = client.get("/api/v1/graph/triples")
        assert triples.status_code == 200
        assert any(t["predicate_id"] == "ex:renamedPred" for t in triples.json()["triples"])


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

    def test_update_triple_metadata(self, client: TestClient):
        """Update triple metadata (object_lang, object_datatype)."""
        # Create nodes + predicate + triple
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "META_SUBJ", "labels": {"en": "Meta Subject"}},
        )
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "META_OBJ", "labels": {"en": "Meta Object"}},
        )
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:metaPred", "labels": {"en": "meta pred"}},
        )
        triple_resp = client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "META_SUBJ",
                "predicate_id": "ex:metaPred",
                "object_value": "Hello",
                "object_type": "literal",
            },
        )
        assert triple_resp.status_code == 200

        # Update metadata
        resp = client.patch(
            "/api/v1/graph/triples",
            params={
                "subject_id": "META_SUBJ",
                "predicate_id": "ex:metaPred",
                "object_value": "Hello",
                "object_type": "literal",
            },
            json={"object_lang": "en", "object_datatype": "xsd:string"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["triple"]["object_lang"] == "en"
        assert data["triple"]["object_datatype"] == "xsd:string"


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
        assert data["type"] == "status"
        assert "nodes" in data["data"]
        assert "predicates" in data["data"]
        assert len(data["data"]["nodes"]) >= 1

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


# ── Load Profile ──────────────────────────────────────────────────────────


class TestLLMLoadProfile:
    """Test LLM profile loading."""

    def test_load_profile(self, client: TestClient):
        # First create a named profile
        create_resp = client.post(
            "/api/v1/llm/profiles",
            json={
                "name": "test-profile",
                "provider_type": "deepseek",
                "api_key": "test-key-123",
                "model": "deepseek-v4-flash",
            },
        )
        assert create_resp.status_code == 201
        # Now load it
        resp = client.post("/api/v1/llm/profiles/test-profile/load")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "loaded"
        assert data["profile"] == "test-profile"

    def test_load_nonexistent_profile(self, client: TestClient):
        resp = client.post("/api/v1/llm/profiles/nonexistent/load")
        assert resp.status_code == 404


# ── Additional Command Dispatch Tests ─────────────────────────────────────


class TestAdditionalCommands:
    """Test additional command dispatch paths not covered elsewhere."""

    def test_node_add_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "add"], "flags": {"labels": "Cmd Added Node"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "node" in data["data"]

    def test_node_list_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "table"

    def test_unit_list_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["unit", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "table"

    def test_unit_view_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["unit", "view", "unit:METER"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_unit_resolve_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["unit", "resolve", "J"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resolved" in data["data"]

    def test_review_sessions_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["review", "sessions"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "table"

    def test_backup_summary_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "_summary" in data["data"]

    def test_backup_config_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "config"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_config_list(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "config", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_config_add_and_delete(self, client: TestClient):
        """Add a backup strategy, verify, test, then delete it."""
        resp = client.post(
            "/api/v1/command",
            json={
                "tokens": ["backup", "config", "add"],
                "flags": {"id": "pytest-strategy", "interval": "0", "max_copies": "3"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "config", "test", "pytest-strategy"], "flags": {}},
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "config", "delete", "pytest-strategy"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_prune_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "prune"], "flags": {"keep": "5"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_now_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "now"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_list_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_interactive_form_routing(self, client: TestClient):
        """Verify !node add with form flag returns form-required."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "node-add"

    def test_interactive_form_predicate(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "predicate-add"

    def test_interactive_form_triple(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "triple-add"

    def test_interactive_form_unit(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["unit", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "unit-add"


# ── SPARQL Query Endpoint ─────────────────────────────────────────────────


class TestSparqlAPI:
    """Test the SPARQL-like endpoint."""

    def test_sparql_select(self, client: TestClient):
        resp = client.get("/api/v1/query/sparql", params={"query": "SELECT * FROM nodes LIMIT 5"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "count" in data

    def test_sparql_rejects_non_select(self, client: TestClient):
        resp = client.get("/api/v1/query/sparql", params={"query": "DROP TABLE nodes"})
        assert resp.status_code == 400


# ── Query Search ──────────────────────────────────────────────────────────


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


# ── Deeper Unit Tests ─────────────────────────────────────────────────────


class TestUnitDecomposeAPI:
    """Test unit decompose endpoint."""

    def test_decompose_unit(self, client: TestClient):
        resp = client.post("/api/v1/units/decompose", params={"node_id": "unit:JOULE"})
        assert resp.status_code == 200
        data = resp.json()
        assert "decomposition" in data

    def test_decompose_nonexistent(self, client: TestClient):
        resp = client.post("/api/v1/units/decompose", params={"node_id": "unit:NONEXISTENT"})
        assert resp.status_code == 404


# ── Review Session CRUD ───────────────────────────────────────────────────


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


# ── Proof API ─────────────────────────────────────────────────────────────


class TestProofAPI:
    """Test proof CRUD operations."""

    def test_create_and_get_proof(self, client: TestClient):
        # Create fresh nodes and predicate for proof FK constraints
        resp = client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "PROOF_SUBJ", "labels": {"en": "Proof Subject"}},
        )
        assert resp.status_code == 200
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "PROOF_OBJ", "labels": {"en": "Proof Object"}},
        )
        assert resp.status_code == 200
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:proofPred", "labels": {"en": "proof predicate"}},
        )
        assert resp.status_code == 200
        client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "PROOF_SUBJ",
                "predicate_id": "ex:proofPred",
                "object_value": "PROOF_OBJ",
                "object_type": "uri",
            },
        )
        # Create proof
        resp = client.post(
            "/api/v1/proof/proofs",
            json={
                "subject_id": "PROOF_SUBJ",
                "predicate_id": "ex:proofPred",
                "object_value": "PROOF_OBJ",
                "proof_type": "observation",
                "source": "e2e test",
                "notes": "Testing",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "proof" in data
        proof_uuid = data["proof"]["uuid"]
        assert proof_uuid

        # Get by triple
        resp = client.get(
            "/api/v1/proof/proofs/by-triple",
            params={"subject_id": "PROOF_SUBJ", "predicate_id": "ex:proofPred", "object_value": "PROOF_OBJ"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["proofs"]) >= 1

        # Get by subject
        resp = client.get("/api/v1/proof/proofs/by-subject/PROOF_SUBJ")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["proofs"]) >= 1

        # Delete
        resp = client.delete(f"/api/v1/proof/proofs/{proof_uuid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


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


class TestFileAttachment:
    """Test file attachment API."""

    def test_attach_local_file(self, client: TestClient, tmp_path):
        """Attach a local file to a node (in-place reference)."""
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "FILENODE", "labels": {"en": "File Node"}},
        )

        # Create a temp file
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        resp = client.post(
            "/api/v1/files/attach",
            json={
                "node_id": "FILENODE",
                "source": str(test_file),
                "en_loko": True,  # reference only — no copy
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["triples"]) >= 1

        # Verify triples exist
        resp = client.get("/api/v1/files/by-node/FILENODE")
        assert resp.status_code == 200
        assert len(resp.json()["attachments"]) >= 1
