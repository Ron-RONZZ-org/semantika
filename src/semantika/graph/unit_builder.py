"""Compound unit node creation from AST + singleton creation.

Ported from A-semantika's ``_unit_builder.py`` with EO→EN migration.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

from semantika.graph.unit_parser import (
    SingularUnit,
    UnitExpression,
    UnitPower,
    UnitProduct,
    normalize,
)
from semantika.graph.unit_errors import UnitNotFoundError
from semantika.core.crud import now

if TYPE_CHECKING:
    from semantika.graph.node_service import NodeService
    from semantika.core import SemantikaDB


class UnitBuilder:
    """Creates compound unit nodes from parsed expressions."""

    def __init__(
        self,
        db: SemantikaDB,
        node_svc: NodeService,
        resolve_word_fn: Callable[[str], dict],
    ) -> None:
        self.db = db
        self.node_svc = node_svc
        self._resolve_word_to_node = resolve_word_fn

    def create_from_ast(self, expr: UnitExpression) -> str:
        """Walk an AST and create missing compound unit nodes.

        Returns the ``node_id`` of the root unit.
        """
        expr = normalize(expr)

        if isinstance(expr, SingularUnit):
            node = self._resolve_word_to_node(expr.name)
            return node["node_id"]

        if isinstance(expr, UnitPower):
            base_id = self.create_from_ast(expr.base)
            return self._build_power_node(base_id, expr.exponent)

        if isinstance(expr, UnitProduct):
            term_ids: list[str] = []
            for term in expr.terms:
                term_id = self.create_from_ast(term)
                term_ids.append(term_id)
            return self._build_product_node(term_ids)

        raise UnitNotFoundError(f"Unsupported expression type: {type(expr).__name__}")

    def _build_power_node(self, base_id: str, exponent: int) -> str:
        """Create or find a UnitPower node."""
        from semantika.graph.node_helpers import normalize_label_to_id

        now_iso = now()
        local_name = base_id.split(":")[-1]
        if exponent == 2:
            suffix = "_SQ"
        elif exponent == 3:
            suffix = "_CU"
        else:
            suffix = f"_POW{exponent}"
        node_id = f"unit:{local_name}{suffix}"

        existing = self.node_svc.resolve_node_id_prefix(node_id)
        if existing:
            return existing["node_id"]

        labels = json.dumps({"en": f"{base_id.split(':')[-1]}^{exponent}"})
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, labels, label_text, definitions, definition_text, created_at, updated_at) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (node_id, labels, now_iso, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, 'rdf:type', ':UnitPower', 'uri', ?)",
            (node_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, ':hasBase', ?, 'uri', ?)",
            (node_id, base_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, ':hasExponent', ?, 'literal', ?)",
            (node_id, str(exponent), now_iso),
        )
        return node_id

    def _build_product_node(self, term_ids: list[str]) -> str:
        """Create or find a UnitProduct node.

        Binary decomposition: repeated UnitProduct(term1, term2).
        """
        if len(term_ids) == 1:
            return term_ids[0]
        if len(term_ids) == 2:
            return self._build_binary_product(term_ids[0], term_ids[1])
        result = term_ids[-1]
        for tid in reversed(term_ids[:-1]):
            result = self._build_binary_product(tid, result)
        return result

    def _build_binary_product(self, term1_id: str, term2_id: str) -> str:
        """Create a binary UnitProduct node."""
        now_iso = now()
        terms_sorted = sorted([term1_id, term2_id])
        name1 = terms_sorted[0].split(":")[-1]
        name2 = terms_sorted[1].split(":")[-1]
        node_id = f"unit:{name1}_TIMES_{name2}"

        existing = self.node_svc.resolve_node_id_prefix(node_id)
        if existing:
            return existing["node_id"]

        labels = json.dumps({"en": f"{name1}·{name2}"})
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, labels, label_text, definitions, definition_text, created_at, updated_at) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (node_id, labels, now_iso, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, 'rdf:type', ':UnitProduct', 'uri', ?)",
            (node_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, ':hasTerm1', ?, 'uri', ?)",
            (node_id, term1_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, ':hasTerm2', ?, 'uri', ?)",
            (node_id, term2_id, now_iso),
        )
        return node_id

    def create_singleton(self, node_id: str, label: str, symbol: str) -> str:
        """Create a custom singular unit node."""
        if not node_id.startswith("unit:"):
            node_id = f"unit:{node_id}"

        now_iso = now()
        labels = json.dumps({"en": label})
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, labels, label_text, definitions, definition_text, created_at, updated_at) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (node_id, labels, now_iso, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, 'rdf:type', ':SingularUnit', 'uri', ?)",
            (node_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_id, predicate_id, object_value, object_type, created_at) "
            "VALUES (?, ':symbol', ?, 'literal', ?)",
            (node_id, symbol, now_iso),
        )
        return node_id
