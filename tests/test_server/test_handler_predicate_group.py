"""Tests for predicate group command handlers via dispatch().

Uses shared ``services`` fixture from conftest which provides isolated
DB and proper patching of ``get_services()`` in all handler modules.
"""

from __future__ import annotations

import pytest

# Trigger handler registration
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch


def _create_group_with_member(services: dict, group_name: str = "my-group",
                               pred_id: str = "ex:knows") -> None:
    """Helper: create a predicate group with one member."""
    ps = services["predicate"]
    pg = services["predicate_group"]
    ps.create({"predicate_id": pred_id})
    group = pg.create({"group_name": group_name})
    pg.add_member(group["uuid"], pred_id)


# ── Tests ─────────────────────────────────────────────────────────────────


class TestPredicateGroupList:
    """!predicate group list"""

    def test_list_empty(self, services: dict) -> None:
        result = dispatch(["predicate", "group", "list"], {})
        assert result["type"] == "table"
        assert result["label"] == "Predicate Groups"

    def test_list_with_group(self, services: dict) -> None:
        _create_group_with_member(services)
        result = dispatch(["predicate", "group", "list"], {})
        assert result["type"] == "table"
        assert len(result["data"]) >= 1


class TestPredicateGroupView:
    """!predicate group view"""

    def test_view_not_found(self) -> None:
        with pytest.raises(Exception, match="not found"):
            dispatch(["predicate", "group", "view"], {"name": "nonexistent"})

    def test_view_missing_name(self) -> None:
        with pytest.raises(Exception, match="Specify a group name"):
            dispatch(["predicate", "group", "view"], {})

    def test_view_success(self, services: dict) -> None:
        _create_group_with_member(services)
        result = dispatch(["predicate", "group", "view"], {"name": "my-group"})
        assert result["type"] == "status"
        assert "members" in result["data"]


class TestPredicateGroupAdd:
    """!predicate group add"""

    def test_add_success(self, services: dict) -> None:
        result = dispatch(["predicate", "group", "add"], {"name": "new-group"})
        assert "Created group" in result["data"]["message"]

    def test_add_missing_name(self) -> None:
        with pytest.raises(Exception, match="Specify a group name"):
            dispatch(["predicate", "group", "add"], {})

    def test_add_duplicate(self, services: dict) -> None:
        dispatch(["predicate", "group", "add"], {"name": "dup-group"})
        with pytest.raises(Exception, match="already exists"):
            dispatch(["predicate", "group", "add"], {"name": "dup-group"})


class TestPredicateGroupRename:
    """!predicate group rename"""

    def test_rename_success(self, services: dict) -> None:
        dispatch(["predicate", "group", "add"], {"name": "old-name"})
        result = dispatch(
            ["predicate", "group", "rename"],
            {"name": "old-name", "new_name": "new-name"},
        )
        assert "Renamed" in result["data"]["message"]

    def test_rename_missing_args(self) -> None:
        with pytest.raises(Exception, match="Specify current and new"):
            dispatch(["predicate", "group", "rename"], {})

    def test_rename_not_found(self) -> None:
        with pytest.raises(Exception, match="not found"):
            dispatch(
                ["predicate", "group", "rename"],
                {"name": "nonexistent", "new_name": "newname"},
            )


class TestPredicateGroupDelete:
    """!predicate group delete"""

    def test_delete_success(self, services: dict) -> None:
        _create_group_with_member(services)
        result = dispatch(["predicate", "group", "delete"], {"name": "my-group"})
        assert "Deleted group" in result["data"]["message"]

    def test_delete_missing_name(self) -> None:
        with pytest.raises(Exception, match="Specify a group name"):
            dispatch(["predicate", "group", "delete"], {})

    def test_delete_not_found(self) -> None:
        with pytest.raises(Exception, match="not found"):
            dispatch(["predicate", "group", "delete"], {"name": "nonexistent"})


class TestPredicateGroupSearch:
    """!predicate group search"""

    def test_search_empty(self) -> None:
        result = dispatch(["predicate", "group", "search"], {"q": "xyz"})
        assert result["type"] == "table"
        assert len(result["data"]) == 0

    def test_search_found(self, services: dict) -> None:
        _create_group_with_member(services)
        result = dispatch(["predicate", "group", "search"], {"q": "my-"})
        assert len(result["data"]) >= 1

    def test_search_missing_query(self) -> None:
        with pytest.raises(Exception, match="Enter a search term"):
            dispatch(["predicate", "group", "search"], {})


class TestPredicateGroupAddMember:
    """!predicate group add-member"""

    def test_add_member_success(self, services: dict) -> None:
        _create_group_with_member(services, group_name="my-group", pred_id="ex:parent")
        # Create another predicate to add via the command
        services["predicate"].create({"predicate_id": "ex:knows"})
        result = dispatch(
            ["predicate", "group", "add-member"],
            {"group": "my-group", "predicate_id": "ex:knows"},
        )
        assert "Added" in result["data"]["message"]

    def test_add_member_missing_args(self) -> None:
        with pytest.raises(Exception, match="Specify group name"):
            dispatch(["predicate", "group", "add-member"], {})


class TestPredicateGroupRemoveMember:
    """!predicate group remove-member"""

    def test_remove_member_success(self, services: dict) -> None:
        _create_group_with_member(services)
        result = dispatch(
            ["predicate", "group", "remove-member"],
            {"group": "my-group", "predicate_id": "ex:knows"},
        )
        assert "Removed" in result["data"]["message"]

    def test_remove_member_missing_args(self) -> None:
        with pytest.raises(Exception, match="Specify group name"):
            dispatch(["predicate", "group", "remove-member"], {})
