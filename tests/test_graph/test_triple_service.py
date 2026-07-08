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
