"""Unit tests for command handlers via dispatch().

Tests edge cases and error branches not covered by API E2E tests.
Uses isolated test databases and mocked get_services()
(defined in ``conftest.py``).
"""

from __future__ import annotations

import json

import pytest

# Trigger handler registration
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch, get_command_tree


@pytest.fixture
def seeded(services: dict) -> dict:
    """Create seed data for tests that need nodes + predicates."""
    ns = services["node"]
    ps = services["predicate"]
    ts = services["triple"]
    ns.create({"node_id": "ALICE", "labels": {"en": "Alice"}})
    ns.create({"node_id": "BOB", "labels": {"en": "Bob"}})
    ps.create({"predicate_id": "ex:knows", "labels": {"en": "knows"}})
    ts.add("ALICE", "ex:knows", "BOB", object_type="node")
    return services


# ── Trash handler tests ──────────────────────────────────────────────────


class TestTrashHandler:
    def test_trash_list_empty(self):
        result = dispatch(["node", "trash", "list"], {})
        assert result["type"] == "table"
        assert result["label"] == "Trash"

    def test_trash_restore_not_found(self):
        with pytest.raises(Exception, match="not found in trash"):
            dispatch(["node", "trash", "restore"], {"id": "NONEXISTENT"})

    def test_trash_delete(self, seeded):
        dispatch(["node", "delete"], {"id": "ALICE", "force": "1"})
        result = dispatch(["node", "trash", "delete"], {"id": "ALICE"})
        assert "Permanently deleted" in result["data"]["message"]

    def test_trash_purge(self, seeded):
        dispatch(["node", "delete"], {"id": "ALICE", "force": "1"})
        result = dispatch(["node", "trash", "purge"], {"days": "0"})
        assert "Purged" in result["data"]["message"]

    def test_trash_purge_invalid_days(self):
        with pytest.raises(Exception, match="Invalid days"):
            dispatch(["node", "trash", "purge"], {"days": "abc"})

    def test_trash_restore_missing_id(self):
        with pytest.raises(Exception, match="Specify a node ID"):
            dispatch(["node", "trash", "restore"], {})

    def test_trash_delete_missing_id(self):
        with pytest.raises(Exception, match="Specify one or more node IDs"):
            dispatch(["node", "trash", "delete"], {})

    def test_trash_purge_positive_days(self, seeded):
        dispatch(["node", "delete"], {"id": "ALICE", "force": "1"})
        result = dispatch(["node", "trash", "purge"], {"days": "999"})
        assert "Purged" in result["data"]["message"]


# ── Review handler tests ─────────────────────────────────────────────────


class TestReviewHandler:
    """Test review command handlers with isolated services."""

    def test_review_start_invalid_limit(self):
        with pytest.raises(Exception, match="Invalid limit"):
            dispatch(["review", "start"], {"limit": "abc"})

    def test_review_start_invalid_mode(self):
        with pytest.raises(Exception, match="Mode must be"):
            dispatch(["review", "start"], {"mode": "invalid"})

    def test_review_sessions(self, services):
        result = dispatch(["review", "sessions"], {})
        assert result["type"] == "table"

    def test_review_view_missing_uuid(self):
        with pytest.raises(Exception, match="Specify a session UUID"):
            dispatch(["review", "view"], {})

    def test_review_view_not_found(self):
        with pytest.raises(Exception, match="Session not found"):
            dispatch(["review", "view", "00000000-0000-0000-0000-000000000000"], {})

    def test_review_delete_missing_uuid(self):
        with pytest.raises(Exception, match="Specify a session UUID"):
            dispatch(["review", "delete"], {})

    def test_review_delete_not_found(self):
        """Deleting a nonexistent session should not raise."""
        result = dispatch(["review", "delete", "00000000-0000-0000-0000-000000000000"], {})
        assert result["type"] == "status"

    def test_proof_add_missing_args(self):
        with pytest.raises(Exception, match="Specify"):
            dispatch(["proof", "add"], {})

    def test_proof_add(self, seeded):
        # mock_services already patches get_services — just mock proof.create
        seeded["proof"].create = lambda data: {
            "uuid": "mock-uuid-1234", "subject_id": data.get("subject_id", ""),
            "predicate_id": data.get("predicate_id", ""), "object_value": data.get("object_value", ""),
        }
        result = dispatch(["proof", "add", "ALICE", "ex:knows", "BOB"], {})
        assert result["type"] == "status"
        assert "Created proof" in result["data"]["message"]

    def test_proof_view_missing_args(self):
        with pytest.raises(Exception, match="Specify"):
            dispatch(["proof", "view"], {})

    def test_proof_view(self, seeded):
        seeded["proof"].get_by_triple = lambda s, p, o: []
        result = dispatch(["proof", "view", "ALICE", "ex:knows", "BOB"], {})
        assert result["type"] == "table"

    def test_proof_delete_missing_uuid(self):
        with pytest.raises(Exception, match="Specify a proof UUID"):
            dispatch(["proof", "delete"], {})

    def test_proof_delete(self, seeded):
        seeded["proof"].delete = lambda uuid: None
        result = dispatch(["proof", "delete", "mock-uuid"], {})
        assert result["type"] == "status"
        assert "Deleted proof" in result["data"]["message"]


# ── System handler tests ─────────────────────────────────────────────────


class TestSystemHandler:
    """Test system command handlers."""

    def test_system_reindex_requires_confirmed(self):
        """!system reindex without --confirmed returns form-required."""
        result = dispatch(["system", "reindex"], {})
        assert result["type"] == "form-required"
        assert result["title"] == "Confirm Reindex"
        assert result["data"]["form"] == "confirm-reindex"


# ── Builtins handler tests ────────────────────────────────────────────────


class TestBuiltinsHandler:
    """Test !builtins reload command handler."""

    def test_builtins_reload_returns_status(self, services):
        """!builtins reload returns a status message with counts."""
        from semantika.graph.builtin_loader import invalidate_caches, get_predicate_catalog
        invalidate_caches()
        result = dispatch(["builtins", "reload"], {})
        assert result["type"] == "status"
        data = result["data"]
        assert "predicates" in data["message"]
        assert "type nodes" in data["message"]
        # Verify predicates are actually seeded after reload
        catalog = get_predicate_catalog()
        assert len(catalog) >= 1

    def test_builtins_reload_quiet(self, services):
        """!builtins reload --quiet returns minimal status."""
        result = dispatch(["builtins", "reload"], {"quiet": "true"})
        assert result["type"] == "status"
        assert "Builtins reloaded." in result["data"]["message"]

    def test_builtins_reload_preserves_existing(self, services):
        """Re-reading YAML does not overwrite existing user data."""
        from semantika.graph.builtin_loader import invalidate_caches
        invalidate_caches()
        # First reload seeds the data
        dispatch(["builtins", "reload"], {})
        # Re-create a predicate to simulate user data
        services["predicate"].create({"predicate_id": "test:userPred", "labels": {"en": "user"}})
        # Second reload should not remove the user predicate
        dispatch(["builtins", "reload"], {})
        assert services["predicate"].get("test:userPred") is not None


# ── Unit handler tests ───────────────────────────────────────────────────


class TestUnitHandler:
    """Test unit command handlers with isolated services."""

    def test_unit_list(self, services):
        result = dispatch(["unit", "list"], {})
        assert result["type"] == "table"

    def test_unit_view_not_found(self):
        with pytest.raises(Exception, match="Unit not found"):
            dispatch(["unit", "view", "NONEXISTENT"], {})

    def test_unit_add(self, services):
        result = dispatch(["unit", "add"], {"node_id": "TEST_UNIT", "labels": "Test unit", "symbol": "tu"})
        assert result["type"] == "status"
        assert "Created unit" in result["data"]["message"]

    def test_unit_add_no_error_on_duplicate(self, services):
        """create_singleton uses INSERT OR IGNORE, so duplicates don't raise."""
        from semantika.graph.db import get_services
        svc = get_services()
        svc["node"].create({"node_id": "unit:DUP_UNIT", "labels": {"en": "Dup"}})
        result = dispatch(["unit", "add"], {"node_id": "DUP_UNIT", "labels": "Dup"})
        assert result["type"] == "status"
        assert "Created unit" in result["data"]["message"]


# ── LLM handler tests ────────────────────────────────────────────────────


class TestLlmHandler:
    """Test LLM command handlers with mocked keyring."""

    @pytest.fixture(autouse=True)
    def mock_keyring(self, monkeypatch: pytest.MonkeyPatch):
        """Mock keyring to avoid touching system keychain."""
        store: dict[str, str] = {}
        import keyring as _kr
        monkeypatch.setattr(_kr, "set_password", lambda s, k, v: store.update({f"{s}:{k}": v}))
        monkeypatch.setattr(_kr, "get_password", lambda s, k: store.get(f"{s}:{k}"))
        monkeypatch.setattr(_kr, "delete_password", lambda s, k: store.pop(f"{s}:{k}", None))

    def test_llm_root(self):
        result = dispatch(["llm"], {})
        assert result["type"] == "status"
        assert "LLM" in result["title"]

    def test_llm_show(self):
        result = dispatch(["llm", "show"], {})
        assert result["type"] == "status"
        assert "provider_type" in result["data"]

    def test_llm_new_missing_protocol(self):
        with pytest.raises(Exception, match="Missing protocol"):
            dispatch(["llm", "new"], {})

    def test_llm_new(self):
        result = dispatch(["llm", "new"], {"provider_type": "openai", "api_key": "sk-test"})
        assert result["type"] == "status"
        assert result["data"]["protocol"] == "openai"

    def test_llm_new_with_alias(self):
        result = dispatch(["llm", "new"], {"provider_type": "deepseek", "api_key": "sk-ds", "alias": "my-ds"})
        assert "saved_as" in result["data"]

    def test_llm_set_no_flags(self):
        with pytest.raises(Exception, match="No settings"):
            dispatch(["llm", "set"], {})

    def test_llm_set(self):
        dispatch(["llm", "new"], {"provider_type": "openai", "api_key": "sk-old"})
        result = dispatch(["llm", "set"], {"model": "gpt-4"})
        assert result["type"] == "status"

    def test_llm_clear(self):
        dispatch(["llm", "new"], {"provider_type": "openai", "api_key": "sk-test"})
        result = dispatch(["llm", "clear"], {})
        assert result["type"] == "status"

    def test_llm_profiles(self):
        result = dispatch(["llm", "profiles"], {})
        assert result["type"] == "status"

    def test_llm_profile_list(self):
        result = dispatch(["llm", "profile", "list"], {})
        assert result["type"] == "status"

    def test_llm_profile_show(self):
        result = dispatch(["llm", "profile", "show"], {})
        assert result["type"] == "status"

    def test_llm_profile_load_missing_name(self):
        with pytest.raises(Exception, match="Missing profile name"):
            dispatch(["llm", "profile", "load"], {})

    def test_llm_profile_load_not_found(self):
        with pytest.raises(Exception, match="not found"):
            dispatch(["llm", "profile", "load"], {"name": "nope"})

    def test_llm_profile_load(self):
        dispatch(["llm", "new"], {"provider_type": "openai", "api_key": "sk-test", "alias": "my-prof"})
        result = dispatch(["llm", "profile", "load"], {"name": "my-prof"})
        assert result["type"] == "status"

    def test_llm_profile_delete_missing_name(self):
        with pytest.raises(Exception, match="Missing profile name"):
            dispatch(["llm", "profile", "delete"], {})

    def test_llm_profile_delete_not_found(self):
        with pytest.raises(Exception, match="not found"):
            dispatch(["llm", "profile", "delete"], {"name": "nope"})

    def test_llm_profile_delete(self):
        dispatch(["llm", "new"], {"provider_type": "openai", "api_key": "sk-test", "alias": "del-prof"})
        result = dispatch(["llm", "profile", "delete"], {"name": "del-prof"})
        assert result["type"] == "status"


# ── Reset handler tests ──────────────────────────────────────────────────


class TestResetHandler:
    def test_reset_no_args(self):
        with pytest.raises(Exception, match="Provide either"):
            dispatch(["reset"], {})

    def test_reset_conflicting_args(self):
        with pytest.raises(Exception, match="Cannot specify both"):
            dispatch(["reset", "/tmp/backup.db"], {"no-backup": "true"})

    def test_reset_form_required(self):
        result = dispatch(["reset"], {"no-backup": "true"})
        assert result["type"] == "form-required"
        assert result["data"]["form"] == "reset-no-backup"

    def test_reset_execute(self):
        # Mock the non-existent semantika.core.reset module
        import sys
        import types
        mock_module = types.ModuleType('semantika.core.reset')
        mock_module.reset_to_fresh_state = lambda backup_path=None: {
            "backup_path": None, "databases_removed": [], "credentials_cleared": 0}
        sys.modules['semantika.core.reset'] = mock_module

        result = dispatch(["reset"], {"no-backup": "true", "confirmed": "true"})
        assert result["type"] == "status"
        assert "Reset" in result["title"]


# ── Command tree tests ───────────────────────────────────────────────────


class TestCommandTree:
    def test_tree_has_expected_groups(self):
        tree = get_command_tree()
        names = [n["name"] for n in tree]
        for expected in ("node", "predicate", "triple", "unit", "graph",
                         "review", "proof", "llm", "backup", "reset"):
            assert expected in names, f"Missing {expected} in command tree"

    def test_tree_leaves_have_descriptions(self):
        """Every leaf in the tree should have a non-empty description."""
        def check(node):
            if "children" in node:
                for c in node["children"]:
                    check(c)
            else:
                assert node.get("description"), f"Leaf {node['name']} missing description"
        for n in get_command_tree():
            check(n)

    def test_tree_no_duplicates(self):
        tree = get_command_tree()
        names = [n["name"] for n in tree]
        assert len(names) == len(set(names)), "Duplicate top-level names in tree"

    def test_tree_list_nodes_have_list_id_key(self):
        """List commands expose ``listIdKey`` in the command tree."""
        tree = get_command_tree()

        def find_list_id_key(nodes: list, parent_path: str = "") -> list[tuple[str, str]]:
            found = []
            for n in nodes:
                path = f"{parent_path}.{n['name']}" if parent_path else n["name"]
                if n.get("children"):
                    found.extend(find_list_id_key(n["children"], path))
                elif n["name"] == "list":
                    list_id = n.get("listIdKey")
                    if list_id:
                        found.append((path, list_id))
            return found

        list_keys = find_list_id_key(tree)
        key_map = dict(list_keys)

        # Core domains should have listIdKey
        assert key_map.get("node.list") == "nodes"
        assert key_map.get("predicate.list") == "predicates"
        assert key_map.get("triple.list") == "triples"
        assert key_map.get("unit.list") == "units"


# ── Triple handler ambiguous resolution tests ─────────────────────────────
# Note: These MUST run BEFORE TestRegistryReset since they depend on
# handlers being registered. Test order is class definition order.


class TestTripleHandlerAmbiguousResolution:
    """Test that ambiguous node references in triple commands propagate errors."""

    def test_triple_delete_ambiguous_object_raises(self, services: dict):
        """Deleting a triple with an ambiguous object reference raises."""
        ns = services["node"]
        ps = services["predicate"]

        # Create two nodes sharing the same prefix
        ns.create({"node_id": "HELLO_WORLD", "labels": {"en": "Hello World"}})
        ns.create({"node_id": "HELLO_THERE", "labels": {"en": "Hello There"}})
        ps.create({"predicate_id": "ex:knows", "labels": {"en": "knows"}})

        # When _find_triple attempts ambiguous resolution, it should raise
        with pytest.raises(Exception, match="ambiguous"):
            dispatch(["triple", "delete", "HELLO_WORLD", "ex:knows", "HELLO"], {})

    def test_triple_modify_ambiguous_object_raises(self, services: dict):
        """Modifying a triple with an ambiguous object reference raises."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "ALPHA_ONE", "labels": {"en": "Alpha One"}})
        ns.create({"node_id": "ALPHA_TWO", "labels": {"en": "Alpha Two"}})
        ps.create({"predicate_id": "ex:rel", "labels": {"en": "rel"}})
        ts.add("ALPHA_ONE", "ex:rel", "ALPHA_TWO", object_type="node")

        # Modify with ambiguous object should raise, not silently return "not found"
        with pytest.raises(Exception, match="ambiguous"):
            dispatch(["triple", "modify", "ALPHA_ONE", "ex:rel", "ALPHA"], {})


# ── Registry reset tests ─────────────────────────────────────────────────


class TestRegistryReset:
    """Tests for registry.reset_registry().

    These tests save and restore the global registry state to avoid
    polluting subsequent tests in the same process.
    """

    @pytest.fixture(autouse=True)
    def auto_save_restore(self, request: pytest.FixtureRequest) -> None:
        """Save and restore global registry state around each test."""
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

        def _restore() -> None:
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

        request.addfinalizer(_restore)

    def test_reset_registry_clears_commands(self):
        """reset_registry() removes all registered commands."""
        import semantika.server.command.registry as reg

        assert len(reg._commands) > 0, "Commands should be registered"
        tree_before = reg.get_command_tree()
        assert len(tree_before) > 0

        reg.reset_registry()

        assert len(reg._commands) == 0, "All commands should be cleared"
        assert len(reg._interactive_forms) == 0, "Interactive forms should be cleared"
        tree_after = reg.get_command_tree()
        assert len(tree_after) == 0, "Command tree should be empty after reset"

    def test_reset_registry_clears_system_commands(self):
        """reset_registry() also clears _system_commands snapshot."""
        import semantika.server.command.registry as reg

        reg.reset_registry()
        assert len(reg._system_commands) == 0

    def test_reset_registry_clears_cache(self):
        """reset_registry() invalidates cached tree.

        Warms the caches first, then verifies reset clears them.
        Note: _command_tree_cache is set by get_command_tree();
              _command_defs_cache is set by get_command_definitions().
        """
        import semantika.server.command.registry as reg

        # Warm both caches
        _ = reg.get_command_tree()
        assert reg._command_tree_cache is not None, "Tree cache should be populated after get_command_tree()"
        _ = reg.get_command_definitions()
        assert reg._command_defs_cache is not None, "Defs cache should be populated after get_command_definitions()"

        reg.reset_registry()
        assert reg._command_tree_cache is None, "Tree cache should be cleared"
        assert reg._command_defs_cache is None, "Defs cache should be cleared"
