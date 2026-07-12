"""Tests for PredicateService and PredicateGroupService."""

from __future__ import annotations

import pytest

from semantika.core.crud import now


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

    # ── Proof cascade tests ──────────────────────────────────────────

    def test_soft_delete_predicate_cascades_proofs(self, services: dict):
        """Soft-deleting a predicate deletes proofs attached to its triples."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        prs = services["proof"]

        ns.create({"node_id": "A", "labels": {"en": "A"}})
        ns.create({"node_id": "B", "labels": {"en": "B"}})
        ps.create({"predicate_id": "ex:test_p", "labels": {"en": "test p"}})
        ts.add("A", "ex:test_p", "B", object_type="uri")

        prs.create({
            "subject_id": "A", "predicate_id": "ex:test_p",
            "object_value": "B", "proof_type": "observation",
        })

        ps.delete("ex:test_p", soft=True)
        remaining = prs.get_by_triple("A", "ex:test_p", "B")
        assert remaining == [], "Proofs should be cascade-deleted with predicate"

    def test_hard_delete_predicate_cascades_triples_and_proofs(self, services: dict):
        """Hard-deleting a predicate cascades to triples and proofs."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        prs = services["proof"]

        ns.create({"node_id": "A", "labels": {"en": "A"}})
        ns.create({"node_id": "B", "labels": {"en": "B"}})
        ps.create({"predicate_id": "ex:hard_p", "labels": {"en": "hard p"}})
        ts.add("A", "ex:hard_p", "B", object_type="uri")

        prs.create({
            "subject_id": "A", "predicate_id": "ex:hard_p",
            "object_value": "B", "proof_type": "observation",
        })

        assert ts.count() == 1
        assert len(prs.get_by_triple("A", "ex:hard_p", "B")) == 1

        ps.delete("ex:hard_p", soft=False)

        assert ts.count() == 0, "Triples should be cascade-deleted with predicate"
        remaining = prs.get_by_triple("A", "ex:hard_p", "B")
        assert remaining == [], "Proofs should be cascade-deleted with predicate"

    def test_proofs_not_affected_by_unrelated_predicate_delete(self, services: dict):
        """Deleting an unrelated predicate does not cascade away proofs."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        prs = services["proof"]

        ns.create({"node_id": "A", "labels": {"en": "A"}})
        ns.create({"node_id": "B", "labels": {"en": "B"}})
        ps.create({"predicate_id": "ex:p_target", "labels": {"en": "target"}})
        ps.create({"predicate_id": "ex:p_unrelated", "labels": {"en": "unrelated"}})
        ts.add("A", "ex:p_target", "B", object_type="uri")

        prs.create({
            "subject_id": "A", "predicate_id": "ex:p_target",
            "object_value": "B", "proof_type": "observation",
        })

        ps.delete("ex:p_unrelated", soft=True)
        remaining = prs.get_by_triple("A", "ex:p_target", "B")
        assert len(remaining) == 1, "Unrelated predicate delete should not affect proofs"


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


class TestPredicateDeleteExact:
    """Regression tests for predicate hard delete (exact match fix)."""

    def test_hard_delete_by_exact_id(self, services: dict):
        """Hard delete must not use LIKE prefix matching (bug fix)."""
        ps = services["predicate"]
        ps.create({"predicate_id": "ex:test"})
        ps.create({"predicate_id": "ex:test_foo"})
        ps.create({"predicate_id": "ex:test_something"})

        assert ps.delete("ex:test", soft=False) is True
        # Only ex:test should be deleted, not the prefix-matching ones
        assert ps.get("ex:test_foo") is not None
        assert ps.get("ex:test_something") is not None

    def test_hard_delete_not_found(self, services: dict):
        """Hard delete of nonexistent returns False."""
        assert services["predicate"].delete("NONEXISTENT", soft=False) is False

    def test_hard_delete_cascades_triples(self, services: dict):
        """Hard delete removes triples referencing the predicate."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        ns.create({"node_id": "S", "labels": {"en": "S"}})
        ns.create({"node_id": "O", "labels": {"en": "O"}})
        ps.create({"predicate_id": "ex:del"})
        ts.add("S", "ex:del", "O", object_type="uri")
        assert ts.count() == 1

        ps.delete("ex:del", soft=False)
        assert ts.count() == 0


class TestPredicateUpdateNplusOne:
    """Regression tests for update_predicate_id collision detection (N+1 fix)."""

    def test_rename_collision_detected(self, services: dict):
        """Renaming predicate to collide with existing triples raises."""
        ns = services["node"]
        ps = services["predicate"]
        ts = services["triple"]
        ns.create({"node_id": "S", "labels": {"en": "S"}})
        ns.create({"node_id": "O", "labels": {"en": "O"}})
        ps.create({"predicate_id": "ex:old_p"})
        ts.add("S", "ex:old_p", "O", object_type="uri")
        # Insert a triple with the target predicate_id directly, disabling FK
        services["triple"].db.execute("PRAGMA foreign_keys=OFF")
        services["triple"].db.execute(
            "INSERT OR IGNORE INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("S", "ex:new_p", "O", "uri", now()),
        )
        services["triple"].db.execute("PRAGMA foreign_keys=ON")

        with pytest.raises(ValueError, match="collision"):
            ps.update_predicate_id("ex:old_p", "ex:new_p")

    def test_rename_no_collision_succeeds(self, services: dict):
        """Renaming to a non-colliding predicate_id works."""
        ps = services["predicate"]
        ps.create({"predicate_id": "ex:old", "labels": {"en": "old"}})
        result = ps.update_predicate_id("ex:old", "ex:new")
        assert result["predicate_id"] == "ex:new"
        assert ps.get("ex:old") is None

    def test_rename_not_found(self, services: dict):
        """Renaming nonexistent predicate raises."""
        with pytest.raises(ValueError, match="not found"):
            services["predicate"].update_predicate_id("NONEXISTENT", "new")

    def test_rename_to_existing_raises(self, services: dict):
        """Renaming to an existing predicate_id raises."""
        ps = services["predicate"]
        ps.create({"predicate_id": "ex:a"})
        ps.create({"predicate_id": "ex:b"})
        with pytest.raises(ValueError, match="already exists"):
            ps.update_predicate_id("ex:a", "ex:b")


class TestPredicateServiceNormalizeIds:
    """Tests for predicate_service.create() with normalize_ids parameter."""

    def test_create_without_normalize_ids_keeps_diacritics(self, services: dict):
        """Without normalize_ids, a predicate_id with diacritics is kept (invisible chars still stripped)."""
        ps = services["predicate"]
        pred = ps.create({"predicate_id": "ex:matière", "labels": {"en": "Matière"}})
        assert pred["predicate_id"] == "ex:matière"

    def test_create_with_normalize_ids_strips_diacritics(self, services: dict):
        """With normalize_ids=True, diacritics are stripped from predicate_id."""
        ps = services["predicate"]
        pred = ps.create({"predicate_id": "ex:matière", "labels": {"en": "Matière"}}, normalize_ids=True)
        assert pred["predicate_id"] == "ex:matiere"

    def test_create_sanitizes_invisible_chars(self, services: dict):
        """predicate_id is always sanitized (invisible chars removed)."""
        ps = services["predicate"]
        pred = ps.create({"predicate_id": "ex:te\u200bst", "labels": {"en": "Test"}})
        # Without invisible chars
        assert pred["predicate_id"] == "ex:test"
