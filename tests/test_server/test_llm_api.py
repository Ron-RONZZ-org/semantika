"""Tests for the LLM API routes — /api/v1/llm/*.

Covers config, profiles, chat stub, and error paths.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DATA_DIR = Path("/tmp/semantika-llm-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app
from semantika.server.routes.llm import reset_provider


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with isolated DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_llm_state(monkeypatch: pytest.MonkeyPatch):
    """Reset the LLM provider singleton and mock keyring before each test."""
    # Mock keyring with an empty store
    store: dict[str, str] = {}
    import keyring as _kr
    monkeypatch.setattr(_kr, "set_password", lambda s, k, v: store.update({f"{s}:{k}": v}))
    monkeypatch.setattr(_kr, "get_password", lambda s, k: store.get(f"{s}:{k}"))
    monkeypatch.setattr(_kr, "delete_password", lambda s, k: store.pop(f"{s}:{k}", None))
    # Force provider to re-initialize on next access
    reset_provider()


class TestLlmConfigAPI:
    """Test /api/v1/llm/config and /configure endpoints."""

    def test_config_default_not_available(self, client: TestClient):
        """Default state: no LLM configured."""
        resp = client.get("/api/v1/llm/config")
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_configure_and_check(self, client: TestClient):
        """POST /configure saves provider config, then config returns available."""
        resp = client.post(
            "/api/v1/llm/configure",
            json={"provider_type": "openai", "api_key": "sk-test123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "configured"
        assert data["provider_type"] == "openai"

        # Verify config now shows available
        resp = client.get("/api/v1/llm/config")
        assert resp.status_code == 200
        assert resp.json()["available"] is True


class TestLlmProfileAPI:
    """Test /api/v1/llm/profiles endpoints."""

    def test_list_profiles_empty(self, client: TestClient):
        resp = client.get("/api/v1/llm/profiles")
        assert resp.status_code == 200
        assert resp.json()["profiles"] == []

    def test_create_and_list_profile(self, client: TestClient):
        resp = client.post(
            "/api/v1/llm/profiles",
            json={"name": "test-profile", "provider_type": "openai", "api_key": "sk-test"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"

        resp = client.get("/api/v1/llm/profiles")
        profiles = resp.json()["profiles"]
        names = [p["name"] for p in profiles]
        assert "test-profile" in names

    def test_load_profile(self, client: TestClient):
        client.post(
            "/api/v1/llm/profiles",
            json={"name": "work-profile", "provider_type": "deepseek", "api_key": "sk-work"},
        )
        resp = client.post("/api/v1/llm/profiles/work-profile/load")
        assert resp.status_code == 200
        assert resp.json()["status"] == "loaded"

    def test_load_nonexistent_profile(self, client: TestClient):
        resp = client.post("/api/v1/llm/profiles/nonexistent/load")
        assert resp.status_code == 404


class TestLlmChatStub:
    """Test the keyword-based stub fallback when no LLM is configured."""

    def test_chat_empty_message(self, client: TestClient):
        resp = client.post("/api/v1/llm/chat", json={"message": ""})
        assert resp.status_code == 200
        assert "Say something" in resp.json()["reply"]

    def test_chat_stats_keyword(self, client: TestClient):
        """'stats' keyword triggers stats stub."""
        resp = client.post("/api/v1/llm/chat", json={"message": "how many nodes do I have?"})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "nodes" in reply or "graph" in reply

    def test_chat_search_keyword(self, client: TestClient):
        """'search' keyword triggers search stub."""
        # First create a node
        client.post("/api/v1/graph/nodes", json={"node_id": "DOG", "labels": {"en": "Dog"}})
        resp = client.post("/api/v1/llm/chat", json={"message": "search for Dog"})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Dog" in reply or "found" in reply

    def test_chat_search_no_results(self, client: TestClient):
        """Search stub with no matches returns appropriate message."""
        resp = client.post("/api/v1/llm/chat", json={"message": "find ZZZNONEXISTENT"})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "couldn't find" in reply.lower() or "nothing" in reply.lower()

    def test_chat_help_keyword(self, client: TestClient):
        """'help' keyword returns help stub."""
        resp = client.post("/api/v1/llm/chat", json={"message": "what can you do?"})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "help" in reply or "commands" in reply

    def test_chat_generic_fallback(self, client: TestClient):
        """Unknown message returns the generic not-connected stub."""
        resp = client.post("/api/v1/llm/chat", json={"message": "tell me a joke"})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "not connected" in reply.lower() or "LLM" in reply
