"""Tests for SPARQL engine, API routes, and command handler.

Covers:
- IRI mapping functions (_to_uri, _from_uri, _to_rdf_term)
- SparqlEngine query execution and enrichment
- SyncBacklog retry with exponential backoff
- Incremental sync hooks (TripleService → RocksDB cache)
- API routes (GET/POST /api/v1/query/sparql)
- !sparql command dispatch
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pyoxigraph as ox
import pytest
from fastapi.testclient import TestClient

from semantika.graph.db import (
    close_sparql_engine,
    init_sparql_engine,
    reset_services,
)
from semantika.core.config import get_iri_template
from semantika.graph.sparql.engine import (
    _from_uri,
    _to_rdf_term,
    _to_uri,
    SparqlEngine,
    SyncBacklog,
)
from semantika.server.app import create_app
from semantika.server.command.registry import clear_command_cache

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# IRI mapping tests
# ═══════════════════════════════════════════════════════════════════════════


# Template for default config (used when no semantika.jsonc exists)
_NODE_TPL = get_iri_template("node")  # "https://semantika.local/node/$id"
_PRED_TPL = get_iri_template("predicate")  # "https://semantika.local/resource/$id"


class TestIRIMapping:
    """Test internal ID ↔ RDF IRI conversion."""

    def test_bare_node_id(self):
        """Bare labels without colons get the node template."""
        uri = _to_uri("BOOK_001")
        assert uri.value == _NODE_TPL.replace("$id", "BOOK_001")

    def test_known_prefix(self):
        """Known prefixes get their standard namespace."""
        uri = _to_uri("rdf:type")
        assert uri.value == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    def test_unknown_prefix(self):
        """Unknown prefixes get the predicate template."""
        uri = _to_uri("rs:hasAuthor")
        assert uri.value == _PRED_TPL.replace("$id", "rs:hasAuthor")

    def test_full_http_uri(self):
        """Full http/https URIs pass through as-is."""
        uri = _to_uri("http://example.org/foo")
        assert uri.value == "http://example.org/foo"

    def test_from_uri_node(self):
        """Reverse mapping of node template namespace."""
        internal = _from_uri(_NODE_TPL.replace("$id", "BOOK_001"))
        assert internal == "BOOK_001"

    def test_from_uri_known_prefix(self):
        """Reverse mapping of known prefix namespace."""
        internal = _from_uri("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        assert internal == "rdf:type"

    def test_from_uri_resource(self):
        """Reverse mapping of predicate template namespace."""
        internal = _from_uri(_PRED_TPL.replace("$id", "rs:hasAuthor"))
        assert internal == "rs:hasAuthor"

    def test_from_uri_full_http(self):
        """Full http/https URIs pass through as-is."""
        internal = _from_uri("http://example.org/foo")
        assert internal == "http://example.org/foo"

    def test_from_uri_unknown(self):
        """Unmappable URI raises ValueError."""
        with pytest.raises(ValueError):
            _from_uri("urn:isbn:12345")

    def test_to_rdf_term_uri(self):
        """URI object creates NamedNode."""
        term = _to_rdf_term({"object_value": "BOOK_001", "object_type": "node"})
        assert isinstance(term, ox.NamedNode)
        assert term.value == _NODE_TPL.replace("$id", "BOOK_001")

    def test_to_rdf_term_literal(self):
        """Literal object creates Literal."""
        term = _to_rdf_term({"object_value": "Hello", "object_type": "literal"})
        assert isinstance(term, ox.Literal)
        assert term.value == "Hello"

    def test_to_rdf_term_literal_with_lang(self):
        """Literal with language tag."""
        term = _to_rdf_term({
            "object_value": "Bonjour", "object_type": "literal",
            "object_lang": "fr",
        })
        assert isinstance(term, ox.Literal)
        assert term.value == "Bonjour"
        assert term.language == "fr"

    def test_to_rdf_term_literal_with_datatype(self):
        """Literal with datatype."""
        term = _to_rdf_term({
            "object_value": "42", "object_type": "literal",
            "object_datatype": "http://www.w3.org/2001/XMLSchema#integer",
        })
        assert isinstance(term, ox.Literal)
        assert term.value == "42"
        assert term.datatype.value == "http://www.w3.org/2001/XMLSchema#integer"

    def test_empty_id_raises(self):
        """Empty internal ID raises ValueError."""
        with pytest.raises(ValueError):
            _to_uri("")


# ═══════════════════════════════════════════════════════════════════════════
# SyncBacklog tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSyncBacklog:
    """Test the backlog retry mechanism."""

    def test_enqueue_and_process(self):
        """Enqueue an operation then process it."""
        store = ox.Store()
        backlog = SyncBacklog(max_retries=3, base_delay=0.1)
        triple = {"subject_id": "S1", "predicate_id": "p1",
                  "object_value": "O1", "object_type": "node"}

        backlog.enqueue("add", triple)
        assert len(backlog) == 1

        processed = backlog.process_pending(store)
        assert processed >= 1
        assert len(backlog) == 0

        result = store.query("SELECT * WHERE { ?s ?p ?o }")
        count = sum(1 for _ in result)
        assert count == 1

    def test_backlog_retries_and_drops(self):
        """Backlog retries and drops after max_retries."""
        store = ox.Store()
        backlog = SyncBacklog(max_retries=2, base_delay=0.1)

        # Enqueue an op with empty IDs — _to_uri("") raises ValueError
        bad_triple = {"subject_id": "", "predicate_id": "",
                      "object_value": "", "object_type": "node"}
        backlog.enqueue("add", bad_triple)
        assert len(backlog) == 1

        # First retry — fails, still queued
        backlog.process_pending(store)
        assert len(backlog) == 1

        # Second retry — fails again, max_retries reached
        backlog.process_pending(store)
        assert len(backlog) == 0  # dropped


# ═══════════════════════════════════════════════════════════════════════════
# SparqlEngine tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sparql_db(tmp_path: Path):
    """Create a minimal SQLite database for SparqlEngine tests."""
    from semantika.core import SemantikaDB

    db = SemantikaDB(tmp_path / "test.db")

    db.execute(
        "CREATE TABLE IF NOT EXISTS nodes ("
        "  node_id TEXT PRIMARY KEY,"
        "  iri TEXT NOT NULL DEFAULT '',"
        "  labels TEXT NOT NULL DEFAULT '{}',"
        "  label_text TEXT NOT NULL DEFAULT '',"
        "  definitions TEXT NOT NULL DEFAULT '{}',"
        "  definition_text TEXT NOT NULL DEFAULT '',"
        "  created_at TEXT NOT NULL,"
        "  updated_at TEXT NOT NULL"
        ")"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS predicates ("
        "  predicate_id TEXT PRIMARY KEY,"
        "  iri TEXT NOT NULL DEFAULT '',"
        "  source TEXT NOT NULL DEFAULT 'manual',"
        "  labels TEXT NOT NULL DEFAULT '{}',"
        "  descriptions TEXT NOT NULL DEFAULT '{}',"
        "  aliases TEXT NOT NULL DEFAULT '[]',"
        "  created_at TEXT NOT NULL,"
        "  updated_at TEXT NOT NULL"
        ")"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS triples ("
        "  subject_id TEXT NOT NULL,"
        "  predicate_id TEXT NOT NULL,"
        "  object_type TEXT NOT NULL DEFAULT 'node',"
        "  object_value TEXT NOT NULL,"
        "  object_lang TEXT DEFAULT NULL,"
        "  object_datatype TEXT DEFAULT NULL,"
        "  object_unit TEXT DEFAULT NULL,"
        "  created_at TEXT NOT NULL,"
        "  PRIMARY KEY (subject_id, predicate_id, object_value, object_type)"
        ") WITHOUT ROWID"
    )
    # Proofs table needed for cascade-delete in NodeService/PredicateService
    db.execute(
        "CREATE TABLE IF NOT EXISTS proofs ("
        "  uuid TEXT PRIMARY KEY,"
        "  subject_id TEXT NOT NULL,"
        "  predicate_id TEXT NOT NULL,"
        "  object_value TEXT NOT NULL,"
        "  object_type TEXT NOT NULL DEFAULT 'node',"
        "  proof_type TEXT NOT NULL DEFAULT 'observation',"
        "  source TEXT NOT NULL DEFAULT '',"
        "  notes TEXT NOT NULL DEFAULT '',"
        "  created_at TEXT NOT NULL,"
        "  updated_at TEXT NOT NULL"
        ")"
    )
    db.execute("PRAGMA foreign_keys=ON")
    return db


@pytest.fixture
def engine(tmp_path: Path, sparql_db):
    """Create a SparqlEngine with a temporary RocksDB cache."""
    eng = SparqlEngine(sparql_db, cache_dir=tmp_path / "sparql-cache")
    yield eng
    eng.close()


class TestSparqlEngine:
    """Test SparqlEngine query execution and enrichment."""

    def test_sync_and_query(self, engine: SparqlEngine):
        """Add a triple via sync hook and query it back."""
        engine.on_triple_added({
            "subject_id": "BOOK_001",
            "predicate_id": "rdf:type",
            "object_value": "Novel",
            "object_type": "node",
        })
        result = engine.execute("SELECT * WHERE { ?s ?p ?o }")
        assert "results" in result
        bindings = result["results"]["bindings"]
        assert len(bindings) == 1
        # rdf:type → http://www.w3.org/1999/02/22-rdf-syntax-ns#type
        assert bindings[0]["p"]["value"] == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
        assert "node/BOOK_001" in bindings[0]["s"]["value"]

    def test_sync_and_remove(self, engine: SparqlEngine):
        """Remove a triple via sync hook and verify it's gone."""
        triple = {
            "subject_id": "BOOK_001",
            "predicate_id": "rdf:type",
            "object_value": "Novel",
            "object_type": "node",
        }
        engine.on_triple_added(triple)
        engine.on_triple_removed(triple)
        result = engine.execute("SELECT * WHERE { ?s ?p ?o }")
        bindings = result["results"]["bindings"]
        assert len(bindings) == 0

    def test_ask_query(self, engine: SparqlEngine):
        """ASK query returns boolean."""
        engine.on_triple_added({
            "subject_id": "S1", "predicate_id": "p1",
            "object_value": "O1", "object_type": "node",
        })
        result = engine.execute("ASK { ?s ?p ?o }")
        assert result["boolean"] is True

        # Use a valid IRI pattern for non-matching
        result = engine.execute("ASK { ?s ?p <http://nonexistent> }")
        assert result["boolean"] is False

    def test_query_with_enrichment(self, engine: SparqlEngine, sparql_db):
        """URI bindings get enriched with labels from SQLite."""
        sparql_db.execute(
            "INSERT INTO nodes (node_id, labels, label_text, definitions, "
            "definition_text, created_at, updated_at) "
            "VALUES ('BOOK_001', '{\"en\": \"The Great Gatsby\"}', "
            "'The Great Gatsby', '{}', '', '2026-01-01', '2026-01-01')"
        )
        engine.on_triple_added({
            "subject_id": "BOOK_001",
            "predicate_id": "rdf:type",
            "object_value": "Novel",
            "object_type": "node",
        })
        result = engine.execute("SELECT ?s WHERE { ?s ?p ?o }")
        bindings = result["results"]["bindings"]
        assert len(bindings) == 1
        s_binding = bindings[0]["s"]
        assert s_binding["_label"] == "The Great Gatsby"

    def test_construct_query(self, engine: SparqlEngine):
        """CONSTRUCT query returns Turtle data."""
        engine.on_triple_added({
            "subject_id": "S1", "predicate_id": "p1",
            "object_value": "O1", "object_type": "node",
        })
        result = engine.execute("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")
        assert "data" in result
        assert "format" in result
        assert result["format"] == "turtle"
        assert "S1" in result["data"] or "O1" in result["data"]

    def test_max_query_length(self, engine: SparqlEngine):
        """Query exceeding MAX_QUERY_LENGTH raises ValueError."""
        long_query = "SELECT * WHERE { ?s ?p ?o }" + (" " * engine.MAX_QUERY_LENGTH)
        with pytest.raises(ValueError, match="exceeds maximum length"):
            engine.execute(long_query)

    def test_sync_triple_metadata_update(self, engine: SparqlEngine):
        """Update metadata using on_triple_updated."""
        old_triple = {
            "subject_id": "S1", "predicate_id": "p1", "object_value": "Hello",
            "object_type": "literal", "object_lang": None,
        }
        new_triple = {
            "subject_id": "S1", "predicate_id": "p1", "object_value": "Hello",
            "object_type": "literal", "object_lang": "en",
        }
        engine.on_triple_added(old_triple)
        engine.on_triple_updated(old_triple, new_triple)

        result = engine.execute("SELECT * WHERE { ?s ?p ?o }")
        bindings = result["results"]["bindings"]
        assert len(bindings) == 1

    def test_backlog_size(self, engine: SparqlEngine):
        """backlog_size property reflects pending retries."""
        assert engine.backlog_size == 0
        engine.on_triple_added({
            "subject_id": "", "predicate_id": "",
            "object_value": "", "object_type": "node",
        })
        assert engine.backlog_size >= 1


# ═══════════════════════════════════════════════════════════════════════════
# IRI resolution cache tests (Option B)
# ═══════════════════════════════════════════════════════════════════════════


class TestIriResolution:
    """Test _resolve_iri cache behaviour."""

    def test_resolve_bare_node(self, engine: SparqlEngine, sparql_db):
        """A bare node ID without a custom iri column gets the template IRI."""
        sparql_db.execute(
            "INSERT INTO nodes (node_id, labels, created_at, updated_at) "
            "VALUES ('BOOK_001', '{}', '2024-01-01', '2024-01-01')"
        )
        iri = engine._resolve_iri("BOOK_001", kind="node")
        assert iri == _NODE_TPL.replace("$id", "BOOK_001")

    def test_resolve_node_with_custom_iri(self, engine: SparqlEngine, sparql_db):
        """A node with a stored iri column returns the custom IRI."""
        sparql_db.execute(
            "INSERT INTO nodes (node_id, iri, labels, created_at, updated_at) "
            "VALUES ('CUSTOM', 'https://purl.org/custom', '{}', '2024-01-01', '2024-01-01')"
        )
        iri = engine._resolve_iri("CUSTOM", kind="node")
        assert iri == "https://purl.org/custom"

    def test_resolve_cache_hit(self, engine: SparqlEngine, sparql_db):
        """After the first resolution, subsequent calls hit the cache."""
        sparql_db.execute(
            "INSERT INTO nodes (node_id, labels, created_at, updated_at) "
            "VALUES ('CACHED', '{}', '2024-01-01', '2024-01-01')"
        )
        # First call — populates cache
        iri1 = engine._resolve_iri("CACHED", kind="node")
        assert iri1 == _NODE_TPL.replace("$id", "CACHED")
        # Delete from DB to prove cache is used
        sparql_db.execute("DELETE FROM nodes WHERE node_id = 'CACHED'")
        iri2 = engine._resolve_iri("CACHED", kind="node")
        assert iri2 == iri1  # Cache hit — still returns cached value

    def test_resolve_known_prefix_predicate(self, engine: SparqlEngine, sparql_db):
        """Known-prefix predicate (rdf:type) resolves without DB query."""
        iri = engine._resolve_iri("rdf:type", kind="predicate")
        assert iri == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    def test_clear_cache(self, engine: SparqlEngine, sparql_db):
        """clear_iri_cache() empties the cache so next call re-queries."""
        sparql_db.execute(
            "INSERT INTO nodes (node_id, labels, created_at, updated_at) "
            "VALUES ('CLR', '{}', '2024-01-01', '2024-01-01')"
        )
        engine._resolve_iri("CLR", kind="node")
        engine.clear_iri_cache()
        # After clear, should re-query (which still works)
        iri = engine._resolve_iri("CLR", kind="node")
        assert iri == _NODE_TPL.replace("$id", "CLR")


# ═══════════════════════════════════════════════════════════════════════════
# Dual-path enrichment tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDualPathEnrichment:
    """Test the dual-path enrichment logic in _serialize_solutions."""

    def test_template_path(self, engine: SparqlEngine, sparql_db):
        """An IRI matching the node template prefix is resolved by string-op."""
        sparql_db.execute(
            "INSERT INTO nodes (node_id, labels, created_at, updated_at) "
            "VALUES ('GATSBY', '{\"en\": \"The Great Gatsby\"}', '2024-01-01', '2024-01-01')"
        )
        # Sync a triple so Oxigraph has it
        iri = _NODE_TPL.replace("$id", "GATSBY")
        engine._iri_cache["GATSBY"] = iri
        engine.on_triple_added({
            "subject_id": "GATSBY",
            "predicate_id": "rdf:type",
            "object_value": "Novel",
            "object_type": "node",
        })
        result = engine.execute(
            "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
            "SELECT ?s WHERE { ?s rdf:type ?o }"
        )
        bindings = result["results"]["bindings"]
        assert len(bindings) == 1
        s = bindings[0]["s"]
        assert s["_label"] == "The Great Gatsby"
        assert s["_type"] == "node"
        assert s["_id"] == "GATSBY"

    def test_custom_iri_path(self, engine: SparqlEngine, sparql_db):
        """An IRI that does NOT match the template prefix queries the iri column."""
        custom_iri = "https://purl.org/my-node"
        sparql_db.execute(
            "INSERT INTO nodes (node_id, iri, labels, created_at, updated_at) "
            "VALUES ('PURL', ?, '{\"en\": \"Purl Node\"}', '2024-01-01', '2024-01-01')",
            (custom_iri,),
        )
        # Sync a triple with the custom IRI
        engine._iri_cache["PURL"] = custom_iri
        engine.on_triple_added({
            "subject_id": "PURL",
            "predicate_id": "rdf:type",
            "object_value": "Thing",
            "object_type": "node",
        })
        result = engine.execute(
            "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
            "SELECT ?s WHERE { ?s rdf:type ?o }"
        )
        bindings = result["results"]["bindings"]
        assert len(bindings) == 1
        s = bindings[0]["s"]
        assert s["_label"] == "Purl Node"
        assert s["_type"] == "node"
        assert s["_id"] == "PURL"
        # The IRI in the SPARQL result IS the custom one
        assert s["value"] == custom_iri

    def test_known_prefix_iri_path(self, engine: SparqlEngine, sparql_db):
        """IRIs from known prefix namespaces (rdf:) query the iri column."""
        # A predicate with a fixed standard IRI
        sparql_db.execute(
            "INSERT INTO predicates (predicate_id, iri, labels, created_at, updated_at) "
            "VALUES ('ex:custom', 'http://example.org/custom', '{}', '2024-01-01', '2024-01-01')"
        )
        engine._iri_cache["ex:custom"] = "http://example.org/custom"
        engine.on_triple_added({
            "subject_id": "GATSBY",
            "predicate_id": "ex:custom",
            "object_value": "Novel",
            "object_type": "node",
        })
        # We need the subject too
        sparql_db.execute(
            "INSERT INTO nodes (node_id, labels, created_at, updated_at) "
            "VALUES ('GATSBY', '{}', '2024-01-01', '2024-01-01')"
        )
        engine._iri_cache["GATSBY"] = _NODE_TPL.replace("$id", "GATSBY")
        result = engine.execute(
            "PREFIX ex: <http://example.org/> "
            "SELECT ?p WHERE { ?s ?p ?o }"
        )
        bindings = result["results"]["bindings"]
        assert len(bindings) == 1
        p = bindings[0]["p"]
        assert p["_label"] == "ex:custom"  # fallback to predicate_id
        assert p["_type"] == "predicate"
        assert p["_id"] == "ex:custom"


# ═══════════════════════════════════════════════════════════════════════════
# Incremental sync integration tests
# ═══════════════════════════════════════════════════════════════════════════


class TestIncrementalSync:
    """Test that TripleService mutations are synced to the SPARQL cache."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path, sparql_db):
        """Initialize services and SPARQL engine for each test."""
        self.db = sparql_db
        from semantika.graph.triple_service import TripleService
        from semantika.graph.node_service import NodeService
        from semantika.graph.predicate_service import PredicateService

        self.engine = SparqlEngine(sparql_db, cache_dir=tmp_path / "sync-cache")
        self.triple_svc = TripleService(sparql_db)
        self.triple_svc._sparql_engine = self.engine
        self.node_svc = NodeService(sparql_db)
        self.node_svc._sparql_engine = self.engine
        self.pred_svc = PredicateService(sparql_db)
        self.pred_svc._sparql_engine = self.engine

        # Seed nodes and predicates
        self.db.execute(
            "INSERT INTO nodes (node_id, labels, label_text, definitions, "
            "definition_text, created_at, updated_at) "
            "VALUES ('N1', '{}', '', '{}', '', '2026-01-01', '2026-01-01')"
        )
        self.db.execute(
            "INSERT INTO nodes (node_id, labels, label_text, definitions, "
            "definition_text, created_at, updated_at) "
            "VALUES ('O1', '{}', '', '{}', '', '2026-01-01', '2026-01-01')"
        )
        self.db.execute(
            "INSERT INTO predicates (predicate_id, source, labels, descriptions, "
            "aliases, created_at, updated_at) "
            "VALUES ('p1', 'manual', '{}', '{}', '[]', '2026-01-01', '2026-01-01')"
        )
        yield
        self.engine.close()

    def test_triple_add_syncs_to_sparql(self):
        """TripleService.add() syncs triple to RocksDB cache."""
        self.triple_svc.add("N1", "p1", "O1", object_type="node")
        result = self.engine.execute("SELECT * WHERE { ?s ?p ?o }")
        assert len(result["results"]["bindings"]) == 1

    def test_triple_remove_syncs_to_sparql(self):
        """TripleService.remove() syncs removal to RocksDB cache."""
        self.triple_svc.add("N1", "p1", "O1", object_type="node")
        self.triple_svc.remove(subject_id="N1")
        result = self.engine.execute("SELECT * WHERE { ?s ?p ?o }")
        assert len(result["results"]["bindings"]) == 0

    def test_node_delete_syncs_cascade(self):
        """NodeService.delete() syncs cascade-deleted triples."""
        self.triple_svc.add("N1", "p1", "O1", object_type="node")
        self.node_svc.delete("N1", soft=False)
        result = self.engine.execute("SELECT * WHERE { ?s ?p ?o }")
        assert len(result["results"]["bindings"]) == 0

    def test_predicate_delete_syncs_cascade(self):
        """PredicateService.delete() syncs cascade-deleted triples."""
        self.triple_svc.add("N1", "p1", "O1", object_type="node")
        self.pred_svc.delete("p1", soft=False)
        result = self.engine.execute("SELECT * WHERE { ?s ?p ?o }")
        assert len(result["results"]["bindings"]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# API route tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSparqlAPI:
    """Test the SPARQL API endpoints — /api/v1/query/sparql."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        close_sparql_engine()
        reset_services()
        clear_command_cache()

        # Patch data_dir to isolate the test database
        test_data_dir = tmp_path / "data"
        test_data_dir.mkdir(parents=True, exist_ok=True)
        from semantika import core as semantika_core
        monkeypatch.setattr(semantika_core, "data_dir", lambda: test_data_dir)
        from semantika.graph import db as graph_db
        monkeypatch.setattr(graph_db, "get_db_path", lambda: test_data_dir / "semantika.db")
        # Close any existing DB so the next get_db() uses the new path
        from semantika.core import db as core_db
        if hasattr(core_db, "_db_instance") and core_db._db_instance is not None:
            core_db._db_instance.close()
        graph_db._db_instance = None
        graph_db._db_path = None

        cache_dir = tmp_path / "api-sparql-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        init_sparql_engine(cache_dir=cache_dir)

        app = create_app()
        self.client = TestClient(app)

        # Seed data in correct order: nodes first, then predicates, then triples
        self.client.post("/api/v1/graph/nodes", json={
            "node_id": "N1", "labels": {"en": "Node One"},
        })
        self.client.post("/api/v1/graph/nodes", json={
            "node_id": "N2", "labels": {"en": "Node Two"},
        })
        self.client.post("/api/v1/graph/predicates", json={
            "predicate_id": "ex:testPred", "labels": {"en": "test predicate"},
        })
        self.client.post("/api/v1/graph/triples", json={
            "subject_id": "N1", "predicate_id": "ex:testPred",
            "object_value": "Hello World", "object_type": "literal",
        })
        yield

    def teardown_method(self):
        close_sparql_engine()
        reset_services()

    def test_get_sparql(self):
        """GET /api/v1/query/sparql?query=... returns results."""
        resp = self.client.get(
            "/api/v1/query/sparql",
            params={"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]["bindings"]) >= 1

    def test_get_sparql_empty(self):
        """GET without query returns empty results."""
        resp = self.client.get("/api/v1/query/sparql")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]["bindings"]) == 0

    def test_post_sparql(self):
        """POST with raw query body returns results."""
        resp = self.client.post(
            "/api/v1/query/sparql",
            content=b"SELECT * WHERE { ?s ?p ?o } LIMIT 10",
            headers={"Content-Type": "application/sparql-query"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_sparql_ask(self):
        """ASK query returns boolean."""
        resp = self.client.get(
            "/api/v1/query/sparql",
            params={"query": "ASK { ?s ?p ?o }"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "boolean" in data
        assert data["boolean"] is True

    def test_sparql_syntax_error(self):
        """Invalid SPARQL returns 400."""
        resp = self.client.get(
            "/api/v1/query/sparql",
            params={"query": "SELECT BROKEN {"},
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# !sparql command tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSparqlCommand:
    """Test the !sparql command dispatch."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from semantika.server.command.registry import clear_command_cache
        close_sparql_engine()
        reset_services()
        clear_command_cache()

        # Patch data_dir to isolate the test database
        test_data_dir = tmp_path / "data"
        test_data_dir.mkdir(parents=True, exist_ok=True)
        from semantika import core as semantika_core
        monkeypatch.setattr(semantika_core, "data_dir", lambda: test_data_dir)
        from semantika.graph import db as graph_db
        monkeypatch.setattr(graph_db, "get_db_path", lambda: test_data_dir / "semantika.db")
        from semantika.core import db as core_db
        if hasattr(core_db, "_db_instance") and core_db._db_instance is not None:
            core_db._db_instance.close()
        graph_db._db_instance = None
        graph_db._db_path = None

        cache_dir = tmp_path / "cmd-sparql-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        init_sparql_engine(cache_dir=cache_dir)

        app = create_app()
        self.client = TestClient(app)

        # Seed data
        self.client.post("/api/v1/graph/nodes", json={
            "node_id": "N1", "labels": {"en": "Node One"},
        })
        self.client.post("/api/v1/graph/nodes", json={
            "node_id": "N2", "labels": {"en": "Node Two"},
        })
        self.client.post("/api/v1/graph/nodes", json={
            "node_id": "CMD_OBJ", "labels": {"en": "Test Object"},
        })
        self.client.post("/api/v1/graph/predicates", json={
            "predicate_id": "ex:cmdPred", "labels": {"en": "cmd predicate"},
        })
        resp = self.client.post("/api/v1/graph/triples", json={
            "subject_id": "N1", "predicate_id": "ex:cmdPred",
            "object_value": "CMD_OBJ", "object_type": "node",
        })
        assert resp.status_code == 200, f"Triple creation failed: {resp.text}"
        yield

    def teardown_method(self):
        close_sparql_engine()
        reset_services()

    def test_sparql_query_command(self):
        """!sparql query returns table results."""
        resp = self.client.post(
            "/api/v1/command",
            json={
                "tokens": ["sparql", "query"],
                "flags": {"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10"},
            },
        )
        assert resp.status_code == 200, f"Query command failed: {resp.text}"
        data = resp.json()
        assert data["type"] == "table", f"Expected table, got {data}"
        assert "rows" in data["data"]
        assert len(data["data"]["rows"]) >= 1

    def test_sparql_ask_command(self):
        """!sparql query with ASK returns status."""
        resp = self.client.post(
            "/api/v1/command",
            json={
                "tokens": ["sparql", "query"],
                "flags": {"query": "ASK { ?s ?p ?o }"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"

    def test_sparql_status_command(self):
        """!sparql status returns engine status."""
        resp = self.client.post(
            "/api/v1/command",
            json={"tokens": ["sparql", "status"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert data["data"]["available"] is True

    def test_sparql_missing_query(self):
        """!sparql query without query string returns form-required."""
        resp = self.client.post(
            "/api/v1/command",
            json={"tokens": ["sparql", "query"], "flags": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "sparql-editor"
