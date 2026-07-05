"""Tests for predicate CRUD API routes — /api/v1/graph/predicates/*.

Covers create, read, update, delete, rename, search, group management
and predicate-group CRUD via both REST and command dispatch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Must override data dir before importing app
TEST_DATA_DIR = Path("/tmp/semantika-preds-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Predicate CRUD ─────────────────────────────────────────────────────


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
            json={"new_id": "ex:renamedPred"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["predicate"]["predicate_id"] == "ex:renamedPred"

        # Verify triple was cascaded
        triples = client.get("/api/v1/graph/triples")
        assert triples.status_code == 200
        assert any(t["predicate_id"] == "ex:renamedPred" for t in triples.json()["triples"])


# ── Predicate update/delete via REST ───────────────────────────────────


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


# ── Predicate via command dispatch ─────────────────────────────────────


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
        assert "trash" in str(data)


# ── Predicate advanced commands ────────────────────────────────────────


class TestPredicateViewCommand:
    """Test !predicate view command (Tier 2c)."""

    def test_predicate_view(self, client: TestClient):
        """View predicate details via !command."""
        client.post("/api/v1/graph/predicates", json={
            "predicate_id": "ex:viewPred", "labels": {"en": "viewable pred"},
            "descriptions": {"en": "A predicate for viewing"},
        })
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "view"], "flags": {"predicate_id": "ex:viewPred"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        resp_data = data.get("data", data)
        assert str(resp_data) != ""


class TestPredicateAddDescriptions:
    """Test !predicate add with descriptions (Tier 2d)."""

    def test_predicate_add_with_descriptions(self, client: TestClient):
        """Add predicate with descriptions via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "add"], "flags": {
                "predicate_id": "ex:descPred",
                "labels": "en::description label",
                "descriptions": "en::A test description",
            }},
        )
        assert resp.status_code == 200
        # Verify via view
        v_resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "view"], "flags": {"predicate_id": "ex:descPred"}},
        )
        assert v_resp.status_code == 200


class TestPredicateDeletePrefix:
    """Test !predicate delete with --prefix (Tier 2b)."""

    def test_predicate_delete_with_prefix(self, client: TestClient):
        """Delete predicates matching a prefix via !command."""
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:pfxKeep", "labels": {"en": "keep me"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:pfxDel1", "labels": {"en": "del me 1"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:pfxDel2", "labels": {"en": "del me 2"}})
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "delete"], "flags": {"prefix": "ex:pfxDel"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "trash" in str(data)
        # Verify kept predicate still exists
        keep = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "view"], "flags": {"predicate_id": "ex:pfxKeep"}},
        )
        assert keep.status_code == 200


class TestPredicateUpdateReplace:
    """Test !predicate update with descriptions and --replace mode (Tier 2e)."""

    def test_predicate_update_with_descriptions(self, client: TestClient):
        """Update a predicate with descriptions via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "update"], "flags": {
                "predicate_id": "ex:viewPred",
                "descriptions": "fr::description francaise",
            }},
        )
        assert resp.status_code == 200
        v_resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "view"], "flags": {"predicate_id": "ex:viewPred"}},
        )
        assert v_resp.status_code == 200

    def test_predicate_update_with_new_id(self, client: TestClient):
        """Rename a predicate via !predicate update with --new-id."""
        client.post("/api/v1/graph/predicates", json={
            "predicate_id": "ex:predRenameMe", "labels": {"en": "rename me"},
        })
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "update"], "flags": {
                "predicate_id": "ex:predRenameMe", "new-id": "ex:predRenamed",
            }},
        )
        assert resp.status_code == 200
        v_resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "view"], "flags": {"predicate_id": "ex:predRenamed"}},
        )
        assert v_resp.status_code == 200


# ── Predicate group CRUD ───────────────────────────────────────────────


class TestPredicateGroupCRUD:
    """Test !predicate-group * commands (Tier 2f)."""

    def _setup_predicate(self, client: TestClient, pred_id: str):
        client.post("/api/v1/graph/predicates", json={"predicate_id": pred_id, "labels": {"en": pred_id}})

    def test_predicate_group_add(self, client: TestClient):
        """Add a predicate group via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "add"], "flags": {"name": "pg_test_group"}},
        )
        assert resp.status_code == 200

    def test_predicate_group_list(self, client: TestClient):
        """List predicate groups via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "list"], "flags": {}},
        )
        assert resp.status_code == 200

    def test_predicate_group_view(self, client: TestClient):
        """View a predicate group via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "view"], "flags": {"name": "pg_test_group"}},
        )
        assert resp.status_code == 200

    def test_predicate_group_add_member(self, client: TestClient):
        """Add a member to a predicate group via !command."""
        self._setup_predicate(client, "ex:pgMember1")
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "add-member"],
                  "flags": {"group": "pg_test_group", "predicate_id": "ex:pgMember1"}},
        )
        assert resp.status_code == 200

    def test_predicate_group_search(self, client: TestClient):
        """Search predicate groups by name via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "search"], "flags": {"q": "pg_test"}},
        )
        assert resp.status_code == 200

    def test_predicate_group_rename(self, client: TestClient):
        """Rename a predicate group via !command."""
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:pgRename", "labels": {"en": "rename"}})
        client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "add"], "flags": {"name": "pg_rename_me"}},
        )
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "rename"],
                  "flags": {"name": "pg_rename_me", "new_name": "pg_renamed"}},
        )
        assert resp.status_code == 200

    def test_predicate_group_remove_member(self, client: TestClient):
        """Remove a member from a predicate group via !command."""
        self._setup_predicate(client, "ex:pgRemoveMe")
        client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "add-member"],
                  "flags": {"group": "pg_renamed", "predicate_id": "ex:pgRemoveMe"}},
        )
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "remove-member"],
                  "flags": {"group": "pg_renamed", "predicate_id": "ex:pgRemoveMe"}},
        )
        assert resp.status_code == 200

    def test_predicate_group_delete(self, client: TestClient):
        """Delete a predicate group via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "delete"], "flags": {"name": "pg_renamed"}},
        )
        assert resp.status_code == 200


# ── Edge cases ─────────────────────────────────────────────────────────


class TestPredicateEdgeCases:
    """Predicate-specific edge cases."""

    def test_predicate_group_search_no_query(self, client: TestClient):
        """predicate-group search without query raises error."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "group", "search"], "flags": {}},
        )
        assert resp.status_code == 400
