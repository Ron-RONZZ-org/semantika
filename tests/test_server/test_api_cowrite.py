"""Tests for cowrite API endpoint — /api/v1/cowrite.

Covers request validation, error handling, and LLM integration.
Schema enforcement is now handled by ``lightercore.cowrite.engine``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app
from semantika.server.llm.provider import reset_provider


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_provider_deps():
    """Ensure the LLM provider singleton returns a mock provider."""
    reset_provider()
    yield


class TestCowriteAPI:
    """Test /api/v1/cowrite endpoint."""

    def test_missing_form_type(self, client: TestClient):
        """POST /api/v1/cowrite without form_type returns 400."""
        resp = client.post("/api/v1/cowrite", json={
            "fields": {"label": "Hello"},
            "instruction": "improve",
        })
        assert resp.status_code == 400
        assert "form_type" in resp.json()["detail"].lower()

    def test_missing_fields(self, client: TestClient):
        """POST /api/v1/cowrite without fields returns 400."""
        resp = client.post("/api/v1/cowrite", json={
            "form_type": "node-add-concept",
            "instruction": "improve",
        })
        assert resp.status_code == 400
        assert "fields" in resp.json()["detail"].lower()

    def test_missing_instruction(self, client: TestClient):
        """POST /api/v1/cowrite without instruction returns 400."""
        resp = client.post("/api/v1/cowrite", json={
            "form_type": "node-add-concept",
            "fields": {"label": "Hello"},
        })
        assert resp.status_code == 400
        assert "instruction" in resp.json()["detail"].lower()

    def test_non_string_field(self, client: TestClient):
        """Non-string field value returns 400."""
        resp = client.post("/api/v1/cowrite", json={
            "form_type": "node-add-concept",
            "fields": {"label": 42},
            "instruction": "improve",
        })
        assert resp.status_code == 400
        assert "must be a string" in resp.json()["detail"]

    @patch("semantika.server.routes.cowrite.get_provider")
    def test_returns_502_when_llm_unavailable(self, mock_get_provider, client: TestClient):
        """When the LLM provider is unavailable, the endpoint returns 502."""
        mock_provider = AsyncMock()
        mock_provider.available = False
        mock_get_provider.return_value = mock_provider

        resp = client.post("/api/v1/cowrite", json={
            "form_type": "node-add-concept",
            "fields": {"label": "Test node"},
            "instruction": "make it better",
        })
        assert resp.status_code == 502

    @patch("semantika.server.routes.cowrite.get_provider")
    def test_happy_path_with_mocked_llm(self, mock_get_provider, client: TestClient):
        """With a mocked provider that returns valid JSON, edits are returned."""
        mock_provider = AsyncMock()
        mock_provider.available = True
        mock_provider.chat = AsyncMock(return_value='{"label": "Improved label", "definition": "Better def"}')
        mock_get_provider.return_value = mock_provider

        resp = client.post("/api/v1/cowrite", json={
            "form_type": "node-add-concept",
            "fields": {"label": "Original label", "definition": "Original def"},
            "instruction": "improve this node",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "edits" in data
        assert "revised" in data
        assert "original" in data
        assert "session_id" in data
        assert data["revised"]["label"] == "Improved label"
        assert data["revised"]["definition"] == "Better def"
        assert data["original"] == {"label": "Original label", "definition": "Original def"}

    @patch("semantika.server.routes.cowrite.get_provider")
    def test_malformed_llm_response_returns_422(self, mock_get_provider, client: TestClient):
        """Malformed LLM JSON returns 422."""
        mock_provider = AsyncMock()
        mock_provider.available = True
        mock_provider.chat = AsyncMock(return_value="not valid json")
        mock_get_provider.return_value = mock_provider

        resp = client.post("/api/v1/cowrite", json={
            "form_type": "node-add-concept",
            "fields": {"label": "Test"},
            "instruction": "improve",
        })
        assert resp.status_code == 422

    @patch("semantika.server.routes.cowrite.get_provider")
    def test_empty_llm_response_returns_502(self, mock_get_provider, client: TestClient):
        """Empty LLM response returns 502."""
        mock_provider = AsyncMock()
        mock_provider.available = True
        mock_provider.chat = AsyncMock(return_value="")
        mock_get_provider.return_value = mock_provider

        resp = client.post("/api/v1/cowrite", json={
            "form_type": "node-add-concept",
            "fields": {"label": "Test"},
            "instruction": "improve",
        })
        assert resp.status_code == 502

    @patch("semantika.server.routes.cowrite.get_provider")
    def test_missing_field_in_response_returns_422(self, mock_get_provider, client: TestClient):
        """LLM returns JSON missing a required field → 422."""
        mock_provider = AsyncMock()
        mock_provider.available = True
        mock_provider.chat = AsyncMock(return_value='{"label": "Improved"}')
        mock_get_provider.return_value = mock_provider

        resp = client.post("/api/v1/cowrite", json={
            "form_type": "node-add-concept",
            "fields": {"label": "Orig", "definition": "Missing"},
            "instruction": "improve",
        })
        assert resp.status_code == 422



