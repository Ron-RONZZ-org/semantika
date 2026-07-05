"""Tests for UnitService — unit ontology management.

Tests cover:
- Lazy seeding of base SI units, derived units, and prefixes
- Listing all units and filtering custom ones
- Getting detailed unit info (symbol, type, decomposition)
- Resolving units by exact node_id, symbol, prefix, or compound expression
- Normalizing unit references without auto-creation
- Creating custom singleton units
- Decomposition of compound units via the decomposer
- Error cases: nonexistent units, unresolvable expressions
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from semantika.core import SemantikaDB
from semantika.graph.db import SCHEMA, TRIPLES_INDEXES
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.triple_service import TripleService
from semantika.graph.unit_service import UnitService
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
def triple_svc(db: SemantikaDB, node_svc: NodeService, pred_svc: PredicateService) -> TripleService:
    """TripleService with basic predicates seeded."""
    for pid, source, labels in [
        ("ex:rel", "manual", {"en": "relation"}),
        ("rdf:type", "rdf", {"en": "type"}),
    ]:
        pred_svc.create({"predicate_id": pid, "labels": labels})
    return TripleService(db)


@pytest.fixture
def unit_svc(
    db: SemantikaDB,
    node_svc: NodeService,
    triple_svc: TripleService,
) -> UnitService:
    """UnitService with lazy-initialised unit ontology."""
    return UnitService(db, node_svc, triple_svc)


# ── Tests ────────────────────────────────────────────────────────────────


class TestUnitServiceList:
    """Tests for list_units()."""

    def test_list_units_returns_seeded(self, unit_svc: UnitService):
        """list_units() returns all seeded SI units after lazy init."""
        units = unit_svc.list_units()
        assert len(units) > 0
        ids = [u["node_id"] for u in units]
        # Base units
        assert "unit:METER" in ids
        assert "unit:KILOGRAM" in ids
        assert "unit:SECOND" in ids
        assert "unit:AMPERE" in ids
        assert "unit:KELVIN" in ids
        assert "unit:MOLE" in ids
        assert "unit:CANDELA" in ids
        # Derived units
        assert "unit:HERTZ" in ids
        assert "unit:NEWTON" in ids
        assert "unit:JOULE" in ids
        assert "unit:WATT" in ids

    def test_list_units_includes_custom(self, unit_svc: UnitService):
        """Custom units created via create_singleton appear in the listing."""
        unit_svc.create_singleton("GIGAANNUM", "Giga-annum", "Ga")
        ids = [u["node_id"] for u in unit_svc.list_units()]
        assert "unit:GIGAANNUM" in ids

    def test_list_units_returns_unit_type(self, unit_svc: UnitService):
        """Each listed unit has a unit_type field."""
        units = unit_svc.list_units()
        for u in units:
            assert "unit_type" in u
            assert u["unit_type"] in (":SingularUnit", ":PrefixedUnit", "")

    def test_list_units_returns_symbol(self, unit_svc: UnitService):
        """Each listed unit has a unit_symbol field (may be empty for type nodes)."""
        units = unit_svc.list_units()
        meter = next(u for u in units if u["node_id"] == "unit:METER")
        assert meter["unit_symbol"] == "m"

    def test_list_units_is_idempotent(self, unit_svc: UnitService):
        """Seeding is lazy and idempotent; repeated calls don't duplicate."""
        first = unit_svc.list_units()
        second = unit_svc.list_units()
        assert len(first) == len(second)


class TestUnitServiceGetInfo:
    """Tests for get_unit_info()."""

    def test_get_unit_info_meter(self, unit_svc: UnitService):
        """get_unit_info returns symbol and type for a base unit."""
        info = unit_svc.get_unit_info("unit:METER")
        assert info is not None
        assert info["unit_symbol"] == "m"
        assert info["unit_type"] == ":SingularUnit"

    def test_get_unit_info_derived(self, unit_svc: UnitService):
        """get_unit_info returns info for a derived unit (JOULE)."""
        info = unit_svc.get_unit_info("unit:JOULE")
        assert info is not None
        assert info["unit_symbol"] == "J"
        assert info["unit_type"] == ":SingularUnit"

    def test_get_unit_info_nonexistent(self, unit_svc: UnitService):
        """get_unit_info returns None for a nonexistent unit."""
        assert unit_svc.get_unit_info("unit:NONEXISTENT") is None

    def test_get_unit_info_by_prefix(self, unit_svc: UnitService):
        """get_unit_info accepts a node_id prefix."""
        info = unit_svc.get_unit_info("unit:MET")  # matches unit:METER unambiguously
        assert info is not None
        assert info["node_id"] == "unit:METER"

    def test_get_unit_info_returns_decomposition(self, unit_svc: UnitService):
        """get_unit_info includes a decomposition field."""
        info = unit_svc.get_unit_info("unit:METER")
        assert info is not None
        assert "decomposition" in info


class TestUnitServiceResolve:
    """Tests for resolve_unit()."""

    def test_resolve_by_exact_node_id(self, unit_svc: UnitService):
        """resolve_unit with exact node_id returns it unchanged."""
        nid = unit_svc.resolve_unit("unit:METER")
        assert nid == "unit:METER"

    def test_resolve_by_symbol(self, unit_svc: UnitService):
        """resolve_unit with unit symbol returns canonical node_id."""
        nid = unit_svc.resolve_unit("m")
        assert nid == "unit:METER"

    def test_resolve_by_case_insensitive_node_id(self, unit_svc: UnitService):
        """resolve_unit is case-insensitive for node_id matching."""
        nid = unit_svc.resolve_unit("unit:meter")
        assert nid == "unit:METER"

    def test_resolve_joule(self, unit_svc: UnitService):
        """resolve_unit('J') returns unit:JOULE."""
        nid = unit_svc.resolve_unit("J")
        assert nid == "unit:JOULE"

    def test_resolve_kelvin(self, unit_svc: UnitService):
        """resolve_unit('K') returns unit:KELVIN."""
        nid = unit_svc.resolve_unit("K")
        assert nid == "unit:KELVIN"

    def test_resolve_hertz(self, unit_svc: UnitService):
        """resolve_unit('Hz') returns unit:HERTZ."""
        nid = unit_svc.resolve_unit("Hz")
        assert nid == "unit:HERTZ"

    def test_resolve_compound_expression(self, unit_svc: UnitService):
        """resolve_unit with J/K creates compound nodes and returns root."""
        nid = unit_svc.resolve_unit("J/K")
        assert nid is not None
        assert "JOULE" in nid

    def test_resolve_square_meter(self, unit_svc: UnitService):
        """resolve_unit('m^2') creates a UnitPower node."""
        nid = unit_svc.resolve_unit("m^2")
        assert nid is not None
        assert "METER" in nid
        assert any(suffix in nid for suffix in ("SQ", "POW"))

    def test_resolve_cubic_meter(self, unit_svc: UnitService):
        """resolve_unit('m^3') creates a cubic UnitPower node."""
        nid = unit_svc.resolve_unit("m^3")
        assert nid is not None
        assert "CU" in nid or "POW3" in nid

    def test_resolve_compound_twice_is_idempotent(self, unit_svc: UnitService):
        """Resolving the same expression twice returns the same node_id."""
        nid1 = unit_svc.resolve_unit("J/K")
        nid2 = unit_svc.resolve_unit("J/K")
        assert nid1 == nid2

    def test_resolve_nonexistent_raises(self, unit_svc: UnitService):
        """resolve_unit raises UnitNotFoundError for unresolvable expression."""
        with pytest.raises(UnitNotFoundError):
            unit_svc.resolve_unit("this_unit_definitely_does_not_exist_42")

    def test_resolve_empty_raises(self, unit_svc: UnitService):
        """resolve_unit with empty string raises ValueError."""
        with pytest.raises((ValueError, UnitNotFoundError)):
            unit_svc.resolve_unit("")


class TestUnitServiceNormalize:
    """Tests for normalize_unit()."""

    def test_normalize_by_node_id(self, unit_svc: UnitService):
        """normalize_unit with exact node_id returns canonical form."""
        assert unit_svc.normalize_unit("unit:METER") == "unit:METER"

    def test_normalize_by_symbol(self, unit_svc: UnitService):
        """normalize_unit with symbol returns canonical node_id."""
        assert unit_svc.normalize_unit("m") == "unit:METER"

    def test_normalize_by_case_insensitive(self, unit_svc: UnitService):
        """normalize_unit is case-insensitive for node_id."""
        assert unit_svc.normalize_unit("unit:meter") == "unit:METER"

    def test_normalize_by_label_search(self, unit_svc: UnitService):
        """normalize_unit falls back to label search for full names."""
        nid = unit_svc.normalize_unit("meter")
        assert nid == "unit:METER"

    def test_normalize_unresolvable_returns_input(self, unit_svc: UnitService):
        """normalize_unit returns input unchanged when nothing matches."""
        result = unit_svc.normalize_unit("not_a_unit_at_all_12345")
        assert result == "not_a_unit_at_all_12345"


class TestUnitServiceCreate:
    """Tests for create_singleton()."""

    def test_create_singleton_custom_unit(self, unit_svc: UnitService):
        """create_singleton creates a custom SingularUnit and returns its ID."""
        nid = unit_svc.create_singleton("MYUNIT", "My Custom Unit", "myu")
        assert nid == "unit:MYUNIT"

        info = unit_svc.get_unit_info(nid)
        assert info is not None
        assert info["unit_symbol"] == "myu"
        assert info["unit_type"] == ":SingularUnit"

    def test_create_singleton_existing_is_idempotent(self, unit_svc: UnitService):
        """Creating a singleton with an existing node_id does not error."""
        nid1 = unit_svc.create_singleton("MYUNIT", "My Custom Unit", "myu")
        nid2 = unit_svc.create_singleton("MYUNIT", "My Custom Unit", "myu")
        assert nid1 == nid2

    def test_create_singleton_appears_in_list(self, unit_svc: UnitService):
        """A newly created singleton appears in list_units()."""
        unit_svc.create_singleton("LIGHTYEAR", "Light Year", "ly")
        ids = [u["node_id"] for u in unit_svc.list_units()]
        assert "unit:LIGHTYEAR" in ids

    def test_create_singleton_auto_prefix(self, unit_svc: UnitService):
        """If node_id lacks 'unit:' prefix, it is prepended."""
        nid = unit_svc.create_singleton("TEST", "Test", "t")
        assert nid.startswith("unit:")


class TestUnitServiceDecomposition:
    """Tests for unit decomposition via unit_svc.decomposer."""

    def test_decompose_base_unit_returns_empty(self, unit_svc: UnitService):
        """A base unit (e.g. METER) has no decomposition."""
        decomp = unit_svc.decomposer.get_decomposition("unit:METER")
        assert decomp == ""

    def test_decompose_power(self, unit_svc: UnitService):
        """m^2 decomposes to a string containing m and exponent."""
        nid = unit_svc.resolve_unit("m^2")
        decomp = unit_svc.decomposer.get_decomposition(nid)
        assert "m" in decomp
        assert "2" in decomp

    def test_decompose_product_with_denominator(self, unit_svc: UnitService):
        """J/K decomposes showing numerator / denominator."""
        nid = unit_svc.resolve_unit("J/K")
        decomp = unit_svc.decomposer.get_decomposition(nid)
        assert "/" in decomp
        assert "J" in decomp
        assert "K" in decomp

    def test_decompose_nonexistent(self, unit_svc: UnitService):
        """get_decomposition returns '' for a nonexistent node_id."""
        assert unit_svc.decomposer.get_decomposition("unit:NONEXISTENT") == ""

    def test_decompose_compound_idempotent(self, unit_svc: UnitService):
        """Decomposing the same compound unit twice gives the same result."""
        nid = unit_svc.resolve_unit("kg*m^2/s^2")  # Joule-like
        d1 = unit_svc.decomposer.get_decomposition(nid)
        d2 = unit_svc.decomposer.get_decomposition(nid)
        assert d1 == d2

    def test_format_unit_ref_uses_symbol(self, unit_svc: UnitService, db: SemantikaDB):
        """format_unit_ref returns the symbol when available."""
        # Trigger seeding so the DB has :symbol triples
        unit_svc.list_units()
        from semantika.graph.unit_decomposition import format_unit_ref
        ref = format_unit_ref(db, "unit:METER")
        assert ref == "m"

    def test_format_unit_ref_falls_back_to_local_name(self, db: SemantikaDB):
        """format_unit_ref returns the local part of node_id when no symbol."""
        from semantika.graph.unit_decomposition import format_unit_ref
        ref = format_unit_ref(db, "unit:NONEXISTENT")
        assert ref == "NONEXISTENT"


class TestUnitServiceEdgeCases:
    """Edge cases and error handling."""

    def test_multiple_resolves_different_expressions(self, unit_svc: UnitService):
        """Different expressions resolve to different node_ids."""
        nid1 = unit_svc.resolve_unit("m^2")
        nid2 = unit_svc.resolve_unit("m^3")
        assert nid1 != nid2

    def test_builder_lazy_initialized(self, unit_svc: UnitService):
        """Builder property is lazily created."""
        builder = unit_svc.builder
        assert builder is not None
        # Accessing again returns the same instance
        assert unit_svc.builder is builder

    def test_decomposer_lazy_initialized(self, unit_svc: UnitService):
        """Decomposer property is lazily created."""
        decomposer = unit_svc.decomposer
        assert decomposer is not None
        assert unit_svc.decomposer is decomposer
