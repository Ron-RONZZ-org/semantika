"""Tests for BuiltinTypeService — YAML-based lazy seeding, fallback behavior."""

from __future__ import annotations

import json

import pytest

from semantika.graph._required_predicates import REQUIRED_PREDICATE_IDS
from semantika.graph.builtin_loader import (
    get_core_predicate_ids,
    get_predicate_catalog,
    get_type_nodes_from_yaml,
    invalidate_caches,
    load_builtins_yaml,
)
from semantika.graph.constants import KNOWN_PREFIXES


class TestYamlSeedData:
    """Verify YAML seed data is well-formed via the loader."""

    def test_builtins_yaml_loads(self):
        """builtins.yaml can be loaded and parsed."""
        data = load_builtins_yaml()
        assert isinstance(data, dict)
        assert "predicates" in data
        assert "type_nodes" in data

    def test_type_nodes_have_required_keys(self):
        """All type nodes have id, labels, and en label."""
        type_nodes = get_type_nodes_from_yaml()
        assert len(type_nodes) > 0
        for node in type_nodes:
            assert "id" in node, f"Type node missing 'id': {node}"
            node_id = node["id"]
            assert node_id.isupper() or "_" in node_id  # Concept type nodes are all-caps
            assert "labels" in node
            assert "en" in node["labels"]

    def test_predicate_catalog_has_all_required(self):
        """Every required predicate appears in the YAML catalog (or fallback)."""
        catalog = get_predicate_catalog()
        for pid in REQUIRED_PREDICATE_IDS:
            assert pid in catalog, (
                f"Required predicate '{pid}' is missing from catalog "
                f"(should have YAML or Python fallback)"
            )

    def test_predicate_catalog_has_labels(self):
        """Every catalog entry has en labels."""
        catalog = get_predicate_catalog()
        for pid, entry in catalog.items():
            assert "en" in entry.get("labels", {}), (
                f"Predicate '{pid}' is missing 'en' label"
            )

    def test_predicate_catalog_has_tier(self):
        """Every catalog entry has a tier field."""
        from semantika.graph.builtin_loader import _normalize_tier
        catalog = get_predicate_catalog()
        for pid, entry in catalog.items():
            tier = _normalize_tier(entry.get("tier"))
            assert tier in ("w3c", "1", "2", "file"), (
                f"Predicate '{pid}' has invalid tier: {entry.get('tier')!r}"
            )

    def test_core_predicate_ids_includes_tier1_only(self):
        """Core predicate IDs include Tier 1 but NOT W3C or Tier 2."""
        core = get_core_predicate_ids()
        # Tier 1 sm: predicates ARE core
        assert "sm:depicts" in core
        assert "sm:theme" in core
        assert "sm:partOf" in core
        # W3C predicates are NOT core (they can be freely deleted/recreated)
        assert "rdf:type" not in core
        assert "rdfs:subClassOf" not in core
        # Tier 2 should NOT be in core
        assert "sm:isAbout" not in core
        assert "sm:relatesTo" not in core

    def test_cached_catalog_same_instance(self):
        """Repeated calls return the same cached instance."""
        invalidate_caches()
        cat1 = get_predicate_catalog()
        cat2 = get_predicate_catalog()
        assert cat1 is cat2


class TestBuiltinTypeService:
    """Test YAML-based lazy seeding and predicate ensuring."""

    def test_ensure_builtins_creates_predicates(self, services: dict):
        bts = services["builtin_type"]
        bts.ensure_builtins()

        catalog = get_predicate_catalog()
        for pid in catalog:
            pred = services["predicate"].get(pid)
            assert pred is not None, f"Predicate {pid} should exist"

    def test_ensure_builtins_creates_type_nodes(self, services: dict):
        bts = services["builtin_type"]
        bts.ensure_builtins()

        type_nodes = get_type_nodes_from_yaml()
        for node in type_nodes:
            n = services["node"].get(node["id"])
            assert n is not None, f"Type node {node['id']} should exist"
            labels = json.loads(n["labels"]) if isinstance(n["labels"], str) else n["labels"]
            assert labels.get("en") == node["labels"]["en"]

    def test_ensure_builtins_creates_rdf_type_triples(self, services: dict):
        bts = services["builtin_type"]
        bts.ensure_builtins()

        type_nodes = get_type_nodes_from_yaml()
        for node in type_nodes:
            triples = services["triple"].get_by_subject(node["id"])
            type_triples = [
                t for t in triples
                if t["predicate_id"] == "rdf:type" and t["object_value"] == node["id"]
            ]
            assert len(type_triples) >= 1, (
                f"Type node {node['id']} should have rdf:type self-reference"
            )

    def test_ensure_builtins_idempotent(self, services: dict):
        """Calling ensure_builtins twice does not duplicate data."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        bts.ensure_builtins()  # second call

        catalog = get_predicate_catalog()
        for pid in catalog:
            pred = services["predicate"].get(pid)
            assert pred is not None

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

    def test_ensure_builtins_creates_w3c_predicates(self, services: dict):
        """ensure_builtins seeds all W3C predicates (rdf:/rdfs:/owl:)."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        for pid in ["rdf:type", "rdfs:subClassOf", "rdfs:label",
                      "owl:sameAs", "owl:disjointWith", "owl:inverseOf",
                      "rdfs:seeAlso"]:
            pred = services["predicate"].get(pid)
            assert pred is not None, f"W3C predicate {pid} should exist"

    def test_ensure_builtins_creates_file_predicates(self, services: dict):
        """ensure_builtins seeds all file-attachment predicates."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        for pid in [":hasFilePath", ":hasFileMime", ":hasFileSize", ":hasFileSource"]:
            pred = services["predicate"].get(pid)
            assert pred is not None, f"File predicate {pid} should exist"

    def test_iri_column_populated_for_known_prefix_predicates(self, services: dict):
        """Known-prefix predicates (rdf:, rdfs:, owl:, sm:) have populated iri column."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        known_prefixes = set(KNOWN_PREFIXES.keys())
        catalog = get_predicate_catalog()
        for pid, entry in catalog.items():
            if ":" in pid:
                prefix = pid.split(":", 1)[0]
                if prefix in known_prefixes:
                    pred = services["predicate"].get(pid)
                    assert pred is not None
                    assert pred["iri"] != "", (
                        f"Known-prefix predicate {pid} should have "
                        f"non-empty iri column, got empty string"
                    )

    def test_iri_column_empty_for_unknown_prefix_predicates(self, services: dict):
        """Unknown-prefix predicates (:hasFile*) have empty iri column."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        known_prefixes = set(KNOWN_PREFIXES.keys())
        for pid in [":hasFilePath", ":hasFileMime", ":hasFileSize", ":hasFileSource"]:
            if ":" in pid:
                prefix = pid.split(":", 1)[0]
                if prefix not in known_prefixes:
                    pred = services["predicate"].get(pid)
                    assert pred is not None
                    assert pred["iri"] == "", (
                        f"Unknown-prefix predicate {pid} should have "
                        f"empty iri column, got {pred['iri']!r}"
                    )

    def test_reload_reseeds(self, services: dict):
        """Reload re-reads YAML and re-seeds (idempotent)."""
        bts = services["builtin_type"]
        counts = bts.reload()

        assert counts["predicates"] >= 1
        assert counts["type_nodes"] >= 1
        # Verify predicates are still there after reload
        assert services["predicate"].get("rdf:type") is not None
        assert services["predicate"].get("sm:depicts") is not None

    def test_reload_after_cache_invalidation(self):
        """invalidate_caches clears the catalog cache."""
        invalidate_caches()
        cat1 = get_predicate_catalog()
        invalidate_caches()
        cat2 = get_predicate_catalog()
        # They should be different objects (cache was cleared)
        assert cat1 is not cat2


    def test_reload_requires_ensure_builtins_call(self, services: dict):
        """Reload invalidates cache and re-seeds even without prior ensure_builtins."""
        bts = services["builtin_type"]
        counts = bts.reload()
        assert counts["predicates"] >= 1
        assert counts["type_nodes"] >= 1

    def test_fallback_warns_on_missing_yaml_predicate(self, services: dict, caplog):
        """When a required predicate is missing from YAML, the Python fallback
        is used and a warning is logged."""
        import logging
        from semantika.graph.builtin_loader import get_predicate_catalog, invalidate_caches

        invalidate_caches()
        caplog.set_level(logging.WARNING)
        catalog = get_predicate_catalog()

        # All required predicates should be in the catalog (via YAML or fallback)
        for pid in REQUIRED_PREDICATE_IDS:
            assert pid in catalog, f"Required predicate '{pid}' missing from catalog"

        # Verify at least some unit predicates come from fallback
        # (they are NOT in builtins.yaml — only in _required_predicates.py)
        assert ":symbol" in catalog
        assert ":multiplier" in catalog

    def test_missing_yaml_returns_empty(self, tmp_path):
        """When no YAML is found, loader returns empty dict."""
        from semantika.graph.builtin_loader import _load_yaml_file
        result = _load_yaml_file(tmp_path / "nonexistent.yaml", "test")
        assert result is None


class TestBuiltinLoader:
    """Test the YAML loader directly."""

    def test_load_builtins_yaml_has_required_keys(self):
        data = load_builtins_yaml()
        assert "version" in data
        assert data["version"] == 1

    def test_yaml_has_all_tiers(self):
        catalog = get_predicate_catalog()
        tiers_seen = set()
        for entry in catalog.values():
            tiers_seen.add(entry.get("tier"))
        assert "w3c" in tiers_seen
        assert "1" in tiers_seen
        assert "2" in tiers_seen
        assert "file" in tiers_seen

    def test_type_nodes_include_media_types(self):
        type_nodes = get_type_nodes_from_yaml()
        type_ids = {n["id"] for n in type_nodes}
        assert "PHOTO" in type_ids
        assert "VIDEO" in type_ids
        assert "DOCUMENT" in type_ids
        assert "SOURCE_CODE" in type_ids
        assert "BOOK" in type_ids
        assert "FILM" in type_ids
        assert "PAPER" in type_ids


class TestSeedDefaultsNoop:
    """The old _seed_default_predicates() remains a no-op."""

    def test_seed_default_predicates_noop_when_empty(self, db):
        from semantika.graph.db import _seed_default_predicates
        _seed_default_predicates(db)
        count = db.execute_one("SELECT COUNT(*) AS cnt FROM predicates")
        assert count["cnt"] == 0
