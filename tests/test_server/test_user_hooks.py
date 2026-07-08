"""Tests for user-defined command hooks (load_user_hooks, call_system_command).

Covers:
- freeze_system_commands snapshotting
- call_system_command delegation
- User hook file loading and command override
- User hook delegating back to system handler
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lightercore.permissions import PermissionLevel

from semantika.server.app import create_app
# Import handlers so @command decorators register system commands
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import (
    _system_commands,
    call_system_command,
    command,
    dispatch,
    freeze_system_commands,
    get_handler_metadata,
    load_user_hooks,
)


# ── Unit tests for core hook infrastructure ────────────────────────────────


class TestFreezeSystemCommands:
    """freeze_system_commands copies current registry into _system_commands."""

    def test_freeze_snapshots_registered_commands(self):
        """After freeze, _system_commands contains known system handlers."""
        freeze_system_commands()
        assert "node.list" in _system_commands
        assert "node.add" in _system_commands
        assert "triple.add" in _system_commands

    def test_freeze_does_not_clear_main_registry(self):
        """_commands is unaffected after freeze."""
        freeze_system_commands()
        assert get_handler_metadata("node.list") is not None


class TestCallSystemCommand:
    """call_system_command invokes the original system handler."""

    @pytest.fixture(autouse=True)
    def _freeze(self):
        freeze_system_commands()

    def test_calls_system_handler(self):
        """call_system_command dispatches to the snapshotted handler."""
        result = call_system_command("node.list", flags={"limit": "10"})
        assert result["type"] == "node-list"

    def test_custom_handler_can_delegate(self):
        """A user-style handler can wrap and delegate to the system handler."""
        # Simulate what a user hook would do: call system handler with --id
        result = call_system_command(
            "node.add",
            flags={"id": "HOOK_TEST", "labels": "en::Hook Test"},
        )
        assert result["type"] == "status"
        assert result["data"]["node"]["node_id"] == "HOOK_TEST"

    def test_unknown_path_raises(self):
        """Unknown command paths raise CommandNotFound."""
        from semantika.server.command.errors import CommandNotFound
        with pytest.raises(CommandNotFound):
            call_system_command("nonexistent.command")


# ── Integration test: user hook file loading ────────────────────────────────


class TestUserHookLoading:
    """User hooks.py file is loaded and its commands override system ones."""

    HOOKS_CODE = """
from semantika.server.command.registry import command, call_system_command
from lightercore.permissions import PermissionLevel

@command("node.list",
         description="[HOOKED] List all nodes",
         permission_level=PermissionLevel.READ,
         params=[{"name": "limit", "type": "number", "default": 100}])
def hooked_node_list(remaining, flags):
    \"\"\"User-hooked version that delegates to system but changes the type.\"\"\"
    result = call_system_command("node.list", remaining, flags)
    result["hooked"] = True
    return result


@command("node.search",
         description="[HOOKED] Search nodes",
         permission_level=PermissionLevel.READ,
         params=[{"name": "q", "type": "string", "required": True}])
def hooked_node_search(remaining, flags):
    \"\"\"Fully custom search that always returns a message.\"\"\"
    q = flags.get("q", remaining[0] if remaining else "")
    return {"type": "status", "data": {"message": f"Hooked search for: {q}"}}
"""

    @pytest.fixture(autouse=True)
    def _setup_hooks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Create a hooks.py file in an isolated config dir."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        hooks_file = tmp_path / "hooks.py"
        hooks_file.write_text(self.HOOKS_CODE, encoding="utf-8")

    def test_hooks_override_system_commands(self):
        """Loading hooks replaces system handlers with user-defined ones."""
        freeze_system_commands()
        load_user_hooks()

        # The user's node.list should have hooked metadata
        meta = get_handler_metadata("node.list")
        assert meta is not None
        assert "[HOOKED]" in meta.get("description", "")

        # Dispatch should call the hooked version
        result = dispatch(["node", "list"], {"limit": "5"})
        assert result.get("hooked") is True
        assert result["type"] == "node-list"  # Delegated to system

    def test_hooks_can_fully_replace(self):
        """A hook that does not delegate fully replaces the command."""
        freeze_system_commands()
        load_user_hooks()

        result = dispatch(["node", "search"], {"q": "test-query"})
        assert result["type"] == "status"
        assert "Hooked search for: test-query" in result["data"]["message"]

    def test_hooked_command_in_tree_and_defs(self):
        """Hooked commands appear in the command tree and tool definitions."""
        from semantika.server.command.registry import (
            get_command_definitions,
            get_command_tree,
        )

        freeze_system_commands()
        load_user_hooks()

        tree = get_command_tree()
        node_entry = next((n for n in tree if n["name"] == "node"), None)
        assert node_entry is not None
        children = node_entry.get("children", [])
        list_entry = next((c for c in children if c["name"] == "list"), None)
        assert list_entry is not None
        assert "[HOOKED]" in list_entry.get("description", "")

        defs = get_command_definitions()
        hooked_def = next(
            (d for d in defs if d["path"] == ["node", "list"]), None
        )
        assert hooked_def is not None
        assert "[HOOKED]" in hooked_def.get("description", "")
