"""Tests for user-defined command hooks — ``~/.config/semantika/hooks/*.py``.

Covers:
- ``freeze_system_commands`` / ``call_system_command`` delegation
- ``load_user_hooks`` directory scanning with ``exec()``
- Boilerplate-free snippets (no imports needed)
- Error isolation (one bad file does not block others)
- Cross-file conflict detection
- ``reset_registry`` cleans up hook sources
- ``--no-hooks`` flag in ``create_app``
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lightercore.permissions import PermissionLevel

from semantika.server.app import create_app
# Import handlers so @command decorators register system commands
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import (
    _hook_sources,
    _system_commands,
    call_system_command,
    dispatch,
    freeze_system_commands,
    get_handler_metadata,
    load_user_hooks,
    reset_registry,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _save_restore_registry():
    """Save and restore the full command registry around each test.

    This ensures tests that modify ``_commands`` (via hook loading,
    ``reset_registry()``, etc.) do not leak state into subsequent tests
    — particularly important because system handlers are registered only
    once at module import time.
    """
    import semantika.server.command.registry as reg
    saved = {
        "_commands": dict(reg._commands),
        "_group_descriptions": dict(reg._group_descriptions),
        "_interactive_forms": dict(reg._interactive_forms),
        "_system_commands": dict(reg._system_commands),
        "_hook_sources": dict(reg._hook_sources),
        "_command_tree_cache": reg._command_tree_cache,
        "_command_defs_cache": reg._command_defs_cache,
    }
    yield
    reg._commands.clear()
    reg._commands.update(saved["_commands"])
    reg._group_descriptions.clear()
    reg._group_descriptions.update(saved["_group_descriptions"])
    reg._interactive_forms.clear()
    reg._interactive_forms.update(saved["_interactive_forms"])
    reg._system_commands.clear()
    reg._system_commands.update(saved["_system_commands"])
    reg._hook_sources.clear()
    reg._hook_sources.update(saved["_hook_sources"])
    reg._command_tree_cache = saved["_command_tree_cache"]
    reg._command_defs_cache = saved["_command_defs_cache"]


@pytest.fixture
def hooks_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an empty hooks directory and point SEMANTIKA_CONFIG_DIR to it."""
    hd = tmp_path / "hooks"
    hd.mkdir(parents=True)
    monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
    return hd


# ── Unit tests: freeze / call_system_command ────────────────────────────────


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
    def _setup(self):
        """Reset services cache and freeze system commands before each test."""
        from semantika.graph.db import reset_services, close_db
        close_db()
        reset_services()
        freeze_system_commands()

    def test_calls_system_handler(self):
        """call_system_command dispatches to the snapshotted handler."""
        result = call_system_command("node.list", flags={"limit": "10"})
        assert result["type"] == "node-list"

    def test_custom_handler_can_delegate(self):
        """A user-style handler can wrap and delegate to the system handler."""
        from semantika.graph.db import get_services
        import uuid
        uid = str(uuid.uuid4())[:8]
        # Use node.add.concept (the concrete handler), not node.add (group root)
        result = call_system_command(
            "node.add.concept",
            flags={"id": f"HOOK_TEST_{uid}", "labels": "en::Hook Test"},
        )
        assert result["type"] == "status"
        assert "HOOK_TEST" in result["data"]["node"]["node_id"]

    def test_unknown_path_raises(self):
        """Unknown command paths raise CommandNotFound."""
        from semantika.server.command.errors import CommandNotFound
        with pytest.raises(CommandNotFound):
            call_system_command("nonexistent.command")


# ── Directory-based hook loading ────────────────────────────────────────────


class TestHooksDirectoryNotFound:
    """When no hooks directory exists, load_user_hooks is a no-op."""

    def test_no_hooks_dir_returns_zero(self, monkeypatch: pytest.MonkeyPatch):
        """Absent hooks dir returns 0 loaded files."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", "/tmp/nonexistent_semantika_cfg")
        freeze_system_commands()
        count = load_user_hooks()
        assert count == 0

    def test_empty_hooks_dir_returns_zero(self, hooks_dir: Path):
        """Empty hooks dir returns 0 loaded files."""
        freeze_system_commands()
        count = load_user_hooks()
        assert count == 0


class TestHookFileLoading:
    """Hook .py files in the hooks directory are loaded via exec()."""

    WRAP_AND_DELEGATE = """\
@command("node.list",
         description="[HOOKED] List all nodes",
         permission_level=PermissionLevel.READ,
         params=[{"name": "limit", "type": "number", "default": 100}])
def hooked_node_list(remaining, flags):
    result = call_system_command("node.list", remaining, flags)
    result["hooked"] = True
    return result
"""

    FULLY_CUSTOM = """\
@command("node.search",
         description="[HOOKED] Search nodes",
         permission_level=PermissionLevel.READ,
         params=[{"name": "q", "type": "string", "required": True}])
def hooked_node_search(remaining, flags):
    q = flags.get("q", remaining[0] if remaining else "")
    return {"type": "status", "data": {"message": f"Hooked search for: {q}"}}
"""

    @pytest.fixture(autouse=True)
    def _setup(self, hooks_dir: Path):
        """Write two hook files into the hooks directory."""
        (hooks_dir / "wrap_node_list.py").write_text(
            self.WRAP_AND_DELEGATE, encoding="utf-8",
        )
        (hooks_dir / "custom_search.py").write_text(
            self.FULLY_CUSTOM, encoding="utf-8",
        )

    def test_hooks_override_system_commands(self):
        """Loading hooks replaces system handlers with user-defined ones."""
        freeze_system_commands()
        count = load_user_hooks()
        assert count == 2

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

    def test_hook_sources_tracked(self):
        """Each registered command is tracked to its source file."""
        freeze_system_commands()
        load_user_hooks()

        assert _hook_sources["node.list"] == "wrap_node_list.py"
        assert _hook_sources["node.search"] == "custom_search.py"

    def test_reset_registry_clears_hook_sources(self):
        """reset_registry removes all hook source tracking."""
        freeze_system_commands()
        load_user_hooks()
        assert len(_hook_sources) == 2

        reset_registry()
        assert len(_hook_sources) == 0

    def test_no_imports_needed(self):
        """Snippets work without any import statements."""
        freeze_system_commands()
        load_user_hooks()
        # The hook files (WRAP_AND_DELEGATE, FULLY_CUSTOM) contain zero
        # import lines — they rely entirely on the pre-populated namespace.
        result = dispatch(["node", "search"], {"q": "no-imports"})
        assert "Hooked search for: no-imports" in result["data"]["message"]


# ── Error isolation ─────────────────────────────────────────────────────────


class TestErrorIsolation:
    """One bad hook file does not block others from loading."""

    def test_syntax_error_skips_one_file(self, hooks_dir: Path):
        """A file with a syntax error is skipped; others still load."""
        (hooks_dir / "good_hook.py").write_text(
            "@command('test.good', description='Works')\n"
            "def good(rem, fl): return {'type': 'status', 'data': {'ok': True}}\n",
            encoding="utf-8",
        )
        (hooks_dir / "bad_syntax.py").write_text(
            "this is not valid python {{{{\n",
            encoding="utf-8",
        )
        (hooks_dir / "another_good.py").write_text(
            "@command('test.another', description='Also works')\n"
            "def another(rem, fl): return {'type': 'status', 'data': {'ok': True}}\n",
            encoding="utf-8",
        )

        freeze_system_commands()
        count = load_user_hooks()
        assert count == 2  # bad_syntax.py skipped

        assert get_handler_metadata("test.good") is not None
        assert get_handler_metadata("test.another") is not None

    def test_runtime_error_skips_one_file(self, hooks_dir: Path):
        """A file that raises at module level is skipped; others still load."""
        (hooks_dir / "good_hook.py").write_text(
            "@command('test.good', description='Works')\n"
            "def good(rem, fl): return {'type': 'status', 'data': {'ok': True}}\n",
            encoding="utf-8",
        )
        (hooks_dir / "bad_runtime.py").write_text(
            "raise RuntimeError('Kaboom!')\n",
            encoding="utf-8",
        )

        freeze_system_commands()
        count = load_user_hooks()
        assert count == 1  # bad_runtime.py skipped

        assert get_handler_metadata("test.good") is not None


# ── Cross-file conflict detection ───────────────────────────────────────────


class TestCrossFileConflict:
    """When two hook files register the same command, the last one wins."""

    def test_last_file_wins_with_warning(self, hooks_dir: Path, caplog):
        """Overriding a command across files logs a warning."""
        (hooks_dir / "first.py").write_text(
            "@command('test.conflict', description='First version')\n"
            "def first(rem, fl): return {'type': 'status', 'data': {'from': 'first'}}\n",
            encoding="utf-8",
        )
        (hooks_dir / "second.py").write_text(
            "@command('test.conflict', description='Second version')\n"
            "def second(rem, fl): return {'type': 'status', 'data': {'from': 'second'}}\n",
            encoding="utf-8",
        )

        freeze_system_commands()
        with caplog.at_level(logging.WARNING):
            count = load_user_hooks()

        assert count == 2
        # The warning mentions the conflict
        assert any(
            "already registered by hook" in rec.message
            for rec in caplog.records
        ), f"Expected conflict warning, got: {[r.message for r in caplog.records]}"

        # Second file's version wins (alphabetical: second.py > first.py)
        result = dispatch(["test", "conflict"], {})
        assert result["data"]["from"] == "second"
        assert _hook_sources["test.conflict"] == "second.py"

    def test_same_file_overrides_no_warning(self, hooks_dir: Path, caplog):
        """Overriding a command within the same file does NOT warn."""
        (hooks_dir / "self_override.py").write_text(
            "@command('test.dup', description='First')\n"
            "def first(rem, fl): pass\n"
            "@command('test.dup', description='Second')\n"
            "def second(rem, fl): pass\n",
            encoding="utf-8",
        )

        freeze_system_commands()
        with caplog.at_level(logging.WARNING):
            load_user_hooks()

        warnings = [r.message for r in caplog.records]
        assert not any(
            "already registered by hook" in m for m in warnings
        ), f"Unexpected cross-file warning: {warnings}"


# ── File scanning rules ─────────────────────────────────────────────────────


class TestFileScanning:
    """Certain files are skipped when scanning the hooks directory."""

    def test_init_py_is_skipped(self, hooks_dir: Path):
        """__init__.py is not loaded as a hook file."""
        (hooks_dir / "__init__.py").write_text(
            "@command('test.init', description='Should not load')\n"
            "def init_cmd(rem, fl): pass\n",
            encoding="utf-8",
        )
        freeze_system_commands()
        count = load_user_hooks()
        assert count == 0

    def test_hidden_files_are_skipped(self, hooks_dir: Path):
        """Dot-prefixed hidden files are not loaded."""
        (hooks_dir / ".hidden_hook.py").write_text(
            "@command('test.hidden', description='Should not load')\n"
            "def hidden_cmd(rem, fl): pass\n",
            encoding="utf-8",
        )
        freeze_system_commands()
        count = load_user_hooks()
        assert count == 0

    def test_editor_backups_are_skipped(self, hooks_dir: Path):
        """Tilde-suffixed editor backup files are not loaded."""
        (hooks_dir / "my_hook.py~").write_text(
            "@command('test.backup', description='Should not load')\n"
            "def backup_cmd(rem, fl): pass\n",
            encoding="utf-8",
        )
        freeze_system_commands()
        count = load_user_hooks()
        assert count == 0

    def test_alphabetical_load_order(self, hooks_dir: Path):
        """Files are loaded in alphabetical order."""
        (hooks_dir / "02_middle.py").write_text(
            "@command('test.middle', description='Middle')\n"
            "def mid(rem, fl): fl['order'] = 'middle'; "
            "return {'type': 'status', 'data': dict(fl)}\n",
            encoding="utf-8",
        )
        (hooks_dir / "01_first.py").write_text(
            "@command('test.first', description='First')\n"
            "def fst(rem, fl): fl['order'] = 'first'; "
            "return {'type': 'status', 'data': dict(fl)}\n",
            encoding="utf-8",
        )
        (hooks_dir / "03_last.py").write_text(
            "@command('test.last', description='Last')\n"
            "def lst(rem, fl): fl['order'] = 'last'; "
            "return {'type': 'status', 'data': dict(fl)}\n",
            encoding="utf-8",
        )

        freeze_system_commands()
        load_user_hooks()

        # Dispatch in alphabetical order should work
        result = dispatch(["test", "first"], {})
        assert result["data"]["order"] == "first"
        result = dispatch(["test", "middle"], {})
        assert result["data"]["order"] == "middle"
        result = dispatch(["test", "last"], {})
        assert result["data"]["order"] == "last"


# ── Tests for the --no-hooks flag ──────────────────────────────────────────


class TestNoHooksFlag:
    """create_app(no_hooks=True) skips loading user hooks."""

    def test_no_hooks_passed_to_load_user_hooks(self, monkeypatch: pytest.MonkeyPatch):
        """With no_hooks=True, load_user_hooks receives no_hooks=True."""
        calls = []

        def _tracking_load(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(
            "semantika.server.command.registry.load_user_hooks",
            _tracking_load,
        )

        create_app(no_hooks=True)
        assert len(calls) == 1, "load_user_hooks should be called once"
        # The no_hooks flag is now handled inside load_user_hooks
        assert calls[0].get("no_hooks") is True, "no_hooks=True should be forwarded"

    def test_default_calls_load_user_hooks(self, monkeypatch: pytest.MonkeyPatch):
        """Without no-hooks, load_user_hooks IS called (default)."""
        calls = []

        def _tracking_load(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(
            "semantika.server.command.registry.load_user_hooks",
            _tracking_load,
        )

        create_app()  # no_hooks defaults to False
        assert len(calls) == 1, "load_user_hooks was not called by default"

    def test_no_hooks_api_still_functions(self):
        """The app returned by create_app(no_hooks=True) still serves API."""
        app = create_app(no_hooks=True)
        with TestClient(app) as client:
            resp = client.get("/api/v1/command/tree")
            assert resp.status_code == 200
            tree = resp.json()
            assert isinstance(tree, list)
            assert len(tree) > 0
