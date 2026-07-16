"""Tests for unit ontology API routes — /api/v1/units/*.

Covers listing, viewing, resolving, creating singleton units,
decomposing units, and unit commands via the dispatch system.
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


# ── Unit CRUD ──────────────────────────────────────────────────────────


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


# ── Unit decompose ─────────────────────────────────────────────────────


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


# ── Unit commands via dispatch ─────────────────────────────────────────


class TestUnitCommands:
    """Test unit commands via !command dispatch."""

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

    def test_unit_decompose_command(self, client: TestClient):
        """Decompose a unit via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["unit", "decompose"], "flags": {"id": "unit:JOULE"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        resp_data = data.get("data", data)
        assert "decomposition" in str(resp_data) or "JOULE" in str(resp_data)

    def test_unit_decompose_not_found_command(self, client: TestClient):
        """Decompose a non-existent unit via !command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["unit", "decompose"], "flags": {"id": "unit:NONEXISTENT"}},
        )
        assert resp.status_code == 400

    def test_unit_decompose_not_found(self, client: TestClient):
        """Decompose a non-existent unit via !command returns 400."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["unit", "decompose"], "flags": {"id": "unit:ZZZFAKE"}},
        )
        assert resp.status_code == 400
