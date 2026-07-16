"""Tests for triple CRUD API routes — /api/v1/graph/triples/*.

Covers URI and literal triples, list, search, delete, modify, view,
and metadata update via both REST and command dispatch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Triple CRUD ────────────────────────────────────────────────────────


class TestTripleAPI:
    """Test the /api/v1/graph/triples endpoints."""

    def _setup(self, client: TestClient):
        """Ensure nodes and predicates exist for triple tests."""
        for nid in ["SUBJ", "OBJ"]:
            client.post(
                "/api/v1/graph/nodes",
                json={"node_id": nid, "labels": {"en": nid}},
            )
        if not any(
            p["predicate_id"] == "ex:rel"
            for p in client.get("/api/v1/graph/predicates").json()["predicates"]
        ):
            client.post(
                "/api/v1/graph/predicates",
                json={"predicate_id": "ex:rel", "labels": {"en": "relation"}},
            )

    def test_add_triple_uri(self, client: TestClient):
        self._setup(client)
        resp = client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "SUBJ",
                "predicate_id": "ex:rel",
                "object_value": "OBJ",
                "object_type": "node",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["triple"]["subject_id"] == "SUBJ"
        assert data["triple"]["object_type"] == "node"

    def test_add_triple_literal(self, client: TestClient):
        resp = client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "SUBJ",
                "predicate_id": "ex:rel",
                "object_value": "Hello World",
                "object_type": "literal",
                "object_lang": "en",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["triple"]["object_type"] == "literal"

    def test_list_triples(self, client: TestClient):
        """Verify triples list endpoint works (was 500 due to WITHOUT ROWID)."""
        resp = client.get("/api/v1/graph/triples?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_get_triples_by_subject(self, client: TestClient):
        resp = client.get("/api/v1/graph/triples/by-subject/SUBJ")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["triples"]) >= 1

    def test_delete_triple(self, client: TestClient):
        resp = client.delete(
            "/api/v1/graph/triples",
            params={
                "subject_id": "SUBJ",
                "predicate_id": "ex:rel",
                "object_value": "Hello World",
                "object_type": "literal",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] >= 1

    def test_update_triple_metadata(self, client: TestClient):
        """Update triple metadata (object_lang, object_datatype)."""
        # Create nodes + predicate + triple
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "META_SUBJ", "labels": {"en": "Meta Subject"}},
        )
        client.post(
            "/api/v1/graph/nodes",
            json={"node_id": "META_OBJ", "labels": {"en": "Meta Object"}},
        )
        client.post(
            "/api/v1/graph/predicates",
            json={"predicate_id": "ex:metaPred", "labels": {"en": "meta pred"}},
        )
        triple_resp = client.post(
            "/api/v1/graph/triples",
            json={
                "subject_id": "META_SUBJ",
                "predicate_id": "ex:metaPred",
                "object_value": "Hello",
                "object_type": "literal",
            },
        )
        assert triple_resp.status_code == 200

        # Update metadata
        resp = client.patch(
            "/api/v1/graph/triples",
            params={
                "subject_id": "META_SUBJ",
                "predicate_id": "ex:metaPred",
                "object_value": "Hello",
                "object_type": "literal",
            },
            json={"object_lang": "en", "object_datatype": "xsd:string"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["triple"]["object_lang"] == "en"
        assert data["triple"]["object_datatype"] == "xsd:string"


# ── Triple with literal types ──────────────────────────────────────────


class TestTripleAddLiteralTypes:
    """Test !triple add with literal type flags (Tier 1a)."""

    def _setup(self, client: TestClient) -> str:
        """Create nodes/predicates needed for triple tests."""
        client.post("/api/v1/graph/nodes", json={"node_id": "LIT_SUBJ", "labels": {"en": "Lit Subject"}})
        client.post("/api/v1/graph/nodes", json={"node_id": "LIT_OBJ", "labels": {"en": "Lit Object"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:litStr", "labels": {"en": "string prop"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:litInt", "labels": {"en": "int prop"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:litFloat", "labels": {"en": "float prop"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:litBool", "labels": {"en": "bool prop"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:litUrl", "labels": {"en": "url prop"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:litKatex", "labels": {"en": "katex prop"}})
        return "LIT_SUBJ"

    def test_triple_add_str_literal(self, client: TestClient):
        """Add a string literal triple via !command."""
        self._setup(client)
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {
                "subject_id": "LIT_SUBJ", "predicate_id": "ex:litStr",
                "object_value": "hello world", "str": "true", "lang": "en",
            }},
        )
        assert resp.status_code == 200
        # Verify the triple was created
        t_resp = client.get("/api/v1/graph/triples/by-subject/LIT_SUBJ")
        assert t_resp.status_code == 200
        triples = t_resp.json()["triples"]
        matches = [t for t in triples if t["predicate_id"] == "ex:litStr" and t["object_value"] == "hello world"]
        assert len(matches) >= 1
        assert matches[0]["object_type"] == "literal"
        assert matches[0]["object_lang"] == "en"

    def test_triple_add_int_literal(self, client: TestClient):
        """Add an integer literal triple."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {
                "subject_id": "LIT_SUBJ", "predicate_id": "ex:litInt",
                "object_value": "42", "int": "true",
            }},
        )
        assert resp.status_code == 200
        t_resp = client.get("/api/v1/graph/triples/by-subject/LIT_SUBJ")
        matches = [t for t in t_resp.json()["triples"] if t["predicate_id"] == "ex:litInt"]
        assert len(matches) >= 1
        assert matches[0]["object_datatype"] == "xsd:integer"

    def test_triple_add_float_literal(self, client: TestClient):
        """Add a float literal triple."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {
                "subject_id": "LIT_SUBJ", "predicate_id": "ex:litFloat",
                "object_value": "3.14", "float": "true",
            }},
        )
        assert resp.status_code == 200
        t_resp = client.get("/api/v1/graph/triples/by-subject/LIT_SUBJ")
        matches = [t for t in t_resp.json()["triples"] if t["predicate_id"] == "ex:litFloat"]
        assert len(matches) >= 1
        assert matches[0]["object_datatype"] == "xsd:decimal"

    def test_triple_add_bool_literal(self, client: TestClient):
        """Add a boolean literal triple."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {
                "subject_id": "LIT_SUBJ", "predicate_id": "ex:litBool",
                "object_value": "true", "bool": "true",
            }},
        )
        assert resp.status_code == 200
        t_resp = client.get("/api/v1/graph/triples/by-subject/LIT_SUBJ")
        matches = [t for t in t_resp.json()["triples"] if t["predicate_id"] == "ex:litBool"]
        assert len(matches) >= 1
        assert matches[0]["object_datatype"] == "xsd:boolean"

    def test_triple_add_url_literal(self, client: TestClient):
        """Add a URL literal triple (xsd:anyURI)."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {
                "subject_id": "LIT_SUBJ", "predicate_id": "ex:litUrl",
                "object_value": "https://example.com/page", "url": "true",
            }},
        )
        assert resp.status_code == 200
        t_resp = client.get("/api/v1/graph/triples/by-subject/LIT_SUBJ")
        matches = [t for t in t_resp.json()["triples"] if t["predicate_id"] == "ex:litUrl"]
        assert len(matches) >= 1
        assert matches[0]["object_datatype"] == "xsd:anyURI"
        assert matches[0]["object_type"] == "literal"

    def test_triple_add_katex_literal(self, client: TestClient):
        """Add a KaTeX formula triple."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {
                "subject_id": "LIT_SUBJ", "predicate_id": "ex:litKatex",
                "object_value": "E=mc^2", "katex": "E=mc^2",
            }},
        )
        assert resp.status_code == 200
        t_resp = client.get("/api/v1/graph/triples/by-subject/LIT_SUBJ")
        matches = [t for t in t_resp.json()["triples"] if t["predicate_id"] == "ex:litKatex"]
        assert len(matches) >= 1
        assert matches[0]["object_datatype"] == "text/katex"

    def test_triple_add_duplicate_metadata_update(self, client: TestClient):
        """Adding same SPO with different metadata should update."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "add"], "flags": {
                "subject_id": "LIT_SUBJ", "predicate_id": "ex:litStr",
                "object_value": "hello world", "str": "true", "lang": "fr",
            }},
        )
        assert resp.status_code == 200
        data = resp.json()
        resp_data = data.get("data", data)
        msg = str(resp_data)
        assert "metadata updated" in msg.lower() or "already exists" in msg.lower()


# ── Triple delete via command ──────────────────────────────────────────


class TestTripleDeleteCommand:
    """Test !triple delete via command dispatch (Tier 1b)."""

    def test_triple_delete_by_spo(self, client: TestClient):
        """Delete a triple by full SPO via !command."""
        client.post("/api/v1/graph/nodes", json={"node_id": "DEL_SUBJ", "labels": {"en": "Del Subject"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:delPred", "labels": {"en": "del pred"}})
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "DEL_SUBJ", "predicate_id": "ex:delPred", "object_value": "del-value", "object_type": "literal"},
        )
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "delete"], "flags": {"subject": "DEL_SUBJ", "predicate": "ex:delPred", "object": "del-value"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "deleted" in str(data).lower()

    def test_triple_delete_by_subject(self, client: TestClient):
        """Delete all triples for a subject via !command."""
        client.post("/api/v1/graph/nodes", json={"node_id": "DEL2_SUBJ", "labels": {"en": "Del2 Subject"}})
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "DEL2_SUBJ", "predicate_id": "ex:delPred", "object_value": "val1", "object_type": "literal"},
        )
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "DEL2_SUBJ", "predicate_id": "ex:delPred", "object_value": "val2", "object_type": "literal"},
        )
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "delete"], "flags": {"subject": "DEL2_SUBJ"}},
        )
        assert resp.status_code == 200
        # Verify no triples remain
        t_resp = client.get(f"/api/v1/graph/triples/by-subject/DEL2_SUBJ")
        assert len(t_resp.json()["triples"]) == 0


# ── Triple modify via command ──────────────────────────────────────────


class TestTripleModifyCommand:
    """Test !triple modify via command dispatch (Tier 1c)."""

    def test_triple_modify_object(self, client: TestClient):
        """Modify the object value of a triple."""
        client.post("/api/v1/graph/nodes", json={"node_id": "MOD_SUBJ", "labels": {"en": "Mod Subject"}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": "ex:modPred", "labels": {"en": "mod pred"}})
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": "MOD_SUBJ", "predicate_id": "ex:modPred", "object_value": "old-value", "object_type": "literal"},
        )
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "modify"], "flags": {
                "subject": "MOD_SUBJ", "predicate": "ex:modPred", "object": "old-value",
                "new-object": "new-value", "str": "true",
            }},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "modified" in str(data).lower()
        # Verify old value gone
        old = client.get(
            "/api/v1/graph/triples/by-subject/MOD_SUBJ",
        )
        vals = [t["object_value"] for t in old.json()["triples"] if t["predicate_id"] == "ex:modPred"]
        assert "old-value" not in vals


# ── Triple view via command ────────────────────────────────────────────


class TestTripleViewCommand:
    """Test !triple view and !view commands (Tier 1d)."""

    def test_triple_view_command(self, client: TestClient):
        """View triples for a node via !triple view."""
        client.post("/api/v1/graph/nodes", json={"node_id": "VIEW_SUBJ", "labels": {"en": "View Subject"}})
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "view"], "flags": {"id": "VIEW_SUBJ"}},
        )
        assert resp.status_code == 200

    def test_view_root_command(self, client: TestClient):
        """View via root !view command."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["graph", "view"], "flags": {"id": "VIEW_SUBJ"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data


# ── Edge cases ─────────────────────────────────────────────────────────


class TestTripleEdgeCases:
    """Triple-specific edge cases."""

    def test_triple_delete_no_subject(self, client: TestClient):
        """Triple delete without subject returns error in response."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["triple", "delete"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Specify" in str(data) or "error" in str(data).lower()


# ── Batch triple creation ────────────────────────────────────────────


class TestTripleBatchAPI:
    """Test the POST /api/v1/graph/triples/batch endpoint.

    Uses unique IDs per test to avoid state conflicts since all tests
    share the module-level test database.
    """

    _counter = 0

    def _setup(self, client: TestClient, tag: str = ""):
        """Create common nodes and predicates with unique IDs."""
        self._counter += 1
        uid = f"{tag}{self._counter}"
        subj = f"BAT_SUBJ_{uid}"
        obj1 = f"BAT_OBJ1_{uid}"
        obj2 = f"BAT_OBJ2_{uid}"
        pred1 = f"ex:rel1_{uid}"
        pred2 = f"ex:rel2_{uid}"
        for nid in [subj, obj1, obj2]:
            client.post("/api/v1/graph/nodes", json={"node_id": nid, "labels": {"en": nid}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": pred1, "labels": {"en": pred1}})
        client.post("/api/v1/graph/predicates", json={"predicate_id": pred2, "labels": {"en": pred2}})
        return subj, obj1, obj2, pred1, pred2

    def test_batch_all_created(self, client: TestClient):
        """All valid triples in batch are created."""
        subj, obj1, obj2, pred1, pred2 = self._setup(client, "all")
        resp = client.post(
            "/api/v1/graph/triples/batch",
            json={"triples": [
                {"subject_id": subj, "predicate_id": pred1, "object_value": obj1},
                {"subject_id": subj, "predicate_id": pred2, "object_value": obj2},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_count"] == 2
        assert data["error_count"] == 0

    def test_batch_with_duplicates(self, client: TestClient):
        """Batch with duplicates reports duplicate status."""
        subj, obj1, obj2, pred1, pred2 = self._setup(client, "dup")
        # Create one triple first
        client.post(
            "/api/v1/graph/triples",
            json={"subject_id": subj, "predicate_id": pred1, "object_value": obj1},
        )
        # Batch with both new and duplicate
        resp = client.post(
            "/api/v1/graph/triples/batch",
            json={"triples": [
                {"subject_id": subj, "predicate_id": pred1, "object_value": obj1},
                {"subject_id": subj, "predicate_id": pred2, "object_value": obj2},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_count"] == 1
        assert data["duplicate_count"] == 1
        assert data["error_count"] == 0

    def test_batch_with_error(self, client: TestClient):
        """Batch with invalid triples reports errors."""
        subj, obj1, obj2, pred1, pred2 = self._setup(client, "err")
        resp = client.post(
            "/api/v1/graph/triples/batch",
            json={"triples": [
                {"subject_id": subj, "predicate_id": pred1, "object_value": obj1},
                {"subject_id": subj, "predicate_id": "ex:missing_xyz", "object_value": obj1},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_count"] == 1
        assert data["error_count"] == 1
        assert data["results"][1]["status"] == "error"
        assert data["results"][1].get("message", "") != ""

    def test_batch_empty_rows_skipped(self, client: TestClient):
        """Empty rows in batch are skipped."""
        subj, obj1, obj2, pred1, pred2 = self._setup(client, "empty")
        resp = client.post(
            "/api/v1/graph/triples/batch",
            json={"triples": [
                {"subject_id": subj, "predicate_id": pred1, "object_value": obj1},
                {"subject_id": "", "predicate_id": "", "object_value": ""},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_count"] == 1
