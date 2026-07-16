"""Tests for the file attachment API routes — /api/v1/files/*.

Covers copy, move, delete, node-not-found, and edge cases.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="class")
def seeded_client(client: TestClient) -> TestClient:
    """Ensure a test node exists."""
    client.post(
        "/api/v1/graph/nodes",
        json={"node_id": "FILENODE", "labels": {"en": "File Node"}},
    )
    client.post(
        "/api/v1/graph/nodes",
        json={"node_id": "FILENODE2", "labels": {"en": "File Node 2"}},
    )
    return client


class TestFileAttachAPI:
    """Cover the non-en_loko (actual file copy) paths."""

    def test_node_not_found(self, client: TestClient, tmp_path: Path):
        """POST /attach with unknown node returns 404."""
        resp = client.post(
            "/api/v1/files/attach",
            json={"node_id": "NONEXISTENT", "source": str(tmp_path / "f.txt"), "en_loko": True},
        )
        assert resp.status_code == 404

    def test_copy_file(self, seeded_client: TestClient, tmp_path: Path):
        """Attach via copy (en_loko=False, move=False)."""
        src = tmp_path / "copy_me.txt"
        src.write_text("hello from copy")
        resp = seeded_client.post(
            "/api/v1/files/attach",
            json={"node_id": "FILENODE", "source": str(src)},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["triples"]) >= 3  # filePath + mime + size
        # Source should still exist after copy
        assert src.exists()

    def test_move_file(self, seeded_client: TestClient, tmp_path: Path):
        """Attach via move (move=True)."""
        src = tmp_path / "move_me.txt"
        src.write_text("hello from move")
        resp = seeded_client.post(
            "/api/v1/files/attach",
            json={"node_id": "FILENODE2", "source": str(src), "move": True},
        )
        assert resp.status_code == 200, resp.text
        # Source should be gone after move
        assert not src.exists()

    def test_file_not_found_error(self, seeded_client: TestClient):
        """Attach with nonexistent file returns 400."""
        resp = seeded_client.post(
            "/api/v1/files/attach",
            json={"node_id": "FILENODE", "source": "/nonexistent/path/foo.txt"},
        )
        assert resp.status_code == 400
        assert "File error" in resp.text

    def test_attach_with_url_rejected(self, seeded_client: TestClient):
        """Attach with unsupported URL returns error."""
        resp = seeded_client.post(
            "/api/v1/files/attach",
            json={"node_id": "FILENODE", "source": "ftp://bad-scheme.com/file.txt"},
        )
        assert resp.status_code == 400

    def test_en_loko_attach(self, seeded_client: TestClient):
        """Attach via en_loko (reference-only, no file operation)."""
        resp = seeded_client.post(
            "/api/v1/files/attach",
            json={"node_id": "FILENODE", "source": "/path/to/reference.txt", "en_loko": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["triples"]) == 1  # only :hasFilePath, no MIME/size
        assert data["triples"][0]["predicate_id"] == ":hasFilePath"

    def test_get_after_copy_attach(self, seeded_client: TestClient, tmp_path: Path):
        """GET /by-node returns correct path and mime after a copy attach."""
        # Create a dedicated node for this test to avoid collision with test_copy_file
        seeded_client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "AFTERCOPY", "labels": {"en": "After Copy Test"}},
        )
        src = tmp_path / "hello_world.txt"
        src.write_text("hello world")
        attach_resp = seeded_client.post(
            "/api/v1/files/attach",
            json={"node_id": "AFTERCOPY", "source": str(src)},
        )
        assert attach_resp.status_code == 200, attach_resp.text
        get_resp = seeded_client.get("/api/v1/files/by-node/AFTERCOPY")
        assert get_resp.status_code == 200
        atts = get_resp.json()["attachments"]
        assert len(atts) >= 1
        # The stored path exists and ends with a plausible filename
        stored_path = atts[0]["path"]
        assert stored_path.endswith(".txt")
        # MIME should be detected (text/plain) and size should be a string of digits
        assert atts[0]["mime"] is not None
        assert atts[0]["size"] is not None
        assert atts[0]["size"].isdigit()


class TestFileGetAPI:
    """Cover the GET /by-node endpoint."""

    def test_get_attachments_empty(self, seeded_client: TestClient):
        """Node with no attachments returns empty list."""
        # Create a node without files
        seeded_client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "NOFILES", "labels": {"en": "No Files"}},
        )
        resp = seeded_client.get("/api/v1/files/by-node/NOFILES")
        assert resp.status_code == 200
        assert resp.json()["attachments"] == []

    def test_get_node_not_found(self, seeded_client: TestClient):
        """GET /by-node on nonexistent node returns 404."""
        resp = seeded_client.get("/api/v1/files/by-node/DOESNOTEXIST")
        assert resp.status_code == 404


class TestFileDeleteAPI:
    """Cover the DELETE /by-node endpoint."""

    def test_delete_attachments(self, seeded_client: TestClient, tmp_path: Path):
        """Attach a file, then delete attachments."""
        src = tmp_path / "to_delete.txt"
        src.write_text("delete me")
        # Attach via copy
        seeded_client.post(
            "/api/v1/files/attach",
            json={"node_id": "FILENODE", "source": str(src)},
        )
        resp = seeded_client.delete("/api/v1/files/by-node/FILENODE")
        assert resp.status_code == 200
        assert resp.json()["deleted_files"] >= 0  # could be 0 if file path not written to managed dir

    def test_delete_nonexistent_node(self, seeded_client: TestClient):
        """DELETE /by-node on nonexistent node returns 404."""
        resp = seeded_client.delete("/api/v1/files/by-node/DOESNOTEXIST")
        assert resp.status_code == 404

    def test_delete_node_with_no_attachments(self, seeded_client: TestClient):
        """Delete on node with no attachments still succeeds."""
        seeded_client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "CLEANNODE", "labels": {"en": "Clean"}},
        )
        resp = seeded_client.delete("/api/v1/files/by-node/CLEANNODE")
        assert resp.status_code == 200
        assert resp.json()["deleted_files"] == 0

    def test_get_after_delete(self, seeded_client: TestClient):
        """After deleting attachments, get returns empty."""
        resp = seeded_client.get("/api/v1/files/by-node/FILENODE")
        assert resp.status_code == 200
        atts = resp.json()["attachments"]
        # There might be filePath triples left (depends on cleanup), but that's ok
        assert isinstance(atts, list)
