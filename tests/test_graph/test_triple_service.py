"""Tests for TripleService — triple CRUD, Turtle export/import, stats."""

from __future__ import annotations


class TestTripleService:
    def test_add_and_query(self, services: dict):
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]

        ns.create({"node_id": "S", "labels": {"en": "Subject"}})
        ns.create({"node_id": "O", "labels": {"en": "Object"}})
        ps.create({"predicate_id": "ex:rel", "labels": {"en": "relation"}})

        triple = ts.add("S", "ex:rel", "O", object_type="node")
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

        ts.add("S", "ex:p", "O", object_type="node")
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
        ts.add("DOG", "rdf:type", "ANIMAL", object_type="node")

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
        ts.add("A", "ex:rel", "B", object_type="node")
        ts.add("B", "ex:rel", "C", object_type="node")

        results = ts.get_by_nodes(["A", "B"])
        assert len(results) == 2

    def test_stats(self, services: dict):
        stats = services["triple"].get_stats()
        assert "nodes" in stats
        assert "predicates" in stats
        assert "triples" in stats


class TestTurtleEdgeCases:
    """Tests for Turtle import/export edge cases."""

    def test_import_simple_turtle(self, services: dict):
        """Import a minimal Turtle graph."""
        from semantika.graph.triple_turtle import import_turtle

        ttl = (
            "@prefix ex: <http://example.org/> .\n"
            "ex:Subject ex:predicate \"literal value\" .\n"
        )
        stats = import_turtle(ttl)
        assert isinstance(stats, dict)
        assert "nodes_created" in stats
        assert "triples_added" in stats

    def test_export_basic(self, services: dict):
        """Export Turtle includes triples."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        ns.create({"node_id": "TURTLE_SUB", "labels": {"en": "Turtle sub"}})
        ps.create({"predicate_id": "ex:hasLabel"})
        ts.add("TURTLE_SUB", "ex:hasLabel", "test label", object_type="literal")

        ttl = ts.export_turtle()
        assert "@prefix" in ttl
        assert "TURTLE_SUB" in ttl or "turtle_sub" in ttl.lower()

    def test_import_blank_nodes_handled(self, services: dict):
        """Blank nodes in Turtle are handled without error."""
        from semantika.graph.triple_turtle import import_turtle

        ttl = (
            "@prefix ex: <http://example.org/> .\n"
            "[] ex:predicate \"blank subject\" .\n"
            "ex:S ex:predicate [] .\n"
        )
        stats = import_turtle(ttl)
        # Should not crash; blank nodes are handled as URIs
        assert isinstance(stats, dict)


class TestTripleBatchAdd:
    """Tests for TripleService.batch_add()."""

    def _setup(self, services: dict) -> dict:
        """Create basic nodes and predicates for batch tests."""
        ns = services["node"]
        ps = services["predicate"]
        ns.create({"node_id": "ALICE", "labels": {"en": "Alice"}})
        ns.create({"node_id": "BOB", "labels": {"en": "Bob"}})
        ns.create({"node_id": "CHARLIE", "labels": {"en": "Charlie"}})
        ps.create({"predicate_id": "ex:knows", "labels": {"en": "knows"}})
        ps.create({"predicate_id": "ex:likes", "labels": {"en": "likes"}})
        ps.create({"predicate_id": "ex:age", "labels": {"en": "age"}})
        return services

    def test_batch_all_created(self, services: dict):
        """All valid triples are created."""
        svc = self._setup(services)
        ts = svc["triple"]
        results = ts.batch_add([
            {"subject_id": "ALICE", "predicate_id": "ex:knows", "object_value": "BOB"},
            {"subject_id": "ALICE", "predicate_id": "ex:likes", "object_value": "CHARLIE"},
            {"subject_id": "BOB", "predicate_id": "ex:knows", "object_value": "CHARLIE"},
        ])
        assert len(results) == 3
        assert all(r["status"] == "created" for r in results)
        assert ts.count() == 3

    def test_batch_duplicates(self, services: dict):
        """Re-adding existing triples reports them as duplicates."""
        svc = self._setup(services)
        ts = svc["triple"]
        ts.add("ALICE", "ex:knows", "BOB", object_type="node")
        results = ts.batch_add([
            {"subject_id": "ALICE", "predicate_id": "ex:knows", "object_value": "BOB"},
            {"subject_id": "ALICE", "predicate_id": "ex:likes", "object_value": "CHARLIE"},
        ])
        assert len(results) == 2
        assert results[0]["status"] == "duplicate"
        assert results[1]["status"] == "created"
        assert ts.count() == 2

    def test_batch_skips_empty_rows(self, services: dict):
        """Completely empty rows are skipped."""
        svc = self._setup(services)
        ts = svc["triple"]
        results = ts.batch_add([
            {"subject_id": "ALICE", "predicate_id": "ex:knows", "object_value": "BOB"},
            {"subject_id": "", "predicate_id": "", "object_value": ""},
            {"subject_id": "BOB", "predicate_id": "ex:likes", "object_value": "CHARLIE"},
        ])
        assert len(results) == 3
        assert results[0]["status"] == "created"
        assert results[1]["status"] == "skipped"
        assert results[2]["status"] == "created"
        assert ts.count() == 2

    def test_batch_mixed_success_and_error(self, services: dict):
        """Some rows succeed, some fail with error."""
        svc = self._setup(services)
        ts = svc["triple"]
        results = ts.batch_add([
            {"subject_id": "ALICE", "predicate_id": "ex:knows", "object_value": "BOB"},
            {"subject_id": "ALICE", "predicate_id": "ex:nonexistent", "object_value": "BOB"},
        ])
        assert len(results) == 2
        assert results[0]["status"] == "created"
        assert results[1]["status"] == "error"
        assert ts.count() == 1

    def test_batch_row_key_correlation(self, services: dict):
        """Custom _row keys correlate frontend rows."""
        svc = self._setup(services)
        ts = svc["triple"]
        results = ts.batch_add([
            {"_row": 5, "subject_id": "ALICE", "predicate_id": "ex:knows", "object_value": "BOB"},
            {"_row": 8, "subject_id": "BOB", "predicate_id": "ex:likes", "object_value": "CHARLIE"},
        ])
        assert results[0]["row"] == 5
        assert results[1]["row"] == 8
