"""Tests for graph command handlers via dispatch().

Covers !stats, !export, !import, !search, !view,
!node list/search/view/add/update/delete/rename/merge,
!predicate list/search/view/add/rename/delete,
!predicate-group list/view/add/rename/delete/search/add-member/remove-member,
!triple list/view/add/delete/modify.

Uses isolated DB (same pattern as test_handler_dispatch.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from semantika.core import SemantikaDB
from semantika.graph.db import SCHEMA, REVIEW_SCHEMA, PROOF_SCHEMA
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.predicate_group_service import PredicateGroupService
from semantika.graph.triple_service import TripleService
from semantika.graph.review_service import ReviewService
from semantika.graph.proof_service import ProofService

from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> SemantikaDB:
    """Create an isolated test database."""
    db_path = tmp_path / "test.db"
    db = SemantikaDB(db_path)
    for table, sql in SCHEMA.items():
        db.init_schema({table: sql})
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_triples_pos ON triples(predicate_id, object_value, subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_triples_osp ON triples(object_value, object_type, predicate_id, subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_triples_pred_subj ON triples(predicate_id, subject_id)",
    ]:
        db.execute(idx)
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
        "  node_id UNINDEXED, label_text, definition_text,"
        "  content=nodes, content_rowid=rowid, tokenize='unicode61'"
        ")"
    )
    for table, sql in {**REVIEW_SCHEMA, **PROOF_SCHEMA}.items():
        db.init_schema({table: sql})
    db.execute("PRAGMA foreign_keys=ON")
    return db


@pytest.fixture
def services(db: SemantikaDB) -> dict:
    """Return all services initialized on the test DB."""
    return {
        "node": NodeService(db),
        "predicate": PredicateService(db),
        "predicate_group": PredicateGroupService(db),
        "triple": TripleService(db),
        "review": ReviewService(db),
        "proof": ProofService(db),
    }


@pytest.fixture(autouse=True)
def mock_services(monkeypatch: pytest.MonkeyPatch, services: dict) -> None:
    """Mock get_services() to return the isolated services.

    Must patch both graph_db AND all handler modules that import
    get_services at module level.
    """
    import semantika.graph.db as graph_db
    monkeypatch.setattr(graph_db, "get_services", lambda: services)
    # Handler modules import get_services at module level via
    #   from semantika.graph.db import get_services
    # so we must patch each module's reference too.
    monkeypatch.setattr(
        "semantika.server.command.handlers.graph.get_services",
        lambda: services,
    )


@pytest.fixture
def seeded(services: dict) -> dict:
    """Create seed data: nodes ALICE, BOB and predicate ex:knows."""
    ns = services["node"]
    ps = services["predicate"]
    ts = services["triple"]
    ns.create({"node_id": "ALICE", "labels": {"en": "Alice"}})
    ns.create({"node_id": "BOB", "labels": {"en": "Bob"}})
    ns.create({"node_id": "CHARLIE", "labels": {"en": "Charlie"}})
    ps.create({"predicate_id": "ex:knows", "labels": {"en": "knows"}})
    ps.create({"predicate_id": "ex:age", "labels": {"en": "age"}})
    ts.add("ALICE", "ex:knows", "BOB", object_type="uri")
    ts.add("ALICE", "ex:age", "30", object_type="literal")
    return services


# ── Top-level command tests ─────────────────────────────────────────────


class TestCmdStats:
    """!stats"""

    def test_stats(self, seeded: dict) -> None:
        result = dispatch(["stats"], {})
        assert result["type"] == "status"

    def test_stats_empty(self, services: dict) -> None:
        result = dispatch(["stats"], {})
        assert result["type"] == "status"


class TestCmdExport:
    """!export"""

    def test_export(self, seeded: dict) -> None:
        result = dispatch(["export"], {})
        assert result["type"] == "status"

    def test_export_triples(self, seeded: dict) -> None:
        result = dispatch(["export"], {"triples": "true"})
        assert result["type"] == "status"


class TestCmdImport:
    """!import"""

    def test_import_turtle(self, seeded: dict) -> None:
        ttl = (
            "@prefix ex: <http://example.org/> .\n"
            '<http://example.org/ALICE> ex:knows <http://example.org/BOB> .\n'
        )
        result = dispatch(["import"], {"data": ttl})
        assert result["type"] == "status"

    def test_import_no_data(self, services: dict) -> None:
        with pytest.raises(Exception, match="Provide TTL"):
            dispatch(["import"], {})


class TestCmdSearch:
    """!search"""

    def test_search_matches(self, seeded: dict) -> None:
        result = dispatch(["search", "Alice"], {})
        assert result["type"] == "table" or result["type"] == "status"

    def test_search_no_matches(self, seeded: dict) -> None:
        result = dispatch(["search", "Nonexistent"], {})
        assert result["type"] == "status"

    def test_search_with_type(self, seeded: dict) -> None:
        result = dispatch(["search", "Alice"], {"type": "node"})
        assert result["type"] in ("table", "status")

    def test_search_all(self, seeded: dict) -> None:
        result = dispatch(["search", "Alice"], {"all": "true"})
        assert result["type"] in ("table", "status")


class TestCmdView:
    """!view"""

    def test_view_node(self, seeded: dict) -> None:
        result = dispatch(["view", "ALICE"], {})
        assert result["type"] == "status"


# ── Node handler tests ───────────────────────────────────────────────────


class TestCmdNodeList:
    """!node list"""

    def test_list_all(self, seeded: dict) -> None:
        result = dispatch(["node", "list"], {})
        assert result["type"] == "table"

    def test_list_with_limit(self, seeded: dict) -> None:
        result = dispatch(["node", "list"], {"limit": "2"})
        assert result["type"] == "table"


class TestCmdNodeSearch:
    """!node search"""

    def test_search(self, seeded: dict) -> None:
        result = dispatch(["node", "search", "Alice"], {})
        assert result["type"] == "table"


class TestCmdNodeView:
    """!node view"""

    def test_view(self, seeded: dict) -> None:
        result = dispatch(["node", "view", "ALICE"], {})
        assert result["type"] == "status"


class TestCmdNodeAdd:
    """!node add"""

    def test_add_with_labels(self, services: dict) -> None:
        result = dispatch(["node", "add"], {"id": "NEWNODE", "labels": "New node"})
        assert result["type"] == "status"

    def test_add_auto_id(self, services: dict) -> None:
        result = dispatch(["node", "add"], {"labels": "Auto node"})
        assert result["type"] == "status"


class TestCmdNodeUpdate:
    """!node update"""

    def test_update_labels(self, seeded: dict) -> None:
        result = dispatch(
            ["node", "update", "ALICE"],
            {"labels": "Updated Alice"},
        )
        assert result["type"] == "status"

    def test_update_definitions(self, seeded: dict) -> None:
        result = dispatch(
            ["node", "update", "ALICE"],
            {"definitions": '{"en": "A person"}'},
        )
        assert result["type"] == "status"


class TestCmdNodeDelete:
    """!node delete"""

    def test_delete(self, seeded: dict) -> None:
        result = dispatch(["node", "delete", "CHARLIE"], {})
        assert result["type"] == "status"

    def test_delete_hard(self, seeded: dict) -> None:
        result = dispatch(["node", "delete", "CHARLIE"], {"hard": "true"})
        assert result["type"] == "status"

    def test_delete_really(self, seeded: dict) -> None:
        result = dispatch(["node", "delete", "CHARLIE"], {"really": "true"})
        assert result["type"] == "status"


class TestCmdNodeRename:
    """!node rename"""

    def test_rename(self, seeded: dict) -> None:
        result = dispatch(["node", "rename", "CHARLIE", "CHARLES"], {})
        assert result["type"] == "status"

    def test_rename_nonexistent(self, services: dict) -> None:
        with pytest.raises(Exception, match="not found"):
            dispatch(["node", "rename", "NONEXISTENT", "NEWID"], {})


class TestCmdNodeMerge:
    """!node merge"""

    def test_merge(self, seeded: dict) -> None:
        result = dispatch(["node", "merge", "ALICE", "CHARLIE"], {})
        assert result["type"] == "status"

    def test_merge_same(self, seeded: dict) -> None:
        with pytest.raises(Exception, match="different"):
            dispatch(["node", "merge", "ALICE", "ALICE"], {})

    def test_merge_source_not_found(self, services: dict) -> None:
        with pytest.raises(Exception, match="not found"):
            dispatch(["node", "merge", "NONEXISTENT", "ALICE"], {})

    def test_merge_target_not_found(self, seeded: dict) -> None:
        with pytest.raises(Exception, match="not found"):
            dispatch(["node", "merge", "ALICE", "NONEXISTENT"], {})


# ── Predicate handler tests ──────────────────────────────────────────────


class TestCmdPredicateList:
    """!predicate list"""

    def test_list(self, seeded: dict) -> None:
        result = dispatch(["predicate", "list"], {})
        assert result["type"] == "table"


class TestCmdPredicateSearch:
    """!predicate search"""

    def test_search(self, seeded: dict) -> None:
        result = dispatch(["predicate", "search", "knows"], {})
        assert result["type"] == "table"


class TestCmdPredicateView:
    """!predicate view"""

    def test_view(self, seeded: dict) -> None:
        result = dispatch(["predicate", "view", "ex:knows"], {})
        assert result["type"] == "status"


class TestCmdPredicateAdd:
    """!predicate add"""

    def test_add(self, services: dict) -> None:
        result = dispatch(
            ["predicate", "add"],
            {"predicate_id": "ex:likes", "labels": "likes"},
        )
        assert result["type"] == "status"

    def test_add_with_domain_range(self, services: dict) -> None:
        result = dispatch(
            ["predicate", "add"],
            {"predicate_id": "ex:owns", "labels": "owns"},
        )
        assert result["type"] == "status"


class TestCmdPredicateRename:
    """!predicate rename"""

    def test_rename(self, seeded: dict) -> None:
        result = dispatch(["predicate", "rename", "ex:age", "ex:years"], {})
        assert result["type"] == "status"

    def test_rename_nonexistent(self, services: dict) -> None:
        with pytest.raises(Exception, match="not found"):
            dispatch(["predicate", "rename", "ex:nope", "ex:new"], {})


class TestCmdPredicateDelete:
    """!predicate delete"""

    def test_delete(self, seeded: dict) -> None:
        result = dispatch(["predicate", "delete", "ex:age"], {})
        assert result["type"] == "status"

    def test_delete_with_really(self, seeded: dict) -> None:
        result = dispatch(["predicate", "delete", "ex:age"], {"really": "true"})
        assert result["type"] == "status"


# ── Predicate group handler tests ────────────────────────────────────────
# NOTE: Registered as "predicate-group.*" (hyphenated, not space-separated)


class TestCmdPredicateGroup:
    """!predicate-group *"""

    def test_list(self, seeded: dict) -> None:
        result = dispatch(["predicate-group", "list"], {})
        assert result["type"] == "table"

    def test_add(self, seeded: dict) -> None:
        result = dispatch(
            ["predicate-group", "add", "social"],
            {},
        )
        assert result["type"] == "status"

    def test_view(self, seeded: dict) -> None:
        dispatch(["predicate-group", "add", "social"], {})
        result = dispatch(["predicate-group", "view", "social"], {})
        assert result["type"] == "status"

    def test_rename(self, seeded: dict) -> None:
        dispatch(["predicate-group", "add", "social"], {})
        result = dispatch(["predicate-group", "rename", "social", "soc"], {})
        assert result["type"] == "status"

    def test_delete(self, seeded: dict) -> None:
        dispatch(["predicate-group", "add", "social"], {})
        result = dispatch(["predicate-group", "delete", "social"], {})
        assert result["type"] == "status"

    def test_search(self, seeded: dict) -> None:
        dispatch(["predicate-group", "add", "social"], {})
        result = dispatch(["predicate-group", "search", "Social"], {})
        assert result["type"] == "table"

    def test_add_member(self, seeded: dict) -> None:
        dispatch(["predicate-group", "add", "social"], {})
        result = dispatch(
            ["predicate-group", "add-member", "social", "ex:knows"],
            {},
        )
        assert result["type"] == "status"

    def test_remove_member(self, seeded: dict) -> None:
        dispatch(["predicate-group", "add", "social"], {})
        dispatch(
            ["predicate-group", "add-member", "social", "ex:knows"], {}
        )
        result = dispatch(
            ["predicate-group", "remove-member", "social", "ex:knows"],
            {},
        )
        assert result["type"] == "status"


# ── Triple handler tests ─────────────────────────────────────────────────


class TestCmdTripleList:
    """!triple list"""

    def test_list(self, seeded: dict) -> None:
        result = dispatch(["triple", "list"], {})
        assert result["type"] == "table"

    def test_list_by_subject(self, seeded: dict) -> None:
        result = dispatch(["triple", "list", "ALICE"], {})
        assert result["type"] == "table"

    def test_list_by_subject_and_predicate(self, seeded: dict) -> None:
        result = dispatch(["triple", "list", "ALICE", "ex:knows"], {})
        assert result["type"] == "table"


class TestCmdTripleView:
    """!triple view"""

    def test_view_nonexistent(self, services: dict) -> None:
        result = dispatch(["triple", "view", "99999"], {})
        # Returns status with error data, not a raised exception
        assert result["type"] == "status"


class TestCmdTripleAdd:
    """!triple add"""

    def test_add_uri(self, seeded: dict) -> None:
        # CHARLIE is a valid node that BOB doesn't know yet
        result = dispatch(
            ["triple", "add", "BOB", "ex:knows", "CHARLIE"],
            {},
        )
        assert result["type"] == "status"

    def test_add_literal(self, seeded: dict) -> None:
        result = dispatch(
            ["triple", "add", "BOB", "ex:age", "25"],
            {"str": "true"},
        )
        assert result["type"] == "status"

    def test_add_with_datatype(self, seeded: dict) -> None:
        result = dispatch(
            ["triple", "add", "BOB", "ex:age", "25"],
            {"int": "true"},
        )
        assert result["type"] == "status"

    def test_add_missing_args(self, seeded: dict) -> None:
        with pytest.raises(Exception):
            dispatch(["triple", "add", "ALICE"], {})

    def test_add_invalid_subject(self, services: dict) -> None:
        with pytest.raises(Exception):
            dispatch(["triple", "add", "NONEXISTENT", "ex:knows", "BOB"], {})

    def test_add_invalid_predicate(self, seeded: dict) -> None:
        with pytest.raises(Exception):
            dispatch(["triple", "add", "ALICE", "ex:nonexistent", "BOB"], {})


class TestCmdTripleModify:
    """!triple modify"""

    def test_modify(self, seeded: dict) -> None:
        result = dispatch(
            ["triple", "modify", "ALICE", "ex:knows", "BOB"],
            {"object_value": "CHARLIE"},
        )
        assert result["type"] == "status"
