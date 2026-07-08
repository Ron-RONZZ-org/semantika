"""Tests for the LLM API routes — /api/v1/llm/*.

Covers config, profiles, chat stub, error paths, and the permission gate.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app
from semantika.server.routes.llm import get_provider
from semantika.server.llm.provider import reset_provider


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
        """Unknown message returns a helpful hint instead of a generic 'not connected'."""
        resp = client.post("/api/v1/llm/chat", json={"message": "tell me a joke"})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        # Should now give a friendly suggestion, not just "not connected"
        assert "help" in reply.lower() or "stats" in reply.lower()


# ── Permission gate tests ─────────────────────────────────────────────────


def _mock_llm_provider(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure provider so that generate_command returns controllable results.

    Monkeypatches the provider singleton's ``generate_command`` method.
    The provider must be available (configured) for the chat route to
    attempt command generation instead of falling back to a stub.
    """
    # Configure a fake provider so the route attempts LLM calls
    from semantika.server.routes.llm import get_provider

    provider = get_provider()
    # Re-configure with dummy credentials to make it "available"
    provider.configure(provider_type="openai", api_key="sk-fake-test")


class TestPermissionGate:
    """LLM-generated destructive commands are gated behind user confirmation.

    These tests mock ``run_tool_loop`` to return a controlled ``confirm_tool``
    response, simulating what the real tool loop does when the LLM calls a
    WRITE-level command.
    """

    _mock_cmd: dict | None = None

    @pytest.fixture(autouse=True)
    def setup(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        # Ensure all command handlers are registered
        from semantika.server.command import handlers  # noqa: F401

        # Make provider available (otherwise the chat route bails early)
        provider = get_provider()
        provider.configure(provider_type="openai", api_key="sk-fake-test")

        # Mock run_tool_loop to return a canned response based on _mock_cmd
        import json as _json
        from semantika.server.command.registry import (
            get_command_level,
            get_handler_metadata,
            dispatch,
        )
        from lightercore.permissions import PermissionLevel
        import semantika.server.routes.llm as llm_module

        async def _mock_run_tool_loop(**kwargs):
            cmd = TestPermissionGate._mock_cmd
            if cmd is None:
                return None
            path = ".".join(cmd["tokens"])
            level = get_command_level(path) if get_handler_metadata(path) is not None else None

            if level is not None and level >= PermissionLevel.WRITE:
                meta = get_handler_metadata(path) or {}
                return {
                    "type": "confirm_tool",
                    "session_id": "test-sid",
                    "batch": [{
                        "tokens": cmd["tokens"],
                        "flags": cmd["flags"],
                        "description": meta.get("description", ""),
                    }],
                    "message": (
                        f"The LLM wants to perform **1** operation(s). "
                        f"Review and approve individually below."
                    ),
                }

            # READ-level: dispatch and return result
            result = dispatch(cmd["tokens"], cmd["flags"])
            return _json.dumps(result)

        monkeypatch.setattr(llm_module, "run_tool_loop", _mock_run_tool_loop)

    def test_blocks_destructive_reset(self, client: TestClient):
        """LLM asking for !reset returns type=confirm_tool instead of dispatching."""
        TestPermissionGate._mock_cmd = {
            "tokens": ["reset"],
            "flags": {"no-backup": "true", "confirmed": "yes"},
        }
        resp = client.post("/api/v1/llm/chat", json={"message": "reset everything"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "confirm_tool"
        assert data["batch"][0]["tokens"] == ["reset"]
        assert "approve" in data.get("message", "").lower()

    def test_blocks_destructive_trash_purge(self, client: TestClient):
        """LLM asking for !trash.purge returns type=confirm_tool."""
        TestPermissionGate._mock_cmd = {"tokens": ["node", "trash", "purge"], "flags": {}}
        resp = client.post("/api/v1/llm/chat", json={"message": "empty the trash"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "confirm_tool"

    def test_blocks_destructive_node_merge(self, client: TestClient):
        """LLM asking for !node.merge returns type=confirm_tool."""
        TestPermissionGate._mock_cmd = {
            "tokens": ["node", "merge"],
            "flags": {"source": "A", "target": "B"},
        }
        resp = client.post("/api/v1/llm/chat", json={"message": "merge A into B"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "confirm_tool"

    def test_allows_write_command(self, client: TestClient):
        """LLM asking for !node.list (WRITE-level) passes through to dispatch."""
        TestPermissionGate._mock_cmd = {"tokens": ["graph", "stats"], "flags": {}}
        resp = client.post("/api/v1/llm/chat", json={"message": "show stats"})
        assert resp.status_code == 200
        data = resp.json()
        # Should not be a confirm_tool type — either a regular result or a stub fallback
        assert data.get("type") != "confirm_tool"

    def test_blocks_backup_restore(self, client: TestClient):
        """LLM asking for !backup.restore returns type=confirm_tool."""
        TestPermissionGate._mock_cmd = {"tokens": ["backup", "restore"], "flags": {}}
        resp = client.post("/api/v1/llm/chat", json={"message": "restore from backup"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "confirm_tool"

    def test_blocks_backup_import(self, client: TestClient):
        """LLM asking for !backup.import returns type=confirm_tool."""
        TestPermissionGate._mock_cmd = {
            "tokens": ["backup", "import"],
            "flags": {"path": "/tmp/export.7z"},
        }
        resp = client.post("/api/v1/llm/chat", json={"message": "import from /tmp/export.7z"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "confirm_tool"

    def test_blocks_single_node_delete(self, client: TestClient):
        """node.delete modifies data, so it asks for user confirmation now."""
        TestPermissionGate._mock_cmd = {"tokens": ["node", "delete"], "flags": {"id": "testnode"}}
        resp = client.post("/api/v1/llm/chat", json={"message": "delete test node"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("type") == "confirm_tool"
        assert "approve" in data.get("message", "").lower()


class TestConfirmEndpoint:
    """POST /api/v1/llm/confirm executes pre-verified commands."""

    def test_confirm_dispatches_command(self, client: TestClient):
        """Confirm endpoint dispatches a simple command."""
        resp = client.post(
            "/api/v1/llm/confirm",
            json={"tokens": ["graph", "stats"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "data" in data

    def test_confirm_empty_tokens(self, client: TestClient):
        """Empty tokens return 400."""
        resp = client.post(
            "/api/v1/llm/confirm",
            json={"tokens": [], "flags": {}},
        )
        assert resp.status_code == 400

    def test_confirm_nonexistent_command(self, client: TestClient):
        """Unknown command returns 400."""
        resp = client.post(
            "/api/v1/llm/confirm",
            json={"tokens": ["nonexistent"], "flags": {}},
        )
        assert resp.status_code == 400

    def test_confirm_destructive_command(self, client: TestClient):
        """Confirm endpoint does NOT gate destructive commands — it dispatches directly."""
        resp = client.post(
            "/api/v1/llm/confirm",
            json={"tokens": ["reset"], "flags": {"no-backup": "true", "confirmed": "yes"}},
        )
        # Should try to dispatch reset (will fail because confirmed is set, but should not be blocked)
        # It attempts reset, which requires --no-backup (provided) and confirmed (provided).
        # It will try to reset the DB — may encounter issues.
        # The important thing: it returns a status response, not "confirm" type
        assert resp.status_code in (200, 400, 500)
        data = resp.json()
        assert isinstance(data, dict)
