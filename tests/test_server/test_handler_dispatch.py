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
    ts.add("ALICE", "ex:knows", "BOB", object_type="uri")
    return services


# ── Trash handler tests ──────────────────────────────────────────────────


class TestTrashHandler:
    def test_trash_list_empty(self):
        result = dispatch(["trash", "list"], {})
        assert result["type"] == "table"
        assert result["label"] == "Trash"

    def test_trash_restore_not_found(self):
        with pytest.raises(Exception, match="not found in trash"):
            dispatch(["trash", "restore"], {"id": "NONEXISTENT"})

    def test_trash_delete(self, seeded):
        dispatch(["node", "delete"], {"id": "ALICE", "force": "1"})
        result = dispatch(["trash", "delete"], {"id": "ALICE"})
        assert "Permanently deleted" in result["data"]["message"]

    def test_trash_purge(self, seeded):
        dispatch(["node", "delete"], {"id": "ALICE", "force": "1"})
        result = dispatch(["trash", "purge"], {"days": "0"})
        assert "Purged" in result["data"]["message"]

    def test_trash_purge_invalid_days(self):
        with pytest.raises(Exception, match="Invalid days"):
            dispatch(["trash", "purge"], {"days": "abc"})

    def test_trash_restore_missing_id(self):
        with pytest.raises(Exception, match="Specify a node ID"):
            dispatch(["trash", "restore"], {})

    def test_trash_delete_missing_id(self):
        with pytest.raises(Exception, match="Specify a node ID"):
            dispatch(["trash", "delete"], {})

    def test_trash_purge_positive_days(self, seeded):
        dispatch(["node", "delete"], {"id": "ALICE", "force": "1"})
        result = dispatch(["trash", "purge"], {"days": "999"})
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
        for expected in ("node", "predicate", "triple", "unit", "search",
                         "view", "export", "import", "stats", "trash",
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
