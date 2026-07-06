"""UnitService — facade for unit ontology operations.

Provides unit node creation, expression-based auto-creation,
decomposition, and the core ``resolve_unit()`` chain.

Ported from A-semantika's ``_unit_service.py`` with EO→EN migration.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING

from semantika.graph.unit_builder import UnitBuilder

logger = logging.getLogger(__name__)
from semantika.core.crud import now
from semantika.core.exceptions import AmbiguousIDError
from semantika.graph.node_helpers import extract_label_text
from semantika.graph.unit_decomposition import UnitDecomposer
from semantika.graph.unit_errors import UnitNotFoundError
from semantika.graph.unit_parser import parse
from semantika.graph.unit_seed_data import ALL_UNITS, BASE_AND_DERIVED

if TYPE_CHECKING:
    from semantika.core import SemantikaDB
    from semantika.graph.node_service import NodeService
    from semantika.graph.triple_service import TripleService


class UnitService:
    """Facade for unit ontology operations."""

    def __init__(
        self,
        db: SemantikaDB,
        node_svc: NodeService,
        triple_svc: TripleService,
    ) -> None:
        self.db = db
        self.node_svc = node_svc
        self.triple_svc = triple_svc
        self._base_units_ensured: bool = False
        self._builder: UnitBuilder | None = None
        self._decomposer: UnitDecomposer | None = None

    @property
    def builder(self) -> UnitBuilder:
        if self._builder is None:
            self._builder = UnitBuilder(self.db, self.node_svc, self._resolve_word_to_node)
        return self._builder

    @property
    def decomposer(self) -> UnitDecomposer:
        if self._decomposer is None:
            self._decomposer = UnitDecomposer(self.db)
        return self._decomposer

    # ── Lazy seeding ─────────────────────────────────────────────────

    def _ensure_base_units(self) -> None:
        """Seed SI base units, derived units, and prefixes on first use."""
        if self._base_units_ensured:
            return

        now_iso = now()
        from semantika.graph.unit_seed_data import UNIT_TYPE_NODES

        # Ensure unit-specific predicates exist
        unit_predicates = [
            "rdf:type", ":symbol", ":ucumCode", ":multiplier", ":offset",
            ":hasBase", ":hasExponent", ":hasTerm1", ":hasTerm2",
        ]
        for pid in unit_predicates:
            self.db.execute(
                "INSERT OR IGNORE INTO predicates "
                "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
                "VALUES (?, 'manual', ?, '{}', '[]', ?, ?)",
                (pid, '{}', now_iso, now_iso),
            )

        # Use a transaction with deferred FKs so that generated-column
        # FK checks (object_node_id) don't fail mid-seeding.
        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            # 1. Create unit TYPE nodes first (referenced by triples)
            for type_node in UNIT_TYPE_NODES:
                labels = json.dumps(type_node["labels"])
                label_text = extract_label_text(type_node["labels"])
                conn.execute(
                    "INSERT OR IGNORE INTO nodes "
                    "(node_id, labels, label_text, definitions, definition_text, created_at, updated_at) "
                    "VALUES (?, ?, ?, '{}', '', ?, ?)",
                    (type_node["node_id"], labels, label_text, now_iso, now_iso),
                )

            # 2. Now insert all rdf:type triples for type nodes
            for type_node in UNIT_TYPE_NODES:
                try:
                    conn.execute(
                        "INSERT INTO triples "
                        "(subject_id, predicate_id, object_value, object_type, created_at) "
                        "VALUES (?, 'rdf:type', ':UnitType', 'uri', ?)",
                        (type_node["node_id"], now_iso),
                    )
                except sqlite3.IntegrityError:
                    pass  # Already exists

            # 3. Create unit nodes (base + derived + prefixes)
            for unit in BASE_AND_DERIVED:
                self._insert_unit_node_in_txn(conn, unit, now_iso)
            for prefix_data in ALL_UNITS[len(BASE_AND_DERIVED):]:
                self._insert_unit_node_in_txn(conn, prefix_data, now_iso)

        self._base_units_ensured = True

    def _insert_unit_node_in_txn(self, conn, unit: dict, now_iso: str) -> None:
        """Insert a unit node and its triples within an existing transaction."""
        import sqlite3
        labels = json.dumps(unit["labels"])
        label_text = extract_label_text(unit["labels"])
        try:
            conn.execute(
                "INSERT INTO nodes "
                "(node_id, labels, label_text, definitions, definition_text, created_at, updated_at) "
                "VALUES (?, ?, ?, '{}', '', ?, ?)",
                (unit["node_id"], labels, label_text, now_iso, now_iso),
            )
        except sqlite3.IntegrityError:
            pass  # Already exists

        try:
            conn.execute(
                "INSERT INTO triples "
                "(subject_id, predicate_id, object_value, object_type, created_at) "
                "VALUES (?, 'rdf:type', ':SingularUnit', 'uri', ?)",
                (unit["node_id"], now_iso),
            )
        except sqlite3.IntegrityError:
            pass

        symbol = unit.get("symbol")
        if symbol:
            try:
                conn.execute(
                    "INSERT INTO triples "
                    "(subject_id, predicate_id, object_value, object_type, created_at) "
                    "VALUES (?, ':symbol', ?, 'literal', ?)",
                    (unit["node_id"], symbol, now_iso),
                )
            except sqlite3.IntegrityError:
                pass
        ucum = unit.get("ucum")
        if ucum:
            try:
                conn.execute(
                    "INSERT INTO triples "
                    "(subject_id, predicate_id, object_value, object_type, created_at) "
                    "VALUES (?, ':ucumCode', ?, 'literal', ?)",
                    (unit["node_id"], ucum, now_iso),
                )
            except sqlite3.IntegrityError:
                pass
        mult = unit.get("multiplier")
        if mult is not None:
            try:
                conn.execute(
                    "INSERT INTO triples "
                    "(subject_id, predicate_id, object_value, object_type, created_at) "
                    "VALUES (?, ':multiplier', ?, 'literal', ?)",
                    (unit["node_id"], str(mult), now_iso),
                )
            except sqlite3.IntegrityError:
                pass
        offset = unit.get("offset")
        if offset is not None:
            try:
                conn.execute(
                    "INSERT INTO triples "
                    "(subject_id, predicate_id, object_value, object_type, created_at) "
                    "VALUES (?, ':offset', ?, 'literal', ?)",
                    (unit["node_id"], str(offset), now_iso),
                )
            except sqlite3.IntegrityError:
                pass

    # ── Symbol / name resolution ─────────────────────────────────────

    def _find_unit_by_symbol(self, name: str) -> dict | None:
        """Find a unit node whose ``:symbol`` triple matches *name*."""
        row = self.db.execute_one(
            "SELECT n.* FROM nodes n "
            "JOIN triples t ON t.subject_id = n.node_id "
            "WHERE t.predicate_id = ':symbol' AND t.object_value = ? "
            "AND t.object_type = 'literal'",
            (name,),
        )
        if row:
            return row
        rows = self.db.execute(
            "SELECT n.* FROM nodes n "
            "JOIN triples t ON t.subject_id = n.node_id "
            "WHERE t.predicate_id = ':symbol' AND t.object_value LIKE ? "
            "AND t.object_type = 'literal'",
            (name,),
        )
        if len(rows) == 1:
            return rows[0]
        return None

    def _resolve_word_to_node(self, word: str) -> dict:
        """Resolve a WORD token from the expression parser to a unit node."""
        try:
            node = self.node_svc.resolve_node_id_prefix(word)
            if node:
                return node
        except AmbiguousIDError:
            logger.debug("Ambiguous node ID prefix resolution for '%s', falling through", word)

        node = self._find_unit_by_symbol(word)
        if node:
            return node

        results = self.node_svc.search(word, limit=2)
        if len(results) == 1:
            return results[0]

        raise UnitNotFoundError(f"Unit not found: {word!r}.")

    # ── Public API ────────────────────────────────────────────────────

    def resolve_unit(self, expr: str) -> str:
        """Resolve a unit expression to a ``node_id``.

        Resolution chain:
          1. Try as an existing ``node_id`` prefix
          2. Parse as unit expression and auto-create compound nodes
        """
        self._ensure_base_units()

        node = self.db.execute_one(
            "SELECT * FROM nodes WHERE node_id = ? COLLATE NOCASE", (expr,)
        )
        if node:
            return node["node_id"]

        node = self.node_svc.resolve_node_id_prefix(expr)
        if node:
            return node["node_id"]

        node = self._find_unit_by_symbol(expr)
        if node:
            return node["node_id"]

        try:
            ast = parse(expr)
            return self.builder.create_from_ast(ast)
        except (ValueError, UnitNotFoundError):
            raise
        except Exception as exc:
            raise UnitNotFoundError(f"Cannot resolve unit expression {expr!r}: {exc}") from exc

    def normalize_unit(self, node_id_or_symbol: str) -> str:
        """Return the canonical ``node_id`` for a unit without auto-creating."""
        self._ensure_base_units()

        node = self.db.execute_one(
            "SELECT * FROM nodes WHERE node_id = ? COLLATE NOCASE", (node_id_or_symbol,)
        )
        if node:
            return node["node_id"]

        node = self.node_svc.resolve_node_id_prefix(node_id_or_symbol)
        if node:
            return node["node_id"]

        node = self._find_unit_by_symbol(node_id_or_symbol)
        if node:
            return node["node_id"]

        results = self.node_svc.search(node_id_or_symbol, limit=2)
        if len(results) == 1:
            return results[0]["node_id"]

        return node_id_or_symbol

    def create_singleton(self, node_id: str, label: str, symbol: str) -> str:
        """Create a custom singular unit node."""
        self._ensure_base_units()
        return self.builder.create_singleton(node_id, label, symbol)

    def list_units(self) -> list[dict]:
        """List all unit nodes (SingularUnit, PrefixedUnit, CompoundUnit, etc.)."""
        self._ensure_base_units()
        rows = self.db.execute(
            """SELECT DISTINCT n.* FROM nodes n
               JOIN triples t ON t.subject_id = n.node_id
               WHERE t.predicate_id = 'rdf:type'
                 AND t.object_value IN (
                     ':SingularUnit', ':PrefixedUnit', ':CompoundUnit',
                     ':UnitProduct', ':UnitPower'
                 )
               ORDER BY n.node_id"""
        )
        result = []
        for row in rows:
            type_row = self.db.execute_one(
                "SELECT object_value FROM triples "
                "WHERE subject_id = ? AND predicate_id = 'rdf:type' "
                "AND object_type = 'uri' ORDER BY object_value LIMIT 1",
                (row["node_id"],),
            )
            sym_row = self.db.execute_one(
                "SELECT object_value FROM triples "
                "WHERE subject_id = ? AND predicate_id = ':symbol' "
                "AND object_type = 'literal'",
                (row["node_id"],),
            )
            row["unit_type"] = type_row["object_value"] if type_row else ""
            row["unit_symbol"] = sym_row["object_value"] if sym_row else ""
            result.append(row)
        return result

    def get_unit_info(self, node_id: str) -> dict | None:
        """Get detailed info for a unit node."""
        self._ensure_base_units()
        node = self.node_svc.resolve_node_id_prefix(node_id)
        if not node:
            return None

        type_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = 'rdf:type' "
            "AND object_type = 'uri' ORDER BY object_value LIMIT 1",
            (node["node_id"],),
        )
        sym_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':symbol' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        ucum_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':ucumCode' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        mult_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':multiplier' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )

        result = dict(node)
        result["unit_type"] = type_row["object_value"] if type_row else ""
        result["unit_symbol"] = sym_row["object_value"] if sym_row else ""
        result["ucum"] = ucum_row["object_value"] if ucum_row else ""
        result["multiplier"] = float(mult_row["object_value"]) if mult_row else None
        result["decomposition"] = self.decomposer.get_decomposition(node_id)
        return result
