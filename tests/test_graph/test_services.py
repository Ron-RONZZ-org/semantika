"""Tests for the graph module — NodeService, PredicateService, TripleService."""

from __future__ import annotations

import os
import json
import pytest
from pathlib import Path

from semantika.core import SemantikaDB
from semantika.graph.db import SCHEMA, REVIEW_SCHEMA, PROOF_SCHEMA
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.predicate_group_service import PredicateGroupService
from semantika.graph.triple_service import TripleService
from semantika.graph.review_service import ReviewService
from semantika.graph.proof_service import ProofService


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


class TestNodeService:
    def test_create_and_get(self, services: dict):
        ns = services["node"]
        node = ns.create({"node_id": "TEST", "labels": {"en": "Test"}})
        assert node["node_id"] == "TEST"
        assert ns.get("TEST") is not None

    def test_create_with_auto_id(self, services: dict):
        ns = services["node"]
        node = ns.create({"labels": {"en": "Auto"}})
        assert node["node_id"] is not None

    def test_create_duplicate(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "DUP", "labels": {"en": "First"}})
        with pytest.raises(ValueError, match="already exists"):
            ns.create({"node_id": "DUP", "labels": {"en": "Second"}})

    def test_search(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "DOG", "labels": {"en": "Dog"}})
        ns.create({"node_id": "CAT", "labels": {"en": "Cat"}})
        results = ns.search("Dog")
        assert len(results) >= 1
        assert results[0]["node_id"] in ("DOG", "CAT")

    def test_prefix_resolution(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "HELLO_WORLD", "labels": {"en": "Hello"}})
        result = ns.resolve_node_id_prefix("HELLO")
        assert result is not None
        assert result["node_id"] == "HELLO_WORLD"

    def test_update(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "UPD", "labels": {"en": "Original"}})
        ns.update("UPD", {"labels": {"en": "Updated"}})
        assert "Updated" in ns.get("UPD")["label_text"]

    def test_trash_and_restore(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "TRASH", "labels": {"en": "Trash Me"}})
        ns.delete("TRASH", soft=True)
        assert len(ns.list_trash()) == 1
        restored = ns.restore_from_trash("TRASH")
        assert restored is not None
        assert ns.get("TRASH") is not None


class TestPredicateService:
    def test_create_and_get(self, services: dict):
        ps = services["predicate"]
        pred = ps.create({"predicate_id": "rdf:type", "labels": {"en": "type"}})
        assert pred["predicate_id"] == "rdf:type"

    def test_search(self, services: dict):
        ps = services["predicate"]
        ps.create({"predicate_id": "ex:test", "labels": {"en": "test predicate"}})
        results = ps.search("test")
        assert len(results) >= 1


class TestPredicateGroupService:
    def test_create_group(self, services: dict):
        pgs = services["predicate_group"]
        group = pgs.create({"group_name": "basic"})
        assert group["group_name"] == "basic"

    def test_add_member(self, services: dict):
        pgs = services["predicate_group"]
        ps = services["predicate"]
        ps.create({"predicate_id": "ex:p1", "labels": {"en": "p1"}})
        group = pgs.create({"group_name": "g1"})
        member = pgs.add_member(group["uuid"], "ex:p1")
        assert member["predicate_id"] == "ex:p1"
        members = pgs.list_members(group["uuid"])
        assert len(members) == 1


class TestTripleService:
    def test_add_and_query(self, services: dict):
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "S", "labels": {"en": "Subject"}})
        ns.create({"node_id": "O", "labels": {"en": "Object"}})
        ps.create({"predicate_id": "ex:rel", "labels": {"en": "relation"}})

        triple = ts.add("S", "ex:rel", "O", object_type="uri")
        assert triple["subject_id"] == "S"

        results = ts.get_by_subject("S")
        assert len(results) == 1

    def test_add_literal(self, services: dict):
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "S", "labels": {"en": "S"}})
        ps.create({"predicate_id": "ex:label", "labels": {"en": "label"}})

        triple = ts.add("S", "ex:label", "Hello World", object_type="literal", object_lang="en")
        assert triple["object_type"] == "literal"

    def test_remove(self, services: dict):
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "S", "labels": {"en": "S"}})
        ns.create({"node_id": "O", "labels": {"en": "O"}})
        ps.create({"predicate_id": "ex:p", "labels": {"en": "p"}})

        ts.add("S", "ex:p", "O", object_type="uri")
        assert ts.count() == 1
        ts.remove("S", "ex:p", "O")
        assert ts.count() == 0  # triple was deleted

    def test_turtle_export(self, services: dict):
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "DOG", "labels": {"en": "Dog"}})
        ns.create({"node_id": "ANIMAL", "labels": {"en": "Animal"}})
        ps.create({"predicate_id": "rdf:type", "labels": {"en": "type"}})
        ts.add("DOG", "rdf:type", "ANIMAL", object_type="uri")

        ttl = ts.export_turtle()
        assert "@prefix" in ttl
        assert "rdf:type" in ttl
        assert "DOG" in ttl

    def test_get_by_nodes_bulk(self, services: dict):
        ns = services["node"]
        ts = services["triple"]
        ps = services["predicate"]

        for nid in ["A", "B", "C"]:
            ns.create({"node_id": nid, "labels": {"en": nid}})
        ps.create({"predicate_id": "ex:rel", "labels": {"en": "rel"}})
        ts.add("A", "ex:rel", "B", object_type="uri")
        ts.add("B", "ex:rel", "C", object_type="uri")

        results = ts.get_by_nodes(["A", "B"])
        assert len(results) == 2

    def test_stats(self, services: dict):
        stats = services["triple"].get_stats()
        assert "nodes" in stats
        assert "predicates" in stats
        assert "triples" in stats


class TestReviewService:
    def test_create_session(self, services: dict):
        # Need at least one triple for a session
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        ns.create({"node_id": "X", "labels": {"en": "X"}})
        ps.create({"predicate_id": "ex:p", "labels": {"en": "p"}})
        # No triple referencing X as object — create with URI pointing to self
        ts.add("X", "ex:p", "X", object_type="uri")

        rs = services["review"]
        session = rs.create_session()
        assert "session" in session


class TestProofService:
    def test_create_and_query(self, services: dict):
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        prs = services["proof"]

        ns.create({"node_id": "X", "labels": {"en": "X"}})
        ns.create({"node_id": "Y", "labels": {"en": "Y"}})
        ps.create({"predicate_id": "ex:p", "labels": {"en": "p"}})
        ts.add("X", "ex:p", "Y", object_type="uri")

        proof = prs.create({
            "subject_id": "X",
            "predicate_id": "ex:p",
            "object_value": "Y",
            "proof_type": "observation",
            "source": "test",
        })
        assert proof["uuid"] is not None

        proofs = prs.get_by_triple("X", "ex:p", "Y")
        assert len(proofs) == 1
