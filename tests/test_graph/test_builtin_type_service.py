"""Tests for BuiltinTypeService — lazy seeding, predicate/type node creation."""

from __future__ import annotations

import json

import pytest

from semantika.graph.builtin_seed_data import BUILTIN_PREDICATES, BUILTIN_TYPE_NODES, REQUIRED_PREDICATES


class TestBuiltinSeedData:
    """Verify seed data constants are well-formed."""

    def test_type_nodes_have_required_keys(self):
        for node in BUILTIN_TYPE_NODES:
            assert "node_id" in node
            assert node["node_id"].startswith("sm:")
            assert "labels" in node
            assert "en" in node["labels"]
            assert "eo" in node["labels"]

    def test_predicates_have_required_fields(self):
        for pid, source, labels, descriptions in BUILTIN_PREDICATES:
            assert pid.startswith("sm:")
            assert source == "semantika"
            assert "en" in labels
            assert "en" in descriptions

    def test_required_predicates_includes_builtin_plus_file_preds(self):
        for pid, _, _, _ in BUILTIN_PREDICATES:
            assert pid in REQUIRED_PREDICATES
        assert ":hasFilePath" in REQUIRED_PREDICATES
        assert ":hasFileMime" in REQUIRED_PREDICATES


class TestBuiltinTypeService:
    """Test lazy seeding and predicate ensuring."""

    def test_ensure_builtins_creates_predicates(self, services: dict):
        bts = services["builtin_type"]
        bts.ensure_builtins()

        for pid, _, _, _ in BUILTIN_PREDICATES:
            pred = services["predicate"].get(pid)
            assert pred is not None, f"Predicate {pid} should exist"

    def test_ensure_builtins_creates_type_nodes(self, services: dict):
        bts = services["builtin_type"]
        bts.ensure_builtins()

        for node in BUILTIN_TYPE_NODES:
            n = services["node"].get(node["node_id"])
            assert n is not None, f"Type node {node['node_id']} should exist"
            labels = json.loads(n["labels"]) if isinstance(n["labels"], str) else n["labels"]
            assert labels.get("en") == node["labels"]["en"]

    def test_ensure_builtins_creates_rdf_type_triples(self, services: dict):
        bts = services["builtin_type"]
        bts.ensure_builtins()

        for node in BUILTIN_TYPE_NODES:
            triples = services["triple"].get_by_subject(node["node_id"])
            type_triples = [
                t for t in triples
                if t["predicate_id"] == "rdf:type" and t["object_value"] == node["node_id"]
            ]
            assert len(type_triples) >= 1, (
                f"Type node {node['node_id']} should have rdf:type self-reference"
            )

    def test_ensure_builtins_idempotent(self, services: dict):
        """Calling ensure_builtins twice does not duplicate data."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        bts.ensure_builtins()  # second call

        for pid, _, _, _ in BUILTIN_PREDICATES:
            pred = services["predicate"].get(pid)
            assert pred is not None
        for node in BUILTIN_TYPE_NODES:
            n = services["node"].get(node["node_id"])
            assert n is not None

    def test_ensure_predicates_creates_missing(self, services: dict):
        """ensure_predicates creates a predicate if it doesn't exist."""
        bts = services["builtin_type"]
        bts.ensure_predicates(["test:customPred"])

        pred = services["predicate"].get("test:customPred")
        assert pred is not None

    def test_ensure_predicates_skips_existing(self, services: dict):
        """ensure_predicates does not error if predicate already exists."""
        services["predicate"].create({"predicate_id": "ex:existingPred"})
        bts = services["builtin_type"]
        bts.ensure_predicates(["ex:existingPred"])  # should not raise

    def test_get_type_node_id(self, services: dict):
        bts = services["builtin_type"]
        assert bts.get_type_node_id("photo") == "sm:Photo"
        assert bts.get_type_node_id("video") == "sm:Video"
        assert bts.get_type_node_id("file") == "sm:Document"
        assert bts.get_type_node_id("code") == "sm:SourceCode"
        assert bts.get_type_node_id("unknown") is None
