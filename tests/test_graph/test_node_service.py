"""Tests for NodeService — node CRUD, FTS5 search, trash, merge, proof cascade."""

from __future__ import annotations

import pytest


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

    def test_get_nonexistent_returns_none(self, services: dict):
        """get() returns None for nonexistent node."""
        assert services["node"].get("NONEXISTENT") is None

    def test_rename_node(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "OLDID", "labels": {"en": "Old"}})
        ns.update_node_id("OLDID", "NEWID")
        assert ns.get("OLDID") is None
        assert ns.get("NEWID") is not None

    def test_rename_nonexistent(self, services: dict):
        ns = services["node"]
        with pytest.raises(ValueError, match="not found"):
            ns.update_node_id("NONEXISTENT", "NEWID")

    def test_rename_to_existing(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "A", "labels": {"en": "A"}})
        ns.create({"node_id": "B", "labels": {"en": "B"}})
        with pytest.raises(ValueError, match="already exists"):
            ns.update_node_id("A", "B")

    def test_merge_nodes(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "SRC", "labels": {"en": "Source"}, "definitions": {"en": "src def"}})
        ns.create({"node_id": "TGT", "labels": {"en": "Target"}, "definitions": {"en": "tgt def"}})
        result = ns.merge_nodes("SRC", "TGT")
        assert result["node_id"] == "TGT"
        assert ns.get("SRC") is None

    def test_merge_same_node(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "SAME", "labels": {"en": "Same"}})
        with pytest.raises(ValueError, match="different"):
            ns.merge_nodes("SAME", "SAME")

    def test_merge_source_not_found(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "TGT", "labels": {"en": "Target"}})
        with pytest.raises(ValueError, match="not found"):
            ns.merge_nodes("NONEXISTENT", "TGT")

    def test_merge_target_not_found(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "SRC", "labels": {"en": "Source"}})
        with pytest.raises(ValueError, match="not found"):
            ns.merge_nodes("SRC", "NONEXISTENT")

    def test_update_with_definitions_dict(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "DEFNODE", "labels": {"en": "Def"}})
        ns.update("DEFNODE", {"definitions": {"en": "Definition text"}})
        node = ns.get("DEFNODE")
        assert node is not None
        assert "Definition text" in node.get("definition_text", "")

    def test_trash_older_than(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "OLDTRASH", "labels": {"en": "Old trash"}})
        ns.delete("OLDTRASH", soft=True)
        items = ns.get_trash_older_than(0)
        assert len(items) >= 1

    def test_empty_all_trash(self, services: dict):
        ns = services["node"]
        ns.create({"node_id": "EMPTYME", "labels": {"en": "Empty"}})
        ns.delete("EMPTYME", soft=True)
        count = ns.empty_all_trash()
        assert count >= 1
        assert len(ns.list_trash()) == 0

    def test_ensure_fts_creates_index(self, services: dict):
        """_ensure_fts creates the FTS table."""
        ns = services["node"]
        ns._ensure_fts()
        # Calling it twice should be idempotent
        ns._ensure_fts()

    # ── Proof cascade tests ──────────────────────────────────────────

    def _setup_triple_with_proof(self, services: dict) -> dict:
        """Helper: create node A→ex:p→B with a proof and return services."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        prs = services["proof"]

        ns.create({"node_id": "A", "labels": {"en": "A"}})
        ns.create({"node_id": "B", "labels": {"en": "B"}})
        ps.create({"predicate_id": "ex:p", "labels": {"en": "p"}})
        ts.add("A", "ex:p", "B", object_type="uri")

        proof = prs.create({
            "subject_id": "A", "predicate_id": "ex:p",
            "object_value": "B", "proof_type": "observation",
        })
        return {"proof_uuid": proof["uuid"], "services": services}

    def test_soft_delete_node_cascades_proofs(self, services: dict):
        """Soft-deleting a node deletes proofs attached to its triples."""
        setup = self._setup_triple_with_proof(services)
        ns = services["node"]
        prs = services["proof"]

        ns.delete("A", soft=True)
        remaining = prs.get_by_subject("A")
        assert remaining == [], "Proofs should be cascade-deleted with node"

    def test_hard_delete_node_cascades_proofs(self, services: dict):
        """Hard-deleting a node deletes proofs attached to its triples."""
        setup = self._setup_triple_with_proof(services)
        ns = services["node"]
        prs = services["proof"]

        ns.delete("A", soft=False)
        remaining = prs.get_by_subject("A")
        assert remaining == [], "Proofs should be cascade-deleted with node"

    def test_soft_delete_node_as_object_cascades_proofs(self, services: dict):
        """Deleting a node that is the URI object of a triple cascades proofs."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        prs = services["proof"]

        ns.create({"node_id": "S", "labels": {"en": "S"}})
        ns.create({"node_id": "OBJ", "labels": {"en": "Object"}})
        ps.create({"predicate_id": "ex:rel", "labels": {"en": "rel"}})
        ts.add("S", "ex:rel", "OBJ", object_type="uri")

        proof = prs.create({
            "subject_id": "S", "predicate_id": "ex:rel",
            "object_value": "OBJ", "proof_type": "observation",
        })

        ns.delete("OBJ", soft=True)
        remaining = prs.get_by_triple("S", "ex:rel", "OBJ")
        assert remaining == [], "Proofs should cascade when URI-object node is deleted"

    def test_proofs_not_affected_by_unrelated_node_delete(self, services: dict):
        """Deleting an unrelated node does not cascade away proofs."""
        ns = services["node"]
        prs = services["proof"]
        services["triple"]
        services["predicate"]

        setup = self._setup_triple_with_proof(services)
        ns.create({"node_id": "UNRELATED", "labels": {"en": "Unrelated"}})
        ns.delete("UNRELATED", soft=True)

        remaining = prs.get_by_subject("A")
        assert len(remaining) == 1, "Unrelated node delete should not affect proofs"

    # ── Batch delete tests ───────────────────────────────────────────

    def test_batch_delete_removes_nodes(self, services: dict):
        """batch_delete removes multiple nodes."""
        ns = services["node"]
        for nid in ["B1", "B2", "B3"]:
            ns.create({"node_id": nid, "labels": {"en": nid}})

        deleted, errors = ns.batch_delete(["B1", "B2", "B3"], soft=True)
        assert deleted == 3
        assert len(errors) == 0
        for nid in ["B1", "B2", "B3"]:
            assert ns.get(nid) is None

    def test_batch_delete_empty(self, services: dict):
        """batch_delete with empty list returns (0, [])."""
        ns = services["node"]
        deleted, errors = ns.batch_delete([], soft=True)
        assert deleted == 0
        assert errors == []

    def test_batch_delete_missing_nodes(self, services: dict):
        """batch_delete reports missing nodes as errors."""
        ns = services["node"]
        ns.create({"node_id": "EXIST", "labels": {"en": "Exists"}})
        deleted, errors = ns.batch_delete(["EXIST", "MISSING1", "MISSING2"], soft=True)
        assert deleted == 1
        assert len(errors) == 2
        assert any("MISSING1" in e for e in errors)
        assert any("MISSING2" in e for e in errors)


class TestNodeHardDelete:
    """Tests for node hard delete with TOCTOU fix."""

    def test_hard_delete_removes_node(self, services: dict):
        """Hard delete removes the node entirely."""
        ns = services["node"]
        ns.create({"node_id": "DELETE_ME", "labels": {"en": "Delete me"}})
        assert ns.delete("DELETE_ME", soft=False) is True
        assert ns.get("DELETE_ME") is None

    def test_hard_delete_cascades_triples(self, services: dict):
        """Hard delete removes triples referencing the node."""
        ns = services["node"]
        ts = services["triple"]
        ns.create({"node_id": "SUBJ", "labels": {"en": "Subject"}})
        ns.create({"node_id": "OBJ", "labels": {"en": "Object"}})
        ps = services["predicate"]
        ps.create({"predicate_id": "ex:p"})
        ts.add("SUBJ", "ex:p", "OBJ", object_type="uri")
        assert ts.count() >= 1

        ns.delete("SUBJ", soft=False)
        assert ts.count() == 0

    def test_hard_delete_not_found(self, services: dict):
        """Hard delete of nonexistent node returns False."""
        assert services["node"].delete("NONEXISTENT", soft=False) is False


class TestNodeServiceNormalizeIds:
    """Tests for node_service.create() with normalize_ids parameter."""

    def test_create_without_normalize_ids_keeps_diacritics(self, services: dict):
        """Without normalize_ids, a node_id with diacritics is kept as-is."""
        ns = services["node"]
        node = ns.create({"node_id": "Matière", "labels": {"en": "Test"}})
        assert node["node_id"] == "Matière"

    def test_create_with_normalize_ids_strips_diacritics(self, services: dict):
        """With normalize_ids=True, diacritics are stripped from node_id."""
        ns = services["node"]
        node = ns.create({"node_id": "Matière", "labels": {"en": "Test"}}, normalize_ids=True)
        assert node["node_id"] == "Matiere"

    def test_create_with_normalize_ids_false_keeps_diacritics(self, services: dict):
        """With normalize_ids=False, diacritics are kept."""
        ns = services["node"]
        node = ns.create({"node_id": "Café", "labels": {"en": "Test"}}, normalize_ids=False)
        assert node["node_id"] == "Café"
