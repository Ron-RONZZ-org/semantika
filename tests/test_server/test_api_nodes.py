"""Tests for node CRUD API routes — /api/v1/graph/nodes/*.

Covers create, read, update, delete, rename, merge, trash lifecycle,
cascade delete, and prefix delete via both REST and command dispatch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB per class."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Helpers ─────────────────────────────────────────────────────────────


def _create_test_node(client: TestClient, node_id: str = "TESTNODE") -> None:
    """Helper to create a basic test node."""
    client.post(
        "/api/v1/graph/nodes",
        json={"node_id": node_id, "labels": {"en": f"Node {node_id}"}},
    )


def _ensure_predicate(client: TestClient, predicate_id: str = "ex:rel") -> None:
    """Helper to create a predicate if it doesn't exist."""
    client.post(
        "/api/v1/graph/predicates",
        json={"predicate_id": predicate_id, "labels": {"en": predicate_id}},
    )


# ── Node CRUD ──────────────────────────────────────────────────────────


class TestNodeAPI:
    """Test the /api/v1/graph/nodes endpoints — each test is self-contained."""

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
        _create_test_node(client)
        resp = client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "TESTNODE", "labels": {"en": "Duplicate"}},
        )
        assert resp.status_code == 400

    def test_list_nodes(self, client: TestClient):
        _create_test_node(client)
        resp = client.get("/api/v1/graph/nodes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(n["node_id"] == "TESTNODE" for n in data["nodes"])

    def test_search_nodes(self, client: TestClient):
        _create_test_node(client)
        resp = client.get("/api/v1/graph/nodes/search?q=Test")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    def test_get_node(self, client: TestClient):
        _create_test_node(client)
        resp = client.get("/api/v1/graph/nodes/TESTNODE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["node"]["node_id"] == "TESTNODE"
        assert "triples" in data

    def test_get_node_not_found(self, client: TestClient):
        resp = client.get("/api/v1/graph/nodes/DOESNOTEXIST")
        assert resp.status_code == 404

    def test_update_node(self, client: TestClient):
        _create_test_node(client)
        resp = client.patch(
            "/api/v1/graph/nodes/TESTNODE",
            json={"labels": {"en": "Updated Node", "fr": "Noeud de test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Updated Node" in data["node"]["label_text"]
        assert "Noeud" in data["node"]["label_text"]

    def test_delete_node(self, client: TestClient):
        _create_test_node(client, "TODELETE")
        resp = client.delete("/api/v1/graph/nodes/TODELETE?soft=true")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_node_prefix_resolution(self, client: TestClient):
        _create_test_node(client)
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
            json={"subject_id": "OLDNAME", "predicate_id": "ex:rel", "object_value": "TARGET", "object_type": "node"},
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
            json={"subject_id": "SOURCE_N", "predicate_id": "ex:mergeRel", "object_value": "TARGET_N", "object_type": "node"},
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


# ── Cascade delete ─────────────────────────────────────────────────────


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

        _ensure_predicate(client)

        resp = client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "FKSOURCE",
                "predicate_id": "ex:rel",
                "object_value": "FKTARGET",
                "object_type": "node",
            },
        )
        assert resp.status_code == 200

        # Delete WITHOUT force should return 409 because there are dependent triples
        resp = client.delete("/api/v1/graph/nodes/FKTARGET?soft=true")
        assert resp.status_code == 409
        assert "triple" in resp.json()["detail"]

        # Delete WITH force should succeed and cascade
        resp = client.delete("/api/v1/graph/nodes/FKTARGET?soft=true&force=true")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify triple referencing the deleted node was also removed
        triples_resp = client.get("/api/v1/graph/triples/by-subject/FKSOURCE").json()
        assert len(triples_resp["triples"]) == 0


# ── Node delete via command ────────────────────────────────────────────


class TestNodeDeletePrefix:
    """Test !node delete with --prefix (Tier 2a)."""

    def test_node_delete_with_prefix(self, client: TestClient):
        """Delete nodes matching a prefix via !command."""
        client.post("/api/v1/graph/nodes", json={"node_id": "ND_KEEP", "labels": {"en": "keep node"}})
        client.post("/api/v1/graph/nodes", json={"node_id": "ND_DEL1", "labels": {"en": "del node 1"}})
        client.post("/api/v1/graph/nodes", json={"node_id": "ND_DEL2", "labels": {"en": "del node 2"}})
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "delete"], "flags": {"prefix": "ND_DEL"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Deleted" in str(data)


# ── Node update via command ────────────────────────────────────────────


class TestNodeUpdateCommand:
    """Test !node update with labels/definitions/new-id (Tier 3b)."""

    def test_node_update_labels(self, client: TestClient):
        """Update node labels via !command."""
        client.post("/api/v1/graph/nodes", json={"node_id": "NUPD", "labels": {"en": "original"}})
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "update"], "flags": {"id": "NUPD", "labels": "en::updated"}},
        )
        assert resp.status_code == 200

    def test_node_update_with_new_id(self, client: TestClient):
        """Update node with --new-id rename via !command."""
        client.post("/api/v1/graph/nodes", json={"node_id": "NUPD2", "labels": {"en": "to rename"}})
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "update"], "flags": {"id": "NUPD2", "labels": "en::renamed", "new-id": "NUPD2_RENAMED"}},
        )
        assert resp.status_code == 200
        # Verify new ID exists
        v_resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "view"], "flags": {"id": "NUPD2_RENAMED"}},
        )
        assert v_resp.status_code == 200


# ── Edge cases ─────────────────────────────────────────────────────────


class TestNodeEdgeCases:
    """Node-specific edge cases."""

    def test_node_delete_multiple(self, client: TestClient):
        """Delete multiple nodes by passing multiple IDs."""
        for nid in ["MD1", "MD2", "MD3"]:
            client.post("/api/v1/graph/nodes", json={"node_id": nid, "labels": {"en": nid}})
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "delete"], "flags": {"id": "MD1", "_1": "MD2", "_2": "MD3"}},
        )
        assert resp.status_code == 200
        assert "Deleted" in str(resp.json())
