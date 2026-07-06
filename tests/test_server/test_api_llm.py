"""Tests for LLM config and chat API routes — /api/v1/llm/*.

Covers chat keyword stubs, LLM configuration lifecycle, profile
creation/loading, and config endpoint integration tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Must override data dir before importing app
TEST_DATA_DIR = Path("/tmp/semantika-llm-e2e-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app
from semantika.server.llm.provider import reset_provider


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_keyring(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replace system keyring with an in-memory dict."""
    store: dict[str, str] = {}

    def set_pw(service: str, key: str, value: str) -> None:
        store[f"{service}:{key}"] = value

    def get_pw(service: str, key: str) -> str | None:
        return store.get(f"{service}:{key}")

    def del_pw(service: str, key: str) -> None:
        store.pop(f"{service}:{key}", None)

    import keyring as _kr
    monkeypatch.setattr(_kr, "set_password", set_pw)
    monkeypatch.setattr(_kr, "get_password", get_pw)
    monkeypatch.setattr(_kr, "delete_password", del_pw)

    reset_provider()
    return store


# ── LLM Chat keyword stubs ────────────────────────────────────────────


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


# ── LLM Config ─────────────────────────────────────────────────────────


class TestLLMConfigAPI:
    """Test LLM configuration routes."""

    def test_llm_config_default(self, client: TestClient):
        resp = client.get("/api/v1/llm/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data
        assert data["available"] is False

    def test_llm_configure_and_check(self, client: TestClient):
        # Configure
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
        # Verify config now shows available
        resp = client.get("/api/v1/llm/config")
        assert resp.status_code == 200
        assert resp.json()["available"] is True

    def test_llm_profiles(self, client: TestClient):
        resp = client.get("/api/v1/llm/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data

    def test_llm_chat_with_keyword_fallback(self, client: TestClient):
        # First configure with a fake key
        client.post(
            "/api/v1/llm/configure",
            json={
                "provider_type": "deepseek",
                "api_key": "test-key-123",
                "model": "deepseek-v4-flash",
            },
        )
        # Then chat — the route will try to use the LLM but the API call
        # will fail; we test the chat route still responds gracefully.
        resp = client.post(
            "/api/v1/llm/chat",
            json={"message": "how many nodes?"},
        )
        assert resp.status_code == 200
        assert "reply" in resp.json()


# ── LLM Profile loading ───────────────────────────────────────────────


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
