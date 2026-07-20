"""Tests for cowrite API endpoint — /api/v1/cowrite.

Covers request validation, error handling, LLM integration, JSON schema
building, and structured-output fallback logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app
from semantika.server.llm.provider import reset_provider
from semantika.server.routes.cowrite import _build_json_schema, _cowrite_chat_with_schema


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


# ── Unit tests for JSON schema builder ────────────────────────────────────────


class TestBuildJsonSchema:
    """Direct tests for _build_json_schema()."""

    def test_builds_schema_with_correct_fields(self):
        """Fields map to properties in the schema."""
        fields = {"label": "a", "definition": "b"}
        schema = _build_json_schema(fields)
        assert schema["type"] == "json_schema"
        jss = schema["json_schema"]
        assert jss["name"] == "cowrite_response"
        assert jss["strict"] is True
        assert set(jss["schema"]["properties"].keys()) == {"label", "definition"}
        assert jss["schema"]["required"] == ["label", "definition"]
        assert jss["schema"]["additionalProperties"] is False

    def test_all_fields_are_string_type(self):
        """Every field in the schema has type 'string'."""
        fields = {"field1": "x", "field2": "y", "field3": "z"}
        schema = _build_json_schema(fields)
        props = schema["json_schema"]["schema"]["properties"]
        for prop in props.values():
            assert prop == {"type": "string"}

    def test_single_field_works(self):
        """A single-field form produces a valid schema."""
        schema = _build_json_schema({"body": "hello"})
        jss = schema["json_schema"]["schema"]
        assert jss["required"] == ["body"]
        assert "body" in jss["properties"]
        assert len(jss["properties"]) == 1

    def test_no_additional_properties(self):
        """additionalProperties is false to prevent hallucinated keys."""
        schema = _build_json_schema({"a": "1"})
        assert schema["json_schema"]["schema"]["additionalProperties"] is False


# ── Unit tests for schema fallback ────────────────────────────────────────────


class TestCowriteChatWithSchema:
    """Test the _cowrite_chat_with_schema() fallback logic."""

    @pytest.mark.asyncio
    async def test_tier1_schema_passed_to_chat_fn(self):
        """When Tier 1 succeeds, response_format with schema is passed."""
        mock_chat = AsyncMock()
        mock_chat.return_value = '{"ok": "yes"}'

        result = await _cowrite_chat_with_schema(
            mock_chat,
            [{"role": "user", "content": "hi"}],
            {"ok": "default"},
        )

        assert result == '{"ok": "yes"}'
        call_kwargs = mock_chat.call_args[1]
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"]["type"] == "json_schema"

    @pytest.mark.asyncio
    async def test_tier1_failure_falls_to_tier2_json_object(self):
        """When strict schema fails, falls back to json_object mode."""
        calls = []

        async def chat_fn_with_tracker(messages, **kwargs):
            calls.append(kwargs)
            if "response_format" in kwargs and kwargs["response_format"].get("type") == "json_schema":
                raise Exception("strict schema not supported")
            return '{"ok": "yes"}'

        result = await _cowrite_chat_with_schema(
            chat_fn_with_tracker,
            [{"role": "user", "content": "hi"}],
            {"ok": "default"},
        )

        assert result == '{"ok": "yes"}'
        assert len(calls) == 2
        assert calls[0]["response_format"]["type"] == "json_schema"
        assert calls[1]["response_format"]["type"] == "json_object"

    @pytest.mark.asyncio
    async def test_all_tiers_fail_returns_tier3_result(self):
        """When all tiers fail, the exception from Tier 3 propagates."""
        async def always_fails(messages, **kwargs):
            raise RuntimeError("API unreachable")

        with pytest.raises(RuntimeError, match="API unreachable"):
            await _cowrite_chat_with_schema(
                always_fails,
                [{"role": "user", "content": "hi"}],
                {"f": "v"},
            )

    @pytest.mark.asyncio
    async def test_fallback_works_end_to_end(self, client: TestClient):
        """API-level: provider that rejects response_format falls through to prompt-only."""
        call_count = 0

        async def rejecting_chat(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if "response_format" in kwargs:
                raise Exception("format not supported")
            return '{"label": "Fallback text", "definition": "Fallback def"}'

        with patch("semantika.server.routes.cowrite.get_provider") as mock_get:
            mock_provider = AsyncMock()
            mock_provider.available = True
            mock_provider.chat = rejecting_chat
            mock_get.return_value = mock_provider

            resp = client.post("/api/v1/cowrite", json={
                "form_type": "node-add-concept",
                "fields": {"label": "Orig", "definition": "Orig def"},
                "instruction": "improve",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["revised"]["label"] == "Fallback text"
        assert data["revised"]["definition"] == "Fallback def"
        # Tier 1 (schema) + Tier 2 (json_object) fail, Tier 3 (prompt-only) succeeds
        assert call_count >= 3
