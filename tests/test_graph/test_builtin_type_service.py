"""Tests for BuiltinTypeService — lazy seeding, predicate/type node creation."""

from __future__ import annotations

import json

import pytest

from semantika.graph.builtin_seed_data import (
    BUILTIN_PREDICATES,
    BUILTIN_TYPE_NODES,
    FILE_PREDICATES,
    REQUIRED_PREDICATES,
    SEED_PREDICATES,
    TIER1_SM_PREDICATES,
    TIER2_SM_PREDICATES,
    W3C_PREDICATES,
)
from semantika.graph.constants import KNOWN_PREFIXES


class TestBuiltinSeedData:
    """Verify seed data constants are well-formed."""

    def test_type_nodes_have_required_keys(self):
        for node in BUILTIN_TYPE_NODES:
            assert "node_id" in node
            # Concept type nodes are all-caps A-Z0-9_ (no prefix)
            assert node["node_id"].isupper() or "_" in node["node_id"]
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
        assert bts.get_type_node_id("photo") == "PHOTO"
        assert bts.get_type_node_id("video") == "VIDEO"
        assert bts.get_type_node_id("file") == "DOCUMENT"
        assert bts.get_type_node_id("code") == "SOURCE_CODE"
        assert bts.get_type_node_id("unknown") is None

    def test_ensure_builtins_creates_all_w3c_predicates(self, services: dict):
        """ensure_builtins seeds all W3C predicates (rdf:/rdfs:/owl:)."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        for pid, _, _, _ in W3C_PREDICATES:
            pred = services["predicate"].get(pid)
            assert pred is not None, f"W3C predicate {pid} should exist"

    def test_ensure_builtins_creates_all_file_predicates(self, services: dict):
        """ensure_builtins seeds all file-attachment predicates."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        for pid, _, _, _ in FILE_PREDICATES:
            pred = services["predicate"].get(pid)
            assert pred is not None, f"File predicate {pid} should exist"

    def test_ensure_builtins_creates_every_seed_predicate(self, services: dict):
        """ensure_builtins seeds the ENTIRE SEED_PREDICATES catalog."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        for pid, _, _, _ in SEED_PREDICATES:
            pred = services["predicate"].get(pid)
            assert pred is not None, f"Seed predicate {pid} should exist"

    def test_ensure_builtins_catalog_count(self, services: dict):
        """Total seeded predicate count matches SEED_PREDICATES length."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        all_preds = services["predicate"].list(limit=999)
        # Only count predicates with seed-reserved IDs (ignore user-created ones)
        seeded_ids = {pid for pid, _, _, _ in SEED_PREDICATES}
        actual_seeded = [p for p in all_preds if p["predicate_id"] in seeded_ids]
        assert len(actual_seeded) == len(SEED_PREDICATES), (
            f"Expected {len(SEED_PREDICATES)} seeded predicates, "
            f"found {len(actual_seeded)}"
        )

    def test_iri_column_populated_for_known_prefix_predicates(self, services: dict):
        """Known-prefix predicates (rdf:, rdfs:, owl:, sm:) have populated iri column."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        known_prefixes = set(KNOWN_PREFIXES.keys())
        for pid, _, _, _ in SEED_PREDICATES:
            if ":" in pid:
                prefix = pid.split(":", 1)[0]
                if prefix in known_prefixes:
                    pred = services["predicate"].get(pid)
                    assert pred is not None, f"Predicate {pid} should exist"
                    assert pred["iri"] != "", (
                        f"Known-prefix predicate {pid} should have "
                        f"non-empty iri column, got empty string"
                    )

    def test_iri_column_empty_for_unknown_prefix_predicates(self, services: dict):
        """Unknown-prefix predicates (:hasFile*) have empty iri column."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        known_prefixes = set(KNOWN_PREFIXES.keys())
        for pid, _, _, _ in FILE_PREDICATES:
            if ":" in pid:
                prefix = pid.split(":", 1)[0]
                if prefix not in known_prefixes:
                    pred = services["predicate"].get(pid)
                    assert pred is not None, f"Predicate {pid} should exist"
                    assert pred["iri"] == "", (
                        f"Unknown-prefix predicate {pid} should have "
                        f"empty iri column, got {pred['iri']!r}"
                    )


class TestSeedDefaultsNoop:
    """Tests that the old _seed_default_predicates() is now a no-op."""

    def test_seed_default_predicates_noop_when_empty(self, db):
        """Calling _seed_default_predicates on an empty DB creates nothing."""
        from semantika.graph.db import _seed_default_predicates
        _seed_default_predicates(db)
        count = db.execute_one("SELECT COUNT(*) AS cnt FROM predicates")
        assert count["cnt"] == 0, (
            "_seed_default_predicates should be a no-op, "
            f"but created {count['cnt']} predicates"
        )
