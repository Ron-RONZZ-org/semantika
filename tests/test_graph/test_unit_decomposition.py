"""Tests for unit_decomposition.py — UnitDecomposer and format_unit_ref."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from semantika.core import SemantikaDB
from semantika.graph.db import SCHEMA
from semantika.graph.unit_decomposition import UnitDecomposer, format_unit_ref


@pytest.fixture
def db(tmp_path: Path) -> SemantikaDB:
    """Create an isolated test database with schema."""
    db_path = tmp_path / "test.db"
    db = SemantikaDB(db_path)

    for table, sql in SCHEMA.items():
        db.init_schema({table: sql})
    db.execute("PRAGMA foreign_keys=ON")
    return db


@pytest.fixture
def seeded_db(db: SemantikaDB) -> SemantikaDB:
    """Seed unit-related test data into the database."""
    ts = "2026-07-04T12:00:00"

    # Create unit predicates
    for pid in ("rdf:type", ":symbol", ":hasBase", ":hasExponent",
                ":hasTerm1", ":hasTerm2", ":multiplier"):
        db.execute(
            "INSERT OR IGNORE INTO predicates "
            "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
            "VALUES (?, 'manual', '{}', '{}', '[]', ?, ?)",
            (pid, ts, ts),
        )

    # Create base unit nodes
    base_units = [
        ("unit:METER", "m"),
        ("unit:KELVIN", "K"),
        ("unit:KILOGRAM", "kg"),
        ("unit:SECOND", "s"),
        ("unit:JOULE", "J"),
    ]
    for nid, sym in base_units:
        labels = json.dumps({"en": nid.split(":")[1].title()})
        label_text = nid.split(":")[1].title()
        db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, labels, label_text, definitions, definition_text, created_at, updated_at) "
            "VALUES (?, ?, ?, '{}', '', ?, ?)",
            (nid, labels, label_text, ts, ts),
        )
        # Add symbol triple
        db.execute(
            "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, ':symbol', ?, 'literal', ?)",
            (nid, sym, ts),
        )

    # Create compound: JOULE = METER^2 * KILOGRAM * SECOND^-2
    # UnitPower: hasBase=METER, hasExponent=2
    power_m2_id = "unit:_M2"
    db.execute(
        "INSERT INTO nodes (node_id, labels, label_text, created_at, updated_at) "
        "VALUES (?, '{}', '', ?, ?)",
        (power_m2_id, ts, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES (?, ':hasBase', 'unit:METER', 'node', ?)",
        (power_m2_id, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES (?, ':hasExponent', '2', 'literal', ?)",
        (power_m2_id, ts),
    )

    # UnitPower: hasBase=KILOGRAM, hasExponent=1
    power_kg_id = "unit:_KG1"
    db.execute(
        "INSERT INTO nodes (node_id, labels, label_text, created_at, updated_at) "
        "VALUES (?, '{}', '', ?, ?)",
        (power_kg_id, ts, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES (?, ':hasBase', 'unit:KILOGRAM', 'node', ?)",
        (power_kg_id, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES (?, ':hasExponent', '1', 'literal', ?)",
        (power_kg_id, ts),
    )

    # UnitProduct: hasTerm1=M2, hasTerm2=KG1
    product_id = "unit:_M2_KG"
    db.execute(
        "INSERT INTO nodes (node_id, labels, label_text, created_at, updated_at) "
        "VALUES (?, '{}', '', ?, ?)",
        (product_id, ts, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES (?, ':hasTerm1', ?, 'node', ?)",
        (product_id, power_m2_id, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES (?, ':hasTerm2', ?, 'node', ?)",
        (product_id, power_kg_id, ts),
    )

    # UnitPower: hasBase=SECOND, hasExponent=-2
    power_s2_id = "unit:_S-2"
    db.execute(
        "INSERT INTO nodes (node_id, labels, label_text, created_at, updated_at) "
        "VALUES (?, '{}', '', ?, ?)",
        (power_s2_id, ts, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES (?, ':hasBase', 'unit:SECOND', 'node', ?)",
        (power_s2_id, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES (?, ':hasExponent', '-2', 'literal', ?)",
        (power_s2_id, ts),
    )

    # JOULE = product / SECOND^2
    # UnitProduct for numerator: M2 + KG
    db.execute(
        "INSERT INTO nodes (node_id, labels, label_text, created_at, updated_at) "
        "VALUES ('unit:JOULE_impl', '{}', '', ?, ?)",
        (ts, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES ('unit:JOULE_impl', ':hasBase', ?, 'node', ?)",
        (product_id, ts),
    )
    db.execute(
        "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
        "VALUES ('unit:JOULE_impl', ':hasExponent', '1', 'literal', ?)",
        (ts,),
    )

    return db


class TestFormatUnitRef:
    def test_unit_with_symbol(self, seeded_db: SemantikaDB):
        result = format_unit_ref(seeded_db, "unit:METER")
        assert result == "m"

    def test_unit_with_long_id(self, seeded_db: SemantikaDB):
        """unit:SHORT should return just 'SHORT'."""
        ts = "2026-07-04T12:00:00"
        seeded_db.execute(
            "INSERT INTO nodes (node_id, labels, label_text, created_at, updated_at) "
            "VALUES ('unit:SHORT', '{}', '', ?, ?)",
            (ts, ts),
        )
        result = format_unit_ref(seeded_db, "unit:SHORT")
        assert result == "SHORT"

    def test_unit_without_prefix(self, seeded_db: SemantikaDB):
        """A node_id without ':' returns truncated ID."""
        ts = "2026-07-04T12:00:00"
        seeded_db.execute(
            "INSERT INTO nodes (node_id, labels, label_text, created_at, updated_at) "
            "VALUES ('NOCOLON', '{}', '', ?, ?)",
            (ts, ts),
        )
        result = format_unit_ref(seeded_db, "NOCOLON")
        assert result == "NOCOLON"


class TestUnitDecomposer:
    def test_power_unit(self, seeded_db: SemantikaDB):
        decomposer = UnitDecomposer(seeded_db)
        result = decomposer.get_decomposition("unit:_M2")
        assert "METER" in result or "m" in result or "M" in result
        assert "^2" in result

    def test_product_unit(self, seeded_db: SemantikaDB):
        decomposer = UnitDecomposer(seeded_db)
        result = decomposer.get_decomposition("unit:_M2_KG")
        assert result  # Non-empty string

    def test_nonexistent_unit(self, seeded_db: SemantikaDB):
        decomposer = UnitDecomposer(seeded_db)
        result = decomposer.get_decomposition("unit:NONEXISTENT")
        assert result == ""

    def test_compound_with_negative_exponent(self, seeded_db: SemantikaDB):
        decomposer = UnitDecomposer(seeded_db)
        result = decomposer.get_decomposition("unit:_S-2")
        assert result  # Non-empty
        assert "SECOND" in result or "s" in result or "S" in result

    def _ensure_base_nodes(self, db: SemantikaDB, ts: str) -> None:
        """Create base node unit:METER if it doesn't exist."""
        db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, labels, label_text, created_at, updated_at) "
            "VALUES ('unit:METER', '{}', 'Meter', ?, ?)",
            (ts, ts),
        )

    def test_missing_term2(self, db: SemantikaDB):
        """Partial product with only term1 should return empty."""
        ts = "2026-07-04T12:00:00"
        self._ensure_base_nodes(db, ts)
        # Ensure predicates exist
        for pid in (":hasTerm1", ":hasTerm2", ":hasBase", ":hasExponent"):
            db.execute(
                "INSERT OR IGNORE INTO predicates "
                "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
                "VALUES (?, 'manual', '{}', '{}', '[]', ?, ?)",
                (pid, ts, ts),
            )
        # Create a node with only :hasTerm1 (no :hasTerm2)
        db.execute(
            "INSERT INTO nodes (node_id, labels, created_at, updated_at) "
            "VALUES ('unit:PARTIAL', '{}', ?, ?)",
            (ts, ts),
        )
        db.execute(
            "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES ('unit:PARTIAL', ':hasTerm1', 'unit:METER', 'node', ?)",
            (ts,),
        )
        decomposer = UnitDecomposer(db)
        result = decomposer.get_decomposition("unit:PARTIAL")
        assert result == ""

    def test_missing_exponent_for_base(self, db: SemantikaDB):
        """A node with :hasBase but no :hasExponent should not be treated as power."""
        ts = "2026-07-04T12:00:00"
        self._ensure_base_nodes(db, ts)
        # Ensure predicates exist
        for pid in (":hasBase", ":hasExponent"):
            db.execute(
                "INSERT OR IGNORE INTO predicates "
                "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
                "VALUES (?, 'manual', '{}', '{}', '[]', ?, ?)",
                (pid, ts, ts),
            )
        db.execute(
            "INSERT INTO nodes (node_id, labels, created_at, updated_at) "
            "VALUES ('unit:BASEONLY', '{}', ?, ?)",
            (ts, ts),
        )
        db.execute(
            "INSERT INTO triples (subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES ('unit:BASEONLY', ':hasBase', 'unit:METER', 'node', ?)",
            (ts,),
        )
        decomposer = UnitDecomposer(db)
        result = decomposer.get_decomposition("unit:BASEONLY")
        assert result == ""  # No exponent → not a valid power
