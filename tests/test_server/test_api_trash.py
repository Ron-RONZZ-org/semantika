"""Tests for trash management — /api/v1/graph/trash endpoints.

Covers permanently deleting trashed nodes via command dispatch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Trash commands via dispatch ───────────────────────────────────────


class TestTrashAPI:
    """Test trash management via !command."""

    def test_trash_delete(self, client: TestClient):
        """Permanently delete a trashed node via !command."""
        client.post("/api/v1/graph/nodes", json={"node_id": "TRASH_DEL", "labels": {"en": "trash delete me"}})
        client.post("/api/v1/graph/nodes/TRASH_DEL/delete?soft=true")
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "trash", "delete"], "flags": {"id": "TRASH_DEL"}},
        )
        assert resp.status_code == 200
        assert "Deleted" in str(resp.json()) or "deleted" in str(resp.json())
