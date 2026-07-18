"""Tests for !node add quote command.

Tests cover auto-ID generation, triple creation, and edge cases.
"""

from __future__ import annotations

import pytest

from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.handlers import node_quote  # noqa: F401
from semantika.server.command.registry import dispatch


@pytest.fixture
def seeded(services: dict) -> dict:
    """Create seed nodes for test dependencies."""
    ns = services["node"]
    ns.create({"node_id": "HAMLET", "labels": {"en": "Hamlet"}})
    ns.create({"node_id": "SHAKESPEARE", "labels": {"en": "William Shakespeare"}})
    ns.create({"node_id": "ACT_3", "labels": {"en": "Act 3"}})
    return services


# ── Helper unit tests ─────────────────────────────────────────────────


class TestNextQuoteSequence:
    def test_first_quote(self, services: dict):
        """First quote for a source should return 1."""
        ns = services["node"]
        ns.create({"node_id": "HAMLET", "labels": {"en": "Hamlet"}})
        seq = node_quote._next_quote_sequence(services, "HAMLET")
        assert seq == 1

    def test_sequential_quotes(self, services: dict):
        """Quotes should get sequential numbers."""
        ns = services["node"]
        ns.create({"node_id": "HAMLET", "labels": {"en": "Hamlet"}})
        ns.create({"node_id": "HAMLET_QUOTE_1", "labels": {"en": "First quote"}})
        ns.create({"node_id": "HAMLET_QUOTE_2", "labels": {"en": "Second quote"}})
        seq = node_quote._next_quote_sequence(services, "HAMLET")
        assert seq == 3

    def test_highest_number_wins(self, services: dict):
        """Should pick the highest existing number, not just count."""
        ns = services["node"]
        ns.create({"node_id": "HAMLET", "labels": {"en": "Hamlet"}})
        ns.create({"node_id": "HAMLET_QUOTE_1", "labels": {"en": "Q1"}})
        ns.create({"node_id": "HAMLET_QUOTE_5", "labels": {"en": "Q5"}})
        ns.create({"node_id": "HAMLET_QUOTE_3", "labels": {"en": "Q3"}})
        seq = node_quote._next_quote_sequence(services, "HAMLET")
        assert seq == 6

    def test_no_matching_prefix(self, services: dict):
        """Non-matching IDs should not interfere with the sequence."""
        ns = services["node"]
        ns.create({"node_id": "HAMLET", "labels": {"en": "Hamlet"}})
        ns.create({"node_id": "HAMLET_QUOTE_1", "labels": {"en": "Q1"}})
        ns.create({"node_id": "OTHER_QUOTE_1", "labels": {"en": "Other"}})
        seq = node_quote._next_quote_sequence(services, "HAMLET")
        assert seq == 2

    def test_source_has_no_quotes_yet(self, services: dict):
        """A source with no existing quotes should start at 1."""
        ns = services["node"]
        ns.create({"node_id": "MACBETH", "labels": {"en": "Macbeth"}})
        seq = node_quote._next_quote_sequence(services, "MACBETH")
        assert seq == 1


# ── !node add quote ──────────────────────────────────────────────────


class TestNodeAddQuote:
    def test_quote_basic(self, seeded: dict):
        """Basic quote creation with labels only."""
        result = dispatch(
            ["node", "add", "quote"],
            {"labels": "en::To be or not to be"},
        )
        assert result["type"] == "status"
        assert result["data"]["node"] is not None

    def test_quote_with_source(self, seeded: dict):
        """--source should auto-generate HAMLET_QUOTE_1 ID."""
        result = dispatch(
            ["node", "add", "quote"],
            {"labels": "en::To be", "source": "HAMLET"},
        )
        assert result["data"]["node"]["node_id"] == "HAMLET_QUOTE_1"

    def test_quote_with_sequential_ids(self, seeded: dict):
        """Multiple quotes from same source should get sequential IDs."""
        r1 = dispatch(
            ["node", "add", "quote"],
            {"labels": "en::To be", "source": "HAMLET"},
        )
        assert r1["data"]["node"]["node_id"] == "HAMLET_QUOTE_1"

        r2 = dispatch(
            ["node", "add", "quote"],
            {"labels": "en::Or not to be", "source": "HAMLET"},
        )
        assert r2["data"]["node"]["node_id"] == "HAMLET_QUOTE_2"

    def test_quote_with_attributed_to(self, seeded: dict):
        """--attributed-to should create sm:attributedTo triple."""
        result = dispatch(
            ["node", "add", "quote"],
            {"labels": "en::To be", "source": "HAMLET",
             "attributed-to": "SHAKESPEARE"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(
            t["predicate_id"] == "sm:attributedTo" and t["object_value"] == "SHAKESPEARE"
            for t in triples
        )

    def test_quote_with_chapter(self, seeded: dict):
        """--chapter should create sm:partOf triple."""
        result = dispatch(
            ["node", "add", "quote"],
            {"labels": "en::To be", "source": "HAMLET",
             "chapter": "ACT_3"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(
            t["predicate_id"] == "sm:partOf" and t["object_value"] == "ACT_3"
            for t in triples
        )

    def test_quote_all_fields(self, seeded: dict):
        """Quote with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "quote"],
            {"labels": "en::To be", "source": "HAMLET",
             "chapter": "ACT_3", "attributed-to": "SHAKESPEARE"},
        )
        assert result["type"] == "status"
        assert result["data"]["node"]["node_id"] == "HAMLET_QUOTE_1"
        triples = result["data"].get("semantic_triples", [])
        # rdf:type QUOTE
        assert any(
            t["predicate_id"] == "rdf:type" and t["object_value"] == "QUOTE"
            for t in triples
        )
        # sm:attributedTo
        assert any(
            t["predicate_id"] == "sm:attributedTo" for t in triples
        )
        # sm:partOf (chapter)
        assert any(
            t["predicate_id"] == "sm:partOf" for t in triples
        )
        # sm:hasExcerpt on SOURCE
        assert any(
            t["predicate_id"] == "sm:hasExcerpt"
            and t["subject_id"] == "HAMLET"
            for t in triples
        )

    def test_quote_without_source(self, seeded: dict):
        """Quote without --source uses label-based auto-ID."""
        import re
        result = dispatch(
            ["node", "add", "quote"],
            {"labels": "en::Alone quote"},
        )
        assert result["type"] == "status"
        # Should use a label-derived ID, not the SOURCE_QUOTE_N pattern
        node_id = result["data"]["node"]["node_id"]
        assert not re.match(r"^\w+_QUOTE_\d+$", node_id)

    def test_quote_invalid_source(self, seeded: dict):
        """Quote with unresolvable --source should raise."""
        with pytest.raises(Exception, match="not found"):
            dispatch(
                ["node", "add", "quote"],
                {"labels": "en::Bad quote", "source": "NONEXISTENT"},
            )

    def test_quote_invalid_attributed_to(self, seeded: dict):
        """Quote with unresolvable --attributed-to should raise."""
        with pytest.raises(Exception, match="not found"):
            dispatch(
                ["node", "add", "quote"],
                {"labels": "en::Bad", "attributed-to": "NONEXISTENT"},
            )


# ── Command tree verification ──────────────────────────────────────


class TestQuoteInTree:
    """Verify quote appears in the command tree."""

    def test_tree_has_quote(self):
        from semantika.server.command.registry import get_command_tree
        tree = get_command_tree()
        add_entry = next(c for c in next(
            n for n in tree if n["name"] == "node"
        )["children"] if c["name"] == "add")
        child_names = [c["name"] for c in add_entry.get("children", [])]
        assert "quote" in child_names
