"""Tests for ProofService — evidence/proof management for triples.

Tests cover:
- Creating proofs with various field combinations (minimal, all fields)
- Querying proofs by triple (subject, predicate, object)
- Querying proofs by subject
- Deleting individual proofs
- Cascade-deleting proofs for a triple
- Batch querying proofs for multiple arcs
- Edge cases: empty results, nonexistent proofs, partial matches

Each test creates an isolated SQLite database and sets up the
necessary node/predicate/triple infrastructure.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from semantika.core import SemantikaDB
from semantika.graph.db import SCHEMA, PROOF_SCHEMA, TRIPLES_INDEXES
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.triple_service import TripleService
from semantika.graph.proof_service import ProofService


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> SemantikaDB:
    """Create an isolated test database with graph + proof schema."""
    db_path = tmp_path / "test.db"
    db = SemantikaDB(db_path)
    for table, sql in SCHEMA.items():
        db.init_schema({table: sql})
    for idx in TRIPLES_INDEXES:
        db.execute(idx)
    for table, sql in PROOF_SCHEMA.items():
        db.init_schema({table: sql})
    db.execute("PRAGMA foreign_keys=ON")
    return db


@pytest.fixture
def node_svc(db: SemantikaDB) -> NodeService:
    return NodeService(db)


@pytest.fixture
def pred_svc(db: SemantikaDB) -> PredicateService:
    return PredicateService(db)


@pytest.fixture
def triple_svc(
    db: SemantikaDB,
    node_svc: NodeService,
    pred_svc: PredicateService,
) -> TripleService:
    """TripleService with basic predicates and nodes seeded."""
    # Seed predicates
    for pid, source, labels in [
        ("ex:bornIn", "manual", {"en": "born in"}),
        ("ex:knows", "manual", {"en": "knows"}),
        ("ex:worksAt", "manual", {"en": "works at"}),
        ("rdf:type", "rdf", {"en": "type"}),
    ]:
        pred_svc.create({"predicate_id": pid, "labels": labels})
    return TripleService(db)


@pytest.fixture
def proof_svc(db: SemantikaDB) -> ProofService:
    return ProofService(db)


@pytest.fixture
def svc(
    node_svc: NodeService,
    pred_svc: PredicateService,
    triple_svc: TripleService,
    proof_svc: ProofService,
) -> dict:
    """Convenience dict of all services."""
    return {
        "node": node_svc,
        "predicate": pred_svc,
        "triple": triple_svc,
        "proof": proof_svc,
    }


def _create_nodes(svc: dict, *node_ids: str) -> None:
    """Create node entries for the given node_ids."""
    ns = svc["node"]
    for nid in node_ids:
        ns.create({"node_id": nid, "labels": {"en": nid}})


def _add_triple(svc: dict, s: str, p: str, o: str) -> dict:
    """Add a URI triple and return it."""
    return svc["triple"].add(s, p, o, object_type="uri")


# ── Tests ────────────────────────────────────────────────────────────────


class TestProofServiceCreate:
    """Tests for ProofService.create()."""

    def test_create_minimal(self, svc: dict):
        """Create a proof with only required fields."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        proof = svc["proof"].create({
            "subject_id": "A",
            "predicate_id": "ex:knows",
            "object_value": "B",
        })
        assert proof["uuid"] is not None
        assert proof["subject_id"] == "A"
        assert proof["predicate_id"] == "ex:knows"
        assert proof["object_value"] == "B"
        # Defaults
        assert proof["object_type"] == "uri"
        assert proof["proof_type"] == "observation"
        assert proof["source"] == ""
        assert proof["notes"] == ""
        assert proof["created_at"] is not None

    def test_create_with_all_fields(self, svc: dict):
        """Create a proof with all optional fields."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        proof = svc["proof"].create({
            "subject_id": "A",
            "predicate_id": "ex:knows",
            "object_value": "B",
            "object_type": "literal",
            "proof_type": "document",
            "source": "https://example.com/doc",
            "notes": "Found in official records",
        })
        assert proof["uuid"] is not None
        assert proof["object_type"] == "literal"
        assert proof["proof_type"] == "document"
        assert proof["source"] == "https://example.com/doc"
        assert proof["notes"] == "Found in official records"

    def test_create_returns_copy(self, svc: dict):
        """The returned dict is independent of the stored row."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        data = {
            "subject_id": "A",
            "predicate_id": "ex:knows",
            "object_value": "B",
        }
        proof = svc["proof"].create(data)
        # Mutating the returned dict shouldn't affect the DB
        proof["proof_type"] = "changed"
        stored = svc["proof"].get_by_triple("A", "ex:knows", "B")
        assert stored[0]["proof_type"] == "observation"

    def test_create_multiple_proofs_same_triple(self, svc: dict):
        """Multiple proofs can be attached to the same triple."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        p1 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B", "proof_type": "observation",
        })
        p2 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B", "proof_type": "document",
        })
        assert p1["uuid"] != p2["uuid"]
        proofs = svc["proof"].get_by_triple("A", "ex:knows", "B")
        assert len(proofs) == 2


class TestProofServiceQuery:
    """Tests for query methods: get_by_triple, get_by_subject."""

    def test_get_by_triple(self, svc: dict):
        """get_by_triple returns proofs for a matching triple."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B", "proof_type": "observation",
        })
        proofs = svc["proof"].get_by_triple("A", "ex:knows", "B")
        assert len(proofs) == 1
        assert proofs[0]["proof_type"] == "observation"

    def test_get_by_triple_empty(self, svc: dict):
        """get_by_triple returns empty list when no proofs exist."""
        proofs = svc["proof"].get_by_triple("A", "ex:knows", "B")
        assert proofs == []

    def test_get_by_triple_wrong_predicate(self, svc: dict):
        """get_by_triple only returns proofs matching exactly."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        proofs = svc["proof"].get_by_triple("A", "ex:bornIn", "B")
        assert proofs == []

    def test_get_by_triple_orders_by_date_desc(self, svc: dict):
        """Results are ordered by created_at DESC (most recent first)."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        # Second proof will have a later timestamp
        import time
        time.sleep(0.01)
        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B", "proof_type": "document",
        })
        proofs = svc["proof"].get_by_triple("A", "ex:knows", "B")
        assert len(proofs) == 2
        # Most recent (document) should be first
        assert proofs[0]["proof_type"] == "document"

    def test_get_by_subject(self, svc: dict):
        """get_by_subject returns all proofs for triples with the given subject."""
        _create_nodes(svc, "S1", "O1", "O2")
        _add_triple(svc, "S1", "ex:knows", "O1")
        _add_triple(svc, "S1", "ex:worksAt", "O2")

        svc["proof"].create({
            "subject_id": "S1", "predicate_id": "ex:knows",
            "object_value": "O1",
        })
        svc["proof"].create({
            "subject_id": "S1", "predicate_id": "ex:worksAt",
            "object_value": "O2",
        })
        results = svc["proof"].get_by_subject("S1")
        assert len(results) == 2

    def test_get_by_subject_empty(self, svc: dict):
        """get_by_subject returns empty list when no proofs exist."""
        results = svc["proof"].get_by_subject("NONEXISTENT")
        assert results == []

    def test_get_by_subject_filters_by_subject(self, svc: dict):
        """get_by_subject only returns proofs for the given subject, not all."""
        _create_nodes(svc, "A", "B", "C")
        _add_triple(svc, "A", "ex:knows", "B")
        _add_triple(svc, "C", "ex:knows", "B")

        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        svc["proof"].create({
            "subject_id": "C", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        results = svc["proof"].get_by_subject("A")
        assert len(results) == 1
        assert results[0]["subject_id"] == "A"


class TestProofServiceDelete:
    """Tests for ProofService.delete()."""

    def test_delete_existing_proof(self, svc: dict):
        """Deleting an existing proof removes it from the DB."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        proof = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        svc["proof"].delete(proof["uuid"])
        remaining = svc["proof"].get_by_triple("A", "ex:knows", "B")
        assert remaining == []

    def test_delete_nonexistent_does_not_raise(self, svc: dict):
        """Deleting a nonexistent UUID should not raise an error."""
        svc["proof"].delete("00000000-0000-0000-0000-000000000000")
        # No exception means success

    def test_delete_only_removes_target(self, svc: dict):
        """Deleting one proof does not affect other proofs on the same triple."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        p1 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        p2 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        svc["proof"].delete(p1["uuid"])
        remaining = svc["proof"].get_by_triple("A", "ex:knows", "B")
        assert len(remaining) == 1
        assert remaining[0]["uuid"] == p2["uuid"]

    def test_delete_returns_false_for_missing(self, svc: dict):
        """delete returns False when UUID does not exist."""
        result = svc["proof"].delete("00000000-0000-0000-0000-000000000000")
        assert result is False

    def test_delete_returns_true_for_existing(self, svc: dict):
        """delete returns True when a row was actually deleted."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")
        p = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows", "object_value": "B",
        })
        result = svc["proof"].delete(p["uuid"])
        assert result is True


class TestProofServiceCascadeDelete:
    """Tests for cascade_delete_proofs()."""

    def test_cascade_delete_all_for_triple(self, svc: dict):
        """cascade_delete_proofs removes all proofs for the given triple."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        count = svc["proof"].cascade_delete_proofs("A", "ex:knows", "B")
        assert count == 2
        remaining = svc["proof"].get_by_triple("A", "ex:knows", "B")
        assert remaining == []

    def test_cascade_delete_returns_zero_when_empty(self, svc: dict):
        """cascade_delete_proofs returns 0 when no proofs exist."""
        count = svc["proof"].cascade_delete_proofs("A", "ex:p", "B")
        assert count == 0

    def test_cascade_delete_only_target_triple(self, svc: dict):
        """Cascade only deletes proofs for the matching triple, not others."""
        _create_nodes(svc, "A", "B", "C")
        _add_triple(svc, "A", "ex:knows", "B")
        _add_triple(svc, "A", "ex:knows", "C")

        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "C",
        })
        count = svc["proof"].cascade_delete_proofs("A", "ex:knows", "B")
        assert count == 1
        remaining = svc["proof"].get_by_triple("A", "ex:knows", "C")
        assert len(remaining) == 1  # Unaffected


class TestProofServiceBatch:
    """Tests for get_proofs_for_arcs_batch()."""

    def test_batch_returns_matching_proofs(self, svc: dict):
        """Batch query returns proofs keyed by arc (s, p, o)."""
        _create_nodes(svc, "A", "B", "C")
        _add_triple(svc, "A", "ex:knows", "B")
        _add_triple(svc, "A", "ex:knows", "C")

        p1 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        _ = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "C",
        })

        arcs = [("A", "ex:knows", "B"), ("A", "ex:knows", "C")]
        result = svc["proof"].get_proofs_for_arcs_batch(arcs)
        assert len(result) == 2
        assert ("A", "ex:knows", "B") in result
        assert ("A", "ex:knows", "C") in result
        # Check UUID was captured
        assert p1["uuid"] in result[("A", "ex:knows", "B")]

    def test_batch_empty_input(self, svc: dict):
        """Empty arc list returns empty dict."""
        result = svc["proof"].get_proofs_for_arcs_batch([])
        assert result == {}

    def test_batch_partial_matches(self, svc: dict):
        """Only arcs that have proofs appear in the result."""
        _create_nodes(svc, "A", "B", "C")
        _add_triple(svc, "A", "ex:knows", "B")
        _add_triple(svc, "A", "ex:knows", "C")

        svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })

        arcs = [("A", "ex:knows", "B"), ("A", "ex:knows", "C"), ("A", "ex:worksAt", "D")]
        result = svc["proof"].get_proofs_for_arcs_batch(arcs)
        assert ("A", "ex:knows", "B") in result
        assert ("A", "ex:knows", "C") not in result
        assert ("A", "ex:worksAt", "D") not in result
        assert len(result) == 1

    def test_batch_multiple_proofs_per_arc(self, svc: dict):
        """An arc with multiple proofs lists all UUIDs."""
        _create_nodes(svc, "A", "B")
        _add_triple(svc, "A", "ex:knows", "B")

        p1 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B", "proof_type": "observation",
        })
        p2 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B", "proof_type": "document",
        })

        arcs = [("A", "ex:knows", "B")]
        result = svc["proof"].get_proofs_for_arcs_batch(arcs)
        uuids = result[("A", "ex:knows", "B")]
        assert len(uuids) == 2
        assert p1["uuid"] in uuids
        assert p2["uuid"] in uuids


class TestProofServiceLifecycle:
    """End-to-end lifecycle: create → query → delete → verify."""

    def test_create_query_delete_query(self, svc: dict):
        """Full lifecycle: create, verify, delete, verify gone."""
        _create_nodes(svc, "X", "Y")
        _add_triple(svc, "X", "ex:knows", "Y")

        # Create
        proof = svc["proof"].create({
            "subject_id": "X", "predicate_id": "ex:knows",
            "object_value": "Y", "source": "test",
        })
        uuid = proof["uuid"]

        # Query
        proofs = svc["proof"].get_by_triple("X", "ex:knows", "Y")
        assert len(proofs) == 1
        assert proofs[0]["uuid"] == uuid

        # Delete
        svc["proof"].delete(uuid)

        # Query — should be empty
        proofs = svc["proof"].get_by_triple("X", "ex:knows", "Y")
        assert proofs == []

    def test_multiple_triples_independent_proofs(self, svc: dict):
        """Proofs on different triples are independent."""
        _create_nodes(svc, "A", "B", "C")
        _add_triple(svc, "A", "ex:knows", "B")
        _add_triple(svc, "A", "ex:knows", "C")

        p1 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "B",
        })
        p2 = svc["proof"].create({
            "subject_id": "A", "predicate_id": "ex:knows",
            "object_value": "C",
        })

        # Delete only p1
        svc["proof"].delete(p1["uuid"])
        assert svc["proof"].get_by_triple("A", "ex:knows", "B") == []
        assert len(svc["proof"].get_by_triple("A", "ex:knows", "C")) == 1
        assert svc["proof"].get_by_triple("A", "ex:knows", "C")[0]["uuid"] == p2["uuid"]

    def test_create_with_different_object_types(self, svc: dict):
        """Proofs can reference literal-valued triples too."""
        # For literal triples, we still need a node and predicate
        _create_nodes(svc, "A")
        svc["triple"].add("A", "ex:bornIn", "Paris", object_type="literal")

        proof = svc["proof"].create({
            "subject_id": "A",
            "predicate_id": "ex:bornIn",
            "object_value": "Paris",
            "object_type": "literal",
            "proof_type": "citation",
        })
        assert proof["uuid"] is not None
        assert proof["object_type"] == "literal"
