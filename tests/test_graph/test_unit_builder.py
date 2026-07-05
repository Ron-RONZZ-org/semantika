"""Tests for UnitBuilder — compound unit node creation from AST.

Tests cover:
- Creating singleton units (with and without 'unit:' prefix)
- Idempotency for existing singletons
- Building compound nodes from parsed AST expressions
- Power nodes (m^2, m^-1)
- Product nodes (m/s → m * s^-1)
- Error handling for unresolvable unit names

Note: Relies on the DB having the seeded SI unit ontology. The
``seeded_env`` fixture triggers UnitService lazy seeding so that
resolve functions can find base units by label, symbol, or prefix.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from semantika.core import SemantikaDB
from semantika.core.exceptions import AmbiguousIDError
from semantika.graph.db import SCHEMA, TRIPLES_INDEXES
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.triple_service import TripleService
from semantika.graph.unit_builder import UnitBuilder
from semantika.graph.unit_service import UnitService
from semantika.graph.unit_parser import (
    parse,
    normalize,
    SingularUnit,
    UnitPower,
    UnitProduct,
)
from semantika.graph.unit_errors import UnitNotFoundError


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> SemantikaDB:
    """Create an isolated test database with full graph schema."""
    db_path = tmp_path / "test.db"
    db = SemantikaDB(db_path)
    for table, sql in SCHEMA.items():
        db.init_schema({table: sql})
    for idx in TRIPLES_INDEXES:
        db.execute(idx)
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
        "  node_id UNINDEXED, label_text, definition_text,"
        "  content=nodes, content_rowid=rowid, tokenize='unicode61'"
        ")"
    )
    db.execute("PRAGMA foreign_keys=ON")
    return db


@pytest.fixture
def node_svc(db: SemantikaDB) -> NodeService:
    return NodeService(db)


@pytest.fixture
def pred_svc(db: SemantikaDB) -> PredicateService:
    return PredicateService(db)


@pytest.fixture
def triple_svc(
    db: SemantikaDB,
    node_svc: NodeService,
    pred_svc: PredicateService,
) -> TripleService:
    """TripleService with basic predicates seeded."""
    for pid, source, labels in [
        ("ex:rel", "manual", {"en": "relation"}),
        ("rdf:type", "rdf", {"en": "type"}),
    ]:
        pred_svc.create({"predicate_id": pid, "labels": labels})
    return TripleService(db)


@pytest.fixture
def seeded_env(
    db: SemantikaDB,
    node_svc: NodeService,
    triple_svc: TripleService,
) -> UnitService:
    """Trigger UnitService lazy seeding so the DB has base/derived units.

    Returns the UnitService for additional convenience.
    """
    us = UnitService(db, node_svc, triple_svc)
    us.list_units()  # triggers _ensure_base_units
    return us


def _make_resolve_fn(db: SemantikaDB, node_svc: NodeService):
    """Build a resolve function suitable for UnitBuilder.

    Resolution chain (matching UnitService._resolve_word_to_node):
      1. Node ID prefix resolution
      2. Symbol lookup via ``:symbol`` triple
      3. Full-text / LIKE search fallback
    """

    def _resolve(word: str) -> dict:
        # 1. Prefix resolution
        try:
            node = node_svc.resolve_node_id_prefix(word)
            if node:
                return node
        except AmbiguousIDError:
            pass

        # 2. Symbol lookup
        sym_node = db.execute_one(
            "SELECT n.* FROM nodes n "
            "JOIN triples t ON t.subject_id = n.node_id "
            "WHERE t.predicate_id = ':symbol' AND t.object_value = ? "
            "AND t.object_type = 'literal'",
            (word,),
        )
        if sym_node:
            return sym_node

        # 3. Full-text / LIKE search (limit=2 for uniqueness check)
        results = node_svc.search(word, limit=2)
        if len(results) == 1:
            return results[0]

        raise ValueError(f"Cannot resolve unit: {word!r}")

    return _resolve


@pytest.fixture
def builder(
    db: SemantikaDB,
    node_svc: NodeService,
    seeded_env: UnitService,
) -> UnitBuilder:
    """UnitBuilder with seeded DB and resolve function."""
    resolve_fn = _make_resolve_fn(db, node_svc)
    return UnitBuilder(db, node_svc, resolve_fn)


# ── Tests ────────────────────────────────────────────────────────────────


class TestUnitBuilderCreateSingleton:
    """Tests for UnitBuilder.create_singleton()."""

    def test_create_singleton(self, builder: UnitBuilder, db: SemantikaDB):
        """create_singleton inserts a node and triples, returns the node_id."""
        nid = builder.create_singleton("MYUNIT", "My Unit", "mu")
        assert nid == "unit:MYUNIT"

        row = db.execute_one("SELECT * FROM nodes WHERE node_id = ?", (nid,))
        assert row is not None
        # The builder stores the label in the JSON `labels` column, not `label_text`
        import json
        labels = json.loads(row["labels"])
        assert labels.get("en") == "My Unit"

        # Check rdf:type triple
        type_triple = db.execute_one(
            "SELECT * FROM triples WHERE subject_id = ? AND predicate_id = 'rdf:type'",
            (nid,),
        )
        assert type_triple is not None
        assert type_triple["object_value"] == ":SingularUnit"

        # Check symbol triple
        sym_triple = db.execute_one(
            "SELECT * FROM triples WHERE subject_id = ? AND predicate_id = ':symbol'",
            (nid,),
        )
        assert sym_triple is not None
        assert sym_triple["object_value"] == "mu"

    def test_create_singleton_auto_prefix(self, builder: UnitBuilder):
        """If node_id does not start with 'unit:', it is automatically added."""
        nid = builder.create_singleton("MYUNIT", "My Unit", "mu")
        assert nid.startswith("unit:")

    def test_create_singleton_existing_is_idempotent(self, builder: UnitBuilder):
        """Creating the same singleton twice returns the same node_id."""
        nid1 = builder.create_singleton("MYUNIT", "My Unit", "mu")
        nid2 = builder.create_singleton("MYUNIT", "My Unit", "mu")
        assert nid1 == nid2

    def test_create_singleton_different_symbols(self, builder: UnitBuilder):
        """Two different singletons get different node_ids."""
        nid1 = builder.create_singleton("UNITA", "Unit A", "ua")
        nid2 = builder.create_singleton("UNITB", "Unit B", "ub")
        assert nid1 != nid2


class TestUnitBuilderCreateFromAst:
    """Tests for UnitBuilder.create_from_ast()."""

    def test_create_from_ast_singleton_by_label(self, builder: UnitBuilder):
        """A SingularUnit AST node resolves to the existing unit node_id."""
        from semantika.graph.unit_parser import SingularUnit

        ast = SingularUnit("meter")
        nid = builder.create_from_ast(ast)
        assert nid == "unit:METER"

    def test_create_from_ast_singleton_by_symbol(self, builder: UnitBuilder):
        """A SingularUnit AST node with symbol resolves correctly."""
        ast = SingularUnit("m")
        nid = builder.create_from_ast(ast)
        assert nid == "unit:METER"

    def test_create_from_ast_singleton_by_uppercase(self, builder: UnitBuilder):
        """A SingularUnit AST node for J (Joule) resolves correctly."""
        ast = SingularUnit("J")
        nid = builder.create_from_ast(ast)
        assert nid == "unit:JOULE"

    def test_create_from_ast_power_node(self, builder: UnitBuilder, db: SemantikaDB):
        """UnitPower (m^2) creates a UnitPower node with :hasBase and :hasExponent."""
        ast = normalize(parse("m^2"))
        nid = builder.create_from_ast(ast)
        assert nid is not None
        assert "METER" in nid
        assert any(s in nid for s in ("SQ", "POW"))

        # Verify the internal structure
        has_base = db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasBase'",
            (nid,),
        )
        assert has_base is not None
        assert has_base["object_value"] == "unit:METER"

        has_exp = db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasExponent'",
            (nid,),
        )
        assert has_exp is not None
        assert has_exp["object_value"] == "2"

    def test_create_from_ast_negative_exponent(self, builder: UnitBuilder, db: SemantikaDB):
        """UnitPower with negative exponent (s^-1) creates a power node."""
        ast = normalize(parse("s^-1"))
        nid = builder.create_from_ast(ast)
        assert nid is not None

        has_exp = db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasExponent'",
            (nid,),
        )
        assert has_exp is not None
        assert has_exp["object_value"] == "-1"

    def test_create_from_ast_product(self, builder: UnitBuilder, db: SemantikaDB):
        """UnitProduct (J/K → J * K^-1) creates a UnitProduct node."""
        ast = normalize(parse("J/K"))
        nid = builder.create_from_ast(ast)
        assert nid is not None

        has_term1 = db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasTerm1'",
            (nid,),
        )
        has_term2 = db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasTerm2'",
            (nid,),
        )
        assert has_term1 is not None
        assert has_term2 is not None
        # At least one of the terms should reference JOULE
        terms = {has_term1["object_value"], has_term2["object_value"]}
        joule_refs = [t for t in terms if "JOULE" in t]
        assert len(joule_refs) >= 1

    def test_create_from_ast_identity_product(self, builder: UnitBuilder):
        """1*m normalises to just m (identity stripped)."""
        ast = normalize(parse("1*m"))
        nid = builder.create_from_ast(ast)
        assert nid == "unit:METER"

    def test_create_from_ast_single_term_product(self, builder: UnitBuilder):
        """A product with a single term just resolves to that term."""
        ast = normalize(parse("m"))
        nid = builder.create_from_ast(ast)
        assert nid == "unit:METER"

    def test_create_from_ast_unknown_raises(self, builder: UnitBuilder):
        """An unresolvable SingularUnit raises ValueError."""
        ast = SingularUnit("zzz_not_a_unit_12345")
        with pytest.raises(ValueError, match="Cannot resolve"):
            builder.create_from_ast(ast)

    def test_create_from_ast_unsupported_type_raises(self, builder: UnitBuilder):
        """An unsupported expression type raises UnitNotFoundError."""
        from semantika.graph.unit_parser import UnitExpression

        class FakeExpr(UnitExpression):
            pass

        with pytest.raises(UnitNotFoundError, match="Unsupported"):
            builder.create_from_ast(FakeExpr())


class TestUnitBuilderIntegration:
    """Integration-level tests that exercise the full pipeline.

    These tests go through UnitService.resolve_unit so that the
    resolve + create_from_ast flow is tested as a whole.
    """

    def test_compound_m_per_s(self, builder: UnitBuilder, db: SemantikaDB):
        """m/s creates a product with term1=METER and term2=SECOND^{-1}."""
        ast = normalize(parse("m/s"))
        nid = builder.create_from_ast(ast)
        assert nid is not None

    def test_compound_newton(self, builder: UnitBuilder, db: SemantikaDB):
        """kg*m/s^2 (Newton) creates a multi-term product chain."""
        ast = normalize(parse("kg*m/s^2"))
        nid = builder.create_from_ast(ast)
        assert nid is not None

    def test_two_term_product_is_binary(self, builder: UnitBuilder, db: SemantikaDB):
        """A two-term product creates exactly one UnitProduct node."""
        ast = normalize(parse("J/K"))
        nid = builder.create_from_ast(ast)

        # The root should be a UnitProduct
        type_row = db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = 'rdf:type' AND object_type = 'uri'",
            (nid,),
        )
        assert type_row is not None
        assert type_row["object_value"] == ":UnitProduct"

    def test_repeated_resolve_returns_same_node(self, builder: UnitBuilder):
        """Calling create_from_ast twice with the same AST is idempotent."""
        ast = normalize(parse("m^2"))
        nid1 = builder.create_from_ast(ast)
        nid2 = builder.create_from_ast(ast)
        assert nid1 == nid2
