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

    def test_search_empty_query(self, services: dict):
        """Empty search query falls back to list."""
        ns = services["node"]
        ns.create({"node_id": "ANY", "labels": {"en": "Anything"}})
        results = ns.search("")
        assert len(results) >= 1

    def test_prefix_resolution(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "HELLO_WORLD", "labels": {"en": "Hello"}})
        result = ns.resolve_node_id_prefix("HELLO")
        assert result is not None
        assert result["node_id"] == "HELLO_WORLD"

    def test_prefix_resolution_ambiguous(self, services: dict):
        """Multiple matches raise AmbiguousIDError."""
        from semantika.core.exceptions import AmbiguousIDError
        ns = services["node"]
        ns.create({"node_id": "HELLO_WORLD", "labels": {"en": "Hello"}})
        ns.create({"node_id": "HELLO_THERE", "labels": {"en": "Hi"}})
        with pytest.raises(AmbiguousIDError):
            ns.resolve_node_id_prefix("HELLO")

    def test_prefix_resolution_not_found(self, services: dict):
        """No match returns None."""
        ns = services["node"]
        assert ns.resolve_node_id_prefix("NONEXISTENT") is None

    def test_update(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "UPD", "labels": {"en": "Original"}})
        ns.update("UPD", {"labels": {"en": "Updated"}})
        assert "Updated" in ns.get("UPD")["label_text"]

    def test_update_with_definitions(self, services: dict):
        """Update with definitions dict."""
        ns = services["node"]
        ns.create({"node_id": "UPDDEF", "labels": {"en": "Def"}})
        ns.update("UPDDEF", {"definitions": {"en": "A definition"}})
        node = ns.get("UPDDEF")
        assert node is not None
        assert "definition" in node.get("definition_text", "")

    def test_update_not_found(self, services: dict):
        """Updating nonexistent node raises ValueError."""
        ns = services["node"]
        with pytest.raises(ValueError, match="not found"):
            ns.update("NONEXISTENT", {"labels": {"en": "Oops"}})

    def test_trash_and_restore(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "TRASH", "labels": {"en": "Trash Me"}})
        ns.delete("TRASH", soft=True)
        assert len(ns.list_trash()) == 1
        restored = ns.restore_from_trash("TRASH")
        assert restored is not None
        assert ns.get("TRASH") is not None

    def test_soft_delete_twice(self, services: dict):
        """Soft-deleting an already deleted node returns False."""
        ns = services["node"]
        ns.create({"node_id": "SD2", "labels": {"en": "Soft Del"}})
        ns.delete("SD2", soft=True)
        result = ns.delete("SD2", soft=True)
        assert result is False

    def test_restore_nonexistent(self, services: dict):
        """Restoring a node that was never trashed returns None."""
        ns = services["node"]
        assert ns.restore_from_trash("NONEXISTENT") is None

    def test_list_empty(self, services: dict):
        """list returns at least auto-created nodes."""
        results = services["node"].list()
        assert isinstance(results, list)


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

    def test_get_by_subject(self, services: dict):
        prs = services["proof"]
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "S1", "labels": {"en": "S1"}})
        ns.create({"node_id": "O1", "labels": {"en": "O1"}})
        ps.create({"predicate_id": "ex:rel", "labels": {"en": "rel"}})
        ts.add("S1", "ex:rel", "O1", object_type="uri")

        prs.create({"subject_id": "S1", "predicate_id": "ex:rel",
                    "object_value": "O1", "proof_type": "observation"})
        results = prs.get_by_subject("S1")
        assert len(results) == 1

    def test_delete_proof(self, services: dict):
        prs = services["proof"]
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "S", "labels": {"en": "S"}})
        ns.create({"node_id": "O", "labels": {"en": "O"}})
        ps.create({"predicate_id": "ex:p", "labels": {"en": "p"}})
        ts.add("S", "ex:p", "O", object_type="uri")

        proof = prs.create({"subject_id": "S", "predicate_id": "ex:p",
                            "object_value": "O", "proof_type": "test"})
        prs.delete(proof["uuid"])
        proofs = prs.get_by_triple("S", "ex:p", "O")
        assert len(proofs) == 0

    def test_cascade_delete_proofs(self, services: dict):
        prs = services["proof"]
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "S", "labels": {"en": "S"}})
        ns.create({"node_id": "O", "labels": {"en": "O"}})
        ps.create({"predicate_id": "ex:p", "labels": {"en": "p"}})
        ts.add("S", "ex:p", "O", object_type="uri")

        prs.create({"subject_id": "S", "predicate_id": "ex:p",
                    "object_value": "O", "proof_type": "test"})
        count = prs.cascade_delete_proofs("S", "ex:p", "O")
        assert count >= 1

    def test_get_proofs_for_arcs_batch(self, services: dict):
        prs = services["proof"]
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "A", "labels": {"en": "A"}})
        ns.create({"node_id": "B", "labels": {"en": "B"}})
        ns.create({"node_id": "C", "labels": {"en": "C"}})
        ps.create({"predicate_id": "ex:rel", "labels": {"en": "rel"}})
        ts.add("A", "ex:rel", "B", object_type="uri")
        ts.add("A", "ex:rel", "C", object_type="uri")

        p1 = prs.create({"subject_id": "A", "predicate_id": "ex:rel",
                         "object_value": "B", "proof_type": "obs"})
        prs.create({"subject_id": "A", "predicate_id": "ex:rel",
                    "object_value": "C", "proof_type": "obs"})

        arcs = [("A", "ex:rel", "B"), ("A", "ex:rel", "C")]
        result = prs.get_proofs_for_arcs_batch(arcs)
        assert len(result) == 2
        assert ("A", "ex:rel", "B") in result

    def test_get_proofs_for_arcs_batch_empty(self, services: dict):
        prs = services["proof"]
        assert prs.get_proofs_for_arcs_batch([]) == {}


class TestUnitService:
    def test_seeded_units(self, services: dict, db):
        from semantika.graph.unit_service import UnitService
        us = UnitService(db, services["node"], services["triple"])
        units = us.list_units()
        assert len(units) > 0

    def test_get_unit_info(self, services: dict, db):
        from semantika.graph.unit_service import UnitService
        us = UnitService(db, services["node"], services["triple"])
        info = us.get_unit_info("unit:METER")
        assert info is not None
        assert info.get("unit_symbol") == "m"

    def test_resolve_singleton(self, services: dict, db):
        from semantika.graph.unit_service import UnitService
        us = UnitService(db, services["node"], services["triple"])
        nid = us.resolve_unit("J")
        assert nid == "unit:JOULE"

    def test_resolve_compound(self, services: dict, db):
        from semantika.graph.unit_service import UnitService
        us = UnitService(db, services["node"], services["triple"])
        nid = us.resolve_unit("J/K")
        assert nid is not None
        assert "JOULE" in nid

    def test_create_singleton(self, services: dict, db):
        from semantika.graph.unit_service import UnitService
        us = UnitService(db, services["node"], services["triple"])
        nid = us.create_singleton("TESTUNIT", "Test Unit", "tu")
        assert nid == "unit:TESTUNIT"
        # Verify it's listed
        ids = [u["node_id"] for u in us.list_units()]
        assert "unit:TESTUNIT" in ids
