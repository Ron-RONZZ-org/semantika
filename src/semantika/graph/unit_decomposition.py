"""Unit decomposition helpers — human-readable display strings.

Ported from A-semantika's ``_unit_decomposition.py`` with EO→EN migration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from semantika.core import SemantikaDB


def format_unit_ref(db: SemantikaDB, node_id: str) -> str:
    """Format a unit node reference for display.

    Uses symbol if available, otherwise the short node_id.
    """
    sym = db.execute_one(
        "SELECT object_value FROM triples "
        "WHERE subject_id = ? AND predicate_id = ':symbol' AND object_type = 'literal'",
        (node_id,),
    )
    if sym:
        return sym["object_value"]
    return node_id.split(":")[-1] if ":" in node_id else node_id[:16]


class UnitDecomposer:
    """Builds human-readable decomposition strings for compound units."""

    def __init__(self, db: SemantikaDB) -> None:
        self.db = db

    def get_decomposition(self, node_id: str) -> str:
        """Build a human-readable decomposition string for a unit.

        Walks the compound unit structure to produce something like
        ``"J / (K * kg)"``.
        """
        # Check for UnitPower
        base = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasBase' AND object_type = 'node'",
            (node_id,),
        )
        exp = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasExponent' AND object_type = 'literal'",
            (node_id,),
        )
        if base and exp:
            base_label = format_unit_ref(self.db, base["object_value"])
            return f"{base_label}^{exp['object_value']}"

        # Check for UnitProduct
        t1 = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasTerm1' AND object_type = 'node'",
            (node_id,),
        )
        t2 = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_id = ? AND predicate_id = ':hasTerm2' AND object_type = 'node'",
            (node_id,),
        )
        if t1 and t2:
            return self._decompose_product(t1["object_value"], t2["object_value"])

        return ""

    def _decompose_product(self, term1_id: str, term2_id: str) -> str:
        """Decompose a binary product, detecting negative exponents."""
        num_parts: list[str] = []
        den_parts: list[str] = []

        for tid in (term1_id, term2_id):
            t_exp = self.db.execute_one(
                "SELECT object_value FROM triples "
                "WHERE subject_id = ? AND predicate_id = ':hasExponent' AND object_type = 'literal'",
                (tid,),
            )
            if t_exp and t_exp["object_value"].startswith("-"):
                pos_exp = t_exp["object_value"][1:]
                base = self.db.execute_one(
                    "SELECT object_value FROM triples "
                    "WHERE subject_id = ? AND predicate_id = ':hasBase' AND object_type = 'node'",
                    (tid,),
                )
                if base:
                    label = format_unit_ref(self.db, base["object_value"])
                    den_parts.append(f"{label}^{pos_exp}" if pos_exp != "1" else label)
                else:
                    den_parts.append(format_unit_ref(self.db, tid))
            else:
                label = format_unit_ref(self.db, tid)
                num_parts.append(label)

        num_str = " · ".join(num_parts) if num_parts else "1"
        den_str = " · ".join(den_parts)
        if not den_parts:
            return num_str
        if len(den_parts) > 1:
            den_str = f"({den_str})"
        return f"{num_str} / {den_str}"
