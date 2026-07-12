"""Tests for ``!help`` command handler and ``GET /api/v1/command/help`` route.

Verifies that ``!help`` returns the auto-generated command reference
grouped by domain, and that ``!help <command>`` returns single-command
details.  Uses the same patterns as ``test_handler_graph.py`` (dispatch)
and ``test_api_command.py`` (route).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch, get_command_definitions

# Must override data dir before importing app (for route tests)
TEST_DATA_DIR = Path("/tmp/semantika-help-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SEMANTIKA_DATA_DIR", str(TEST_DATA_DIR))

from semantika.server.app import create_app


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB.

    Only needed for route tests (``GET /api/v1/command/help``).
    """
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Dispatch tests (!help via dispatch()) ────────────────────────────────


class TestCmdHelp:
    """!help — full command reference."""

    def test_help_returns_help_type(self, services: dict) -> None:
        """!help returns type=help with grouped data."""
        result = dispatch(["help"], {})
        assert result["type"] == "help"
        assert result["title"] == "Command Reference"

    def test_help_has_groups(self, services: dict) -> None:
        """!help data contains groups dict sorted by domain."""
        result = dispatch(["help"], {})
        data = result["data"]
        assert "groups" in data
        assert isinstance(data["groups"], dict)
        # At least a few domains should be present (node, predicate, triple, …)
        assert len(data["groups"]) >= 5

    def test_help_groups_have_commands(self, services: dict) -> None:
        """Each group contains a non-empty list of commands."""
        result = dispatch(["help"], {})
        groups = result["data"]["groups"]
        for domain, cmds in groups.items():
            assert isinstance(cmds, list), f"Group '{domain}' should be a list"
            assert len(cmds) > 0, f"Group '{domain}' should have commands"

    def test_help_commands_have_canonical(self, services: dict) -> None:
        """Each command entry has a canonical form (!path)."""
        result = dispatch(["help"], {})
        groups = result["data"]["groups"]
        for domain, cmds in groups.items():
            for cmd in cmds:
                assert "canonical" in cmd, f"Missing canonical in {domain} cmd"
                assert cmd["canonical"].startswith("!"), (
                    f"canonical should start with !: {cmd['canonical']}"
                )
                assert "description" in cmd, (
                    f"Missing description in {cmd['canonical']}"
                )

    def test_help_tracks_counts(self, services: dict) -> None:
        """!help data includes total and group_count."""
        result = dispatch(["help"], {})
        data = result["data"]
        assert data["total"] > 0
        assert data["group_count"] > 0
        # total should match get_command_definitions()
        all_defs = get_command_definitions()
        assert data["total"] == len(all_defs)


class TestCmdHelpSpecific:
    """!help <command> — single-command detail."""

    def test_help_specific_found(self, services: dict) -> None:
        """!help node list returns detail for node.list."""
        result = dispatch(["help", "node", "list"], {})
        assert result["type"] == "help"
        assert result["title"] == "!node list"
        data = result["data"]
        assert "command" in data
        assert data["command"]["canonical"] == "!node list"
        assert data["groups"] is None

    def test_help_specific_has_params(self, services: dict) -> None:
        """!help triple add shows params."""
        result = dispatch(["help", "triple", "add"], {})
        data = result["data"]
        cmd = data["command"]
        # triple.add requires params
        assert "params" in cmd
        assert len(cmd["params"]) > 0

    def test_help_specific_has_flags(self, services: dict) -> None:
        """!help graph export shows flags."""
        result = dispatch(["help", "graph", "export"], {})
        data = result["data"]
        cmd = data["command"]
        assert "flags" in cmd
        assert len(cmd["flags"]) > 0

    def test_help_specific_not_found(self, services: dict) -> None:
        """!help nonexistent command returns error."""
        result = dispatch(["help", "nonexistent", "command"], {})
        assert result["type"] == "help"
        assert "Not Found" in result["title"]
        data = result["data"]
        assert "error" in data
        assert data["groups"] is None

    def test_help_specific_case_insensitive(self, services: dict) -> None:
        """!help Node List (mixed case) still works."""
        result = dispatch(["Help", "NODE", "LIST"], {})
        assert result["type"] == "help"
        assert result["title"] == "!node list"

    def test_help_specific_deep_path(self, services: dict) -> None:
        """!help predicate group list resolves dotted sub-namespace."""
        result = dispatch(["help", "predicate", "group", "list"], {})
        assert result["type"] == "help"
        data = result["data"]
        assert "command" in data

    def test_help_specific_no_crash_with_many_args(self, services: dict) -> None:
        """!help with many tokens doesn't crash."""
        result = dispatch(["help", "a", "b", "c", "d", "e"], {})
        assert result["type"] == "help"
        assert "Not Found" in result["title"]


# ── Route tests (GET /api/v1/command/help) ───────────────────────────────


class TestHelpRoute:
    """GET /api/v1/command/help — API route."""

    def test_help_route_returns_groups(self, client: TestClient) -> None:
        """GET /help returns groups and totals."""
        resp = client.get("/api/v1/command/help")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "help"
        assert "groups" in body
        assert len(body["groups"]) >= 5
        assert "total" in body
        assert body["total"] > 0

    def test_help_route_single_command(self, client: TestClient) -> None:
        """GET /help?cmd=node.list returns single command."""
        resp = client.get("/api/v1/command/help", params={"cmd": "node.list"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "help"
        assert "command" in body
        assert body["command"]["canonical"] == "!node list"

    def test_help_route_not_found(self, client: TestClient) -> None:
        """GET /help?cmd=nonexistent returns error."""
        resp = client.get("/api/v1/command/help", params={"cmd": "nonexistent.foo"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "help"
        assert "error" in body

    def test_help_route_has_descriptions(self, client: TestClient) -> None:
        """Each command in the groups has a non-empty description."""
        resp = client.get("/api/v1/command/help")
        body = resp.json()
        for domain, cmds in body["groups"].items():
            for cmd in cmds:
                assert cmd.get("description", ""), (
                    f"Command {cmd.get('canonical', 'unknown')} "
                    f"in domain '{domain}' has no description"
                )
