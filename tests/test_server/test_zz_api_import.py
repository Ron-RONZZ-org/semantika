"""TTL import tests — must run LAST to avoid DB locking other test files.

The TTL import writes multiple nodes/predicates/triples in a single request
via thread pool workers. The per-thread connections from LighterbirdDB
persist after the test completes, causing ``database is locked`` errors for
any test file collected after this one.

This file is named ``test_zz_*`` to ensure pytest collects it last.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Must override data dir before importing app
TEST_DATA_DIR = Path("/tmp/semantika-import-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app


SAMPLE_TTL = """@prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Dog a ex:Animal ;
    rdfs:label "Dog"@en .

ex:Cat a ex:Animal ;
    rdfs:label "Cat"@en .
"""


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestTTLImport:
    """Test TTL import via API and command."""

    def test_import_via_api(self, client: TestClient):
        resp = client.post("/api/v1/query/import", json={"data": SAMPLE_TTL})
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["nodes_created"] >= 2
        assert stats["predicates_created"] >= 2
        assert stats["triples_added"] >= 2

    def test_import_via_command(self, client: TestClient):
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["import"], "flags": {"data": SAMPLE_TTL}},
        )
        assert resp.status_code == 200

    def test_import_triples_persisted(self, client: TestClient):
        nodes = client.get("/api/v1/graph/nodes").json()
        node_ids = [n["node_id"] for n in nodes["nodes"]]
        assert any("Cat" in nid or "Animal" in nid for nid in node_ids)
