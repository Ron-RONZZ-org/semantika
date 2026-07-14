"""Tests for graph command handlers via dispatch().

Covers !graph stats, !graph export, !graph import, !graph search, !graph view,
!node list/search/view/add/update/delete/rename/merge,
!predicate list/search/view/add/rename/delete,
!predicate group list/view/add/rename/delete/search/add-member/remove-member,
!triple list/view/add/delete/modify.

Uses isolated DB via shared fixtures (see ``conftest.py``).
"""

from __future__ import annotations

import pytest

from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch


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


# ── Graph-level command tests ────────────────────────────────────────────


class TestCmdGraphStats:
    """!graph stats"""

    def test_stats(self, seeded: dict) -> None:
        result = dispatch(["graph", "stats"], {})
        assert result["type"] == "status"

    def test_stats_empty(self, services: dict) -> None:
        result = dispatch(["graph", "stats"], {})
        assert result["type"] == "status"


class TestCmdGraphExport:
    """!graph export"""

    def test_export(self, seeded: dict) -> None:
        result = dispatch(["graph", "export"], {})
        assert result["type"] == "status"

    def test_export_triples(self, seeded: dict) -> None:
        result = dispatch(["graph", "export"], {"triples": "true"})
        assert result["type"] == "status"


class TestCmdGraphImport:
    """!graph import"""

    def test_import_turtle(self, seeded: dict) -> None:
        ttl = (
            "@prefix ex: <http://example.org/> .\n"
            '<http://example.org/ALICE> ex:knows <http://example.org/BOB> .\n'
        )
        result = dispatch(["graph", "import"], {"data": ttl})
        assert result["type"] == "status"

    def test_import_with_labels(self, seeded: dict) -> None:
        """rdfs:label triples should populate node labels, not placeholders."""
        ttl = (
            "@prefix ex: <http://example.org/> .\n"
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            "ex:Foo a ex:Thing ;\n"
            "    rdfs:label \"My Label\"@en .\n"
        )
        svc = seeded
        import json
        from semantika.server.command.registry import dispatch
        result = dispatch(["graph", "import"], {"data": ttl})
        assert result["type"] == "status"
        assert result["data"]["nodes_created"] >= 2

        node = svc["node"].get("http://example.org/Foo")
        assert node is not None
        labels = node["labels"]
        if isinstance(labels, str):
            labels = json.loads(labels)
        assert labels.get("en") == "My Label", (
            f"Expected 'My Label', got {labels}"
        )

    def test_import_no_data(self, services: dict) -> None:
        with pytest.raises(Exception, match="Provide TTL"):
            dispatch(["graph", "import"], {})


class TestCmdGraphSearch:
    """!graph search"""

    def test_search_matches(self, seeded: dict) -> None:
        result = dispatch(["graph", "search", "Alice"], {})
        assert result["type"] == "table" or result["type"] == "status"

    def test_search_no_matches(self, seeded: dict) -> None:
        result = dispatch(["graph", "search", "Nonexistent"], {})
        assert result["type"] == "status"

    def test_search_with_type(self, seeded: dict) -> None:
        result = dispatch(["graph", "search", "Alice"], {"type": "node"})
        assert result["type"] in ("table", "status")

    def test_search_all(self, seeded: dict) -> None:
        result = dispatch(["graph", "search", "Alice"], {"all": "true"})
        assert result["type"] in ("table", "status")


class TestCmdGraphView:
    """!graph view"""

    def test_view_node(self, seeded: dict) -> None:
        result = dispatch(["graph", "view", "ALICE"], {})
        assert result["type"] == "status"


# ── Node handler tests ───────────────────────────────────────────────────


class TestCmdNodeList:
    """!node list"""

    def test_list_all(self, seeded: dict) -> None:
        result = dispatch(["node", "list"], {})
        assert result["type"] == "node-list"

    def test_list_with_limit(self, seeded: dict) -> None:
        result = dispatch(["node", "list"], {"limit": "2"})
        assert result["type"] == "node-list"


class TestCmdNodeSearch:
    """!node search"""

    def test_search(self, seeded: dict) -> None:
        result = dispatch(["node", "search", "Alice"], {})
        assert result["type"] == "node-list"


class TestCmdNodeView:
    """!node view"""

    def test_view(self, seeded: dict) -> None:
        result = dispatch(["node", "view", "ALICE"], {})
        assert result["type"] == "status"


class TestCmdNodeAdd:
    """!node add"""

    def test_add_with_labels(self, services: dict) -> None:
        result = dispatch(["node", "add", "concept"], {"id": "NEWNODE", "labels": "New node"})
        assert result["type"] == "status"

    def test_add_auto_id(self, services: dict) -> None:
        result = dispatch(["node", "add", "concept"], {"labels": "Auto node"})
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
        assert result["type"] == "predicate-list"


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
# Registered as "predicate.group.*" (dotted sub-namespace)


class TestCmdPredicateGroup:
    """!predicate group *"""

    def test_list(self, seeded: dict) -> None:
        result = dispatch(["predicate", "group", "list"], {})
        assert result["type"] == "table"

    def test_add(self, seeded: dict) -> None:
        result = dispatch(
            ["predicate", "group", "add", "social"],
            {},
        )
        assert result["type"] == "status"

    def test_view(self, seeded: dict) -> None:
        dispatch(["predicate", "group", "add", "social"], {})
        result = dispatch(["predicate", "group", "view", "social"], {})
        assert result["type"] == "status"

    def test_rename(self, seeded: dict) -> None:
        dispatch(["predicate", "group", "add", "social"], {})
        result = dispatch(["predicate", "group", "rename", "social", "soc"], {})
        assert result["type"] == "status"

    def test_delete(self, seeded: dict) -> None:
        dispatch(["predicate", "group", "add", "social"], {})
        result = dispatch(["predicate", "group", "delete", "social"], {})
        assert result["type"] == "status"

    def test_search(self, seeded: dict) -> None:
        dispatch(["predicate", "group", "add", "social"], {})
        result = dispatch(["predicate", "group", "search", "Social"], {})
        assert result["type"] == "table"

    def test_add_member(self, seeded: dict) -> None:
        dispatch(["predicate", "group", "add", "social"], {})
        result = dispatch(
            ["predicate", "group", "add-member", "social", "ex:knows"],
            {},
        )
        assert result["type"] == "status"

    def test_remove_member(self, seeded: dict) -> None:
        dispatch(["predicate", "group", "add", "social"], {})
        dispatch(
            ["predicate", "group", "add-member", "social", "ex:knows"], {}
        )
        result = dispatch(
            ["predicate", "group", "remove-member", "social", "ex:knows"],
            {},
        )
        assert result["type"] == "status"


# ── Triple handler tests ─────────────────────────────────────────────────


class TestCmdTripleList:
    """!triple list"""

    def test_list(self, seeded: dict) -> None:
        result = dispatch(["triple", "list"], {})
        assert result["type"] == "triple-list"

    def test_list_by_subject(self, seeded: dict) -> None:
        result = dispatch(["triple", "list", "ALICE"], {})
        assert result["type"] == "triple-list"

    def test_list_by_subject_and_predicate(self, seeded: dict) -> None:
        result = dispatch(["triple", "list", "ALICE", "ex:knows"], {})
        assert result["type"] == "triple-list"


class TestCmdTripleSearch:
    """!triple search"""

    def test_search_by_subject(self, seeded: dict) -> None:
        """Search by subject label finds triples."""
        result = dispatch(["triple", "search", "Alice"], {})
        assert result["type"] == "triple-list"
        assert len(result["data"]) > 0

    def test_search_by_literal(self, seeded: dict) -> None:
        """Search by literal object value."""
        result = dispatch(["triple", "search", "30"], {})
        assert result["type"] == "triple-list"

    def test_search_no_matches(self, seeded: dict) -> None:
        """No matches returns empty list."""
        result = dispatch(["triple", "search", "ZZZZNOMATCH"], {})
        assert result["type"] == "triple-list"
        assert len(result["data"]) == 0


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


# ── Helper function tests ────────────────────────────────────────────────


class TestResolveTripleType:
    """Tests for the _resolve_triple_type shared helper."""

    def test_uri_default(self) -> None:
        """No flags -> defaults to URI type."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("some:value", {})
        assert val == "some:value"
        assert typ == "uri"
        assert dt is None
        assert lang is None

    def test_str_flag(self) -> None:
        """--str flag sets literal type."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("hello", {"str": "true"})
        assert typ == "literal"
        assert dt is None

    def test_bare_str_flag(self) -> None:
        """Bare --str (no value) also sets literal type."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("hello", {"str": ""})
        assert typ == "literal"

    def test_int_flag(self) -> None:
        """--int flag sets integer datatype."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("42", {"int": "true"})
        assert typ == "literal"
        assert dt == "xsd:integer"

    def test_float_flag(self) -> None:
        """--float flag sets decimal datatype."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("3.14", {"float": "true"})
        assert typ == "literal"
        assert dt == "xsd:decimal"

    def test_bool_flag(self) -> None:
        """--bool flag sets boolean datatype."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("true", {"bool": "true"})
        assert typ == "literal"
        assert dt == "xsd:boolean"

    def test_katex_flag(self) -> None:
        """--katex overrides object value and sets KaTeX datatype."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("ignored", {"katex": "E=mc^2"})
        assert val == "E=mc^2"
        assert typ == "literal"
        assert dt == "text/katex"

    def test_katex_strips_dollar_signs(self) -> None:
        """--katex strips $ delimiters."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("ignored", {"katex": "$E=mc^2$"})
        assert val == "E=mc^2"

    def test_str_with_lang(self) -> None:
        """--str with --lang sets language tag."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("bonjour", {"str": "true", "lang": "fr"})
        assert typ == "literal"
        assert lang == "fr"

    def test_str_takes_precedence_over_int(self) -> None:
        """Flag priority: katex > str_dosiero > str > int > float > bool > uri.
        str comes first in the elif chain, so it wins over int."""
        from semantika.server.command.handlers.triple import _resolve_triple_type
        val, typ, dt, lang = _resolve_triple_type("42", {"str": "true", "int": "true"})
        assert typ == "literal"
        assert dt is None  # str branch doesn't set datatype


class TestResolveObjectNode:
    """Tests for the _resolve_object_node shared helper."""

    def test_resolves_prefix(self, seeded: dict) -> None:
        """Resolves a unique prefix to a node ID."""
        from semantika.graph.db import get_services
        svc = get_services()
        from semantika.server.command.handlers.triple import _resolve_object_node
        nid = _resolve_object_node(svc, "ALI")
        assert nid == "ALICE"

    def test_not_found_raises(self, seeded: dict) -> None:
        """Non-existent reference raises CommandValidationError."""
        from semantika.graph.db import get_services
        svc = get_services()
        from semantika.server.command.errors import CommandValidationError
        from semantika.server.command.handlers.triple import _resolve_object_node
        with pytest.raises(CommandValidationError, match="not found"):
            _resolve_object_node(svc, "NONEXISTENT")


class TestFindTriple:
    """Tests for the _find_triple shared helper."""

    def test_finds_by_literal(self, seeded: dict) -> None:
        """Finds a triple by its literal object value."""
        from semantika.graph.db import get_services
        svc = get_services()
        from semantika.server.command.handlers.triple import _find_triple
        triple = _find_triple(svc, "ALICE", "ex:knows", "BOB")
        assert triple is not None
        assert triple["subject_id"] == "ALICE"

    def test_not_found_returns_none(self, seeded: dict) -> None:
        """Non-existent triple returns None."""
        from semantika.graph.db import get_services
        svc = get_services()
        from semantika.server.command.handlers.triple import _find_triple
        triple = _find_triple(svc, "ALICE", "ex:knows", "NONEXISTENT")
        assert triple is None
