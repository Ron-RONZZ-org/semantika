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
