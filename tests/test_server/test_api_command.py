"""Tests for the command tree and general command dispatch.

Covers command tree introspection, help text, node/predicate/triple add
and list via commands, backup configuration commands, interactive form
routing, form registration, and general edge cases.
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


# ── Command tree ──────────────────────────────────────────────────────


class TestCommandTree:
    """Test the command tree endpoint."""

    def test_command_tree(self, client: TestClient):
        resp = client.get("/api/v1/command/tree")
        assert resp.status_code == 200
        data = resp.json()
        assert any(cmd["name"] == "node" for cmd in data)
        assert any(cmd["name"] == "predicate" for cmd in data)
        assert any(cmd["name"] == "triple" for cmd in data)
        assert any(cmd["name"] == "graph" for cmd in data)

    def test_help_text(self, client: TestClient):
        resp = client.get("/api/v1/command/help")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "help"
        assert "groups" in data
        assert "total" in data
        assert data["total"] > 0


# ── Additional command dispatch tests ──────────────────────────────────


class TestCommandHandler:
    """Test additional command dispatch paths not covered elsewhere."""

    def test_node_add_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "add"], "flags": {"labels": "Cmd Added Node"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "node" in data["data"]

    def test_node_list_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "node-list"


# ── Interactive form routing ───────────────────────────────────────────


class TestInteractiveForm:
    """Test interactive form routing for commands."""

    def test_interactive_form_routing(self, client: TestClient):
        """Verify !node add with form flag returns form-required."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "node-add"

    def test_interactive_form_predicate(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["predicate", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "predicate-add"

    def test_interactive_form_triple(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "triple-add"

    def test_interactive_form_unit(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["unit", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "unit-add"


class TestInteractiveFormsRegistration:
    """Test that all new interactive forms are properly registered."""

    @pytest.mark.parametrize("cmd_tokens,expected_form", [
        (["node", "delete"], "node-delete"),
        (["predicate", "delete"], "predicate-delete"),
        (["triple", "delete"], "triple-delete"),
        (["triple", "modify"], "triple-modify"),
        (["proof", "add"], "proof-add"),
        (["predicate", "group", "add"], "predicate-group-add"),
    ])
    def test_form_routing_on_validation_error(self, client: TestClient, cmd_tokens, expected_form):
        """Trigger form-required response for a command with validation error."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": cmd_tokens, "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("type") == "form-required"
        assert expected_form in str(data.get("data", {}))


# ── Backup config commands ─────────────────────────────────────────────


class TestBackupConfig:
    """Test backup configuration commands via !dispatch."""

    def test_backup_summary(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "_summary" in data["data"]

    def test_backup_config(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "config"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_config_list(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "config", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_config_add_and_delete(self, client: TestClient):
        """Add a backup strategy, verify, test, then delete it."""
        resp = client.post(
            "/api/v1/command",
            json={
                "tokens": ["backup", "config", "add"],
                "flags": {"id": "pytest-strategy", "interval": "0", "max_copies": "3"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "config", "test", "pytest-strategy"], "flags": {}},
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "config", "delete", "pytest-strategy"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_prune(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "prune"], "flags": {"keep": "5"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_now(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "now"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_backup_list(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["backup", "list"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"


# ── Command edge cases ─────────────────────────────────────────────────


class TestCommandEdgeCases:
    """Test corner cases in command handlers."""

    def test_view_missing_id(self, client: TestClient):
        """View without ID raises validation error."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "view"], "flags": {}},
        )
        assert resp.status_code == 400

    def test_view_nonexistent_node(self, client: TestClient):
        """View a non-existent node returns 400."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "view"], "flags": {"id": "ZZZDOESNOTEXIST"}},
        )
        assert resp.status_code == 400
