"""Tests for predicate trash command handlers via dispatch().

Uses shared ``services`` fixture from conftest which provides isolated
DB and proper patching of ``get_services()`` in all handler modules.
"""

from __future__ import annotations

import pytest

# Trigger handler registration
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch


# ── Tests ─────────────────────────────────────────────────────────────────


class TestPredicateTrashList:
    """!predicate trash list"""

    def test_list_empty(self) -> None:
        result = dispatch(["predicate", "trash", "list"], {})
        assert result["type"] == "table"
        assert result["label"] == "Predicate Trash"

    def test_list_with_items(self, services: dict) -> None:
        services["predicate"].create({"predicate_id": "ex:trashme"})
        services["predicate"].delete("ex:trashme", soft=True)
        result = dispatch(["predicate", "trash", "list"], {})
        assert len(result["data"]) >= 1


class TestPredicateTrashRestore:
    """!predicate trash restore"""

    def test_restore_success(self, services: dict) -> None:
        services["predicate"].create({"predicate_id": "ex:trashme"})
        services["predicate"].delete("ex:trashme", soft=True)
        result = dispatch(
            ["predicate", "trash", "restore"], {"predicate_id": "ex:trashme"}
        )
        assert "Restored" in result["data"]["message"]

    def test_restore_not_found(self) -> None:
        with pytest.raises(Exception, match="not found in trash"):
            dispatch(
                ["predicate", "trash", "restore"], {"predicate_id": "nonexistent"}
            )

    def test_restore_missing_id(self) -> None:
        with pytest.raises(Exception, match="Specify a predicate ID"):
            dispatch(["predicate", "trash", "restore"], {})


class TestPredicateTrashDelete:
    """!predicate trash delete"""

    def test_delete_success(self, services: dict) -> None:
        services["predicate"].create({"predicate_id": "ex:trashme"})
        services["predicate"].delete("ex:trashme", soft=True)
        result = dispatch(
            ["predicate", "trash", "delete"], {"predicate_id": "ex:trashme"}
        )
        assert "Permanently deleted" in result["data"]["message"]

    def test_delete_missing_id(self) -> None:
        with pytest.raises(Exception, match="Specify a predicate ID"):
            dispatch(["predicate", "trash", "delete"], {})


class TestPredicateTrashPurge:
    """!predicate trash purge"""

    def test_purge_empty(self) -> None:
        result = dispatch(["predicate", "trash", "purge"], {})
        assert "Purged" in result["data"]["message"]

    def test_purge_with_items(self, services: dict) -> None:
        services["predicate"].create({"predicate_id": "ex:trashme"})
        services["predicate"].delete("ex:trashme", soft=True)
        result = dispatch(["predicate", "trash", "purge"], {})
        assert "Purged" in result["data"]["message"]
        # Verify trash is now empty
        list_result = dispatch(["predicate", "trash", "list"], {})
        assert len(list_result["data"]) == 0
