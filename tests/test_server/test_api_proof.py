"""Tests for proof CRUD API routes — /api/v1/proof/*.

Covers creating, reading, deleting proofs via REST, and proof
commands via the dispatch system.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Must override data dir before importing app
TEST_DATA_DIR = Path("/tmp/semantika-proof-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Proof CRUD via REST ───────────────────────────────────────────────


class TestProofAPI:
    """Test proof CRUD operations."""

    def test_create_and_get_proof(self, client: TestClient):
        # Create fresh nodes and predicate for proof FK constraints
        resp = client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "PROOF_SUBJ", "labels": {"en": "Proof Subject"}},
        )
        assert resp.status_code == 200
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "PROOF_OBJ", "labels": {"en": "Proof Object"}},
        )
        assert resp.status_code == 200
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:proofPred", "labels": {"en": "proof predicate"}},
        )
        assert resp.status_code == 200
        client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "PROOF_SUBJ",
                "predicate_id": "ex:proofPred",
                "object_value": "PROOF_OBJ",
                "object_type": "uri",
            },
        )
        # Create proof
        resp = client.post(
            "/api/v1/proof/proofs",
            json={
                "subject_id": "PROOF_SUBJ",
                "predicate_id": "ex:proofPred",
                "object_value": "PROOF_OBJ",
                "proof_type": "observation",
                "source": "e2e test",
                "notes": "Testing",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "proof" in data
        proof_uuid = data["proof"]["uuid"]
        assert proof_uuid

        # Get by triple
        resp = client.get(
            "/api/v1/proof/proofs/by-triple",
            params={"subject_id": "PROOF_SUBJ", "predicate_id": "ex:proofPred", "object_value": "PROOF_OBJ"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["proofs"]) >= 1

        # Get by subject
        resp = client.get("/api/v1/proof/proofs/by-subject/PROOF_SUBJ")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["proofs"]) >= 1

        # Delete
        resp = client.delete(f"/api/v1/proof/proofs/{proof_uuid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ── Proof commands via dispatch ────────────────────────────────────────


class TestProofCommands:
    """Test !proof add/view/delete via command dispatch (Tier 3e)."""

    def test_proof_add_and_view_via_command(self, client: TestClient):
        """Add and view a proof via !command."""
        client.post("/api/v1/graph/nodes", json={"node_id": "CMD_PRF_S", "labels": {"en": "Cmd Proof S"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:cmdPfP", "labels": {"en": "cmd proof pred"}})
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "CMD_PRF_S", "predicate_id": "ex:cmdPfP", "object_value": "proof-target", "object_type": "literal"},
        )
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["proof", "add"], "flags": {
                "subject_id": "CMD_PRF_S", "predicate_id": "ex:cmdPfP",
                "object_value": "proof-target", "source": "command test",
            }},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Created" in str(data)

        # View proofs for this triple
        v_resp = client.post(
            "/api/v1/command",
            json={"tokens": ["proof", "view"], "flags": {
                "subject_id": "CMD_PRF_S", "predicate_id": "ex:cmdPfP", "object_value": "proof-target",
            }},
        )
        assert v_resp.status_code == 200


# ── Edge cases ─────────────────────────────────────────────────────────


class TestProofEdgeCases:
    """Proof-specific edge cases."""

    def test_proof_add_missing_args(self, client: TestClient):
        """Proof add without required args redirects to form."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["proof", "add"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Interactive commands return form-required on validation failure
        assert "form" in str(data).lower()
