"""BuiltinTypeService — lazy seeding of built-in predicates and type nodes.

Unified single entry point for all seeding (replaces the old
``_seed_default_predicates()`` path in ``db.py`` and the old
Python-dict-based seed data files).

Seed data is loaded from YAML files (``builtins.yaml``, ``units.yaml``)
with a Python fallback for required predicates (see
:mod:`semantika.graph.builtin_loader` and
:mod:`semantika.graph._required_predicates`).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from semantika.core.crud import now
from semantika.graph.builtin_loader import (
    get_predicate_catalog,
    get_type_nodes_from_yaml,
    get_core_predicate_ids,
)
from semantika.graph.db import compute_iri, _iri_is_non_template
from semantika.graph.node_helpers import extract_label_text

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from semantika.core import SemantikaDB
    from semantika.graph.node_service import NodeService
    from semantika.graph.predicate_service import PredicateService
    from semantika.graph.triple_service import TripleService


class BuiltinTypeService:
    """Manages lazy seeding of built-in type nodes and predicates.

    Call :meth:`ensure_builtins` before any operation that depends on
    built-in types or predicates.

    Use :meth:`reload` to re-read the YAML files and re-seed without
    restarting the server.
    """

    def __init__(
        self,
        db: SemantikaDB,
        node_svc: NodeService,
        triple_svc: TripleService,
        pred_svc: PredicateService,
    ) -> None:
        self.db = db
        self.node_svc = node_svc
        self.triple_svc = triple_svc
        self.pred_svc = pred_svc
        self._builtins_ensured: bool = False

    # ── Lazy seeding ─────────────────────────────────────────────────

    def _seed_predicates(self) -> None:
        """Seed all predicates from the YAML catalog (with Python fallback).

        Idempotent — uses ``INSERT OR IGNORE`` so existing data is never
        overwritten.
        """
        now_iso = now()
        catalog = get_predicate_catalog()
        for pid, entry in catalog.items():
            iri = compute_iri(pid) if _iri_is_non_template(pid) else ""
            self.db.execute(
                "INSERT OR IGNORE INTO predicates "
                "(predicate_id, iri, source, labels, descriptions, aliases, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, '[]', ?, ?)",
                (
                    pid,
                    iri,
                    entry.get("source", "manual"),
                    json.dumps(entry.get("labels", {})),
                    json.dumps(entry.get("descriptions", {})),
                    now_iso,
                    now_iso,
                ),
            )

    def _seed_type_nodes(self) -> None:
        """Seed built-in type nodes + ``rdf:type`` triples from YAML.

        Idempotent — uses ``INSERT OR IGNORE``.
        """
        now_iso = now()
        type_nodes = get_type_nodes_from_yaml()

        if not type_nodes:
            logger.warning("No type nodes found in builtins.yaml — skipping type node seeding")
            return

        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            for type_node in type_nodes:
                node_id = type_node.get("id", "")
                if not node_id:
                    continue
                labels = json.dumps(type_node.get("labels", {}))
                label_text = extract_label_text(type_node.get("labels", {}))
                definitions = json.dumps(type_node.get("definitions", {}))
                def_text = extract_label_text(type_node.get("definitions", {}))
                conn.execute(
                    "INSERT OR IGNORE INTO nodes "
                    "(node_id, labels, label_text, definitions, definition_text, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (node_id, labels, label_text, definitions, def_text, now_iso, now_iso),
                )

                # Auto-assign rdf:type = self-reference (a type is a type of itself)
                conn.execute(
                    "INSERT OR IGNORE INTO triples "
                    "(subject_id, predicate_id, object_value, object_type, created_at) "
                    "VALUES (?, 'rdf:type', ?, 'node', ?)",
                    (node_id, node_id, now_iso),
                )

    def ensure_builtins(self) -> None:
        """Seed all built-in predicates and type nodes on first call.

        Seeds from YAML (with Python fallback for required predicates).

        Idempotent — safe to call multiple times.
        Uses ``INSERT OR IGNORE`` so existing data is never overwritten.
        """
        if self._builtins_ensured:
            return

        self._seed_predicates()
        self._seed_type_nodes()
        self._builtins_ensured = True
        logger.debug("Built-in predicates and type nodes seeded")

    def reload(self) -> dict[str, int]:
        """Re-read YAML files and re-seed (without clearing existing data).

        Uses ``INSERT OR IGNORE`` so:
        - New entries added to YAML are seeded
        - Existing entries are never overwritten
        - User data is never touched

        Call :meth:`reload` after editing ``builtins.yaml`` or ``units.yaml``
        to pick up changes without restarting the server.

        Returns:
            Dict with ``predicates`` and ``type_nodes`` counts from the
            YAML files (for status reporting).
        """
        self._builtins_ensured = False
        self.ensure_builtins()

        catalog = get_predicate_catalog()
        type_nodes = get_type_nodes_from_yaml()
        return {
            "predicates": len(catalog),
            "type_nodes": len(type_nodes),
        }

    # ── Predicate existence helpers ──────────────────────────────────

    def ensure_predicates(self, predicate_ids: list[str]) -> None:
        """Ensure specific predicates exist, creating them if missing.

        Checks YAML catalog first, then Python fallback.  If a predicate
        is not in either, creates a minimal entry with ``source=manual``.

        Args:
            predicate_ids: List of predicate IDs to ensure (e.g.
                ``["sm:depicts", "rdf:type"]``).
        """
        self.ensure_builtins()
        catalog = get_predicate_catalog()

        for pid in predicate_ids:
            existing = self.db.execute_one(
                "SELECT predicate_id FROM predicates WHERE predicate_id = ?", (pid,)
            )
            if existing is not None:
                continue

            # Try YAML catalog first
            entry = catalog.get(pid)
            if entry is not None:
                iri = compute_iri(pid) if _iri_is_non_template(pid) else ""
                self.db.execute(
                    "INSERT OR IGNORE INTO predicates "
                    "(predicate_id, iri, source, labels, descriptions, aliases, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, '[]', ?, ?)",
                    (
                        pid,
                        iri,
                        entry.get("source", "manual"),
                        json.dumps(entry.get("labels", {})),
                        json.dumps(entry.get("descriptions", {})),
                        now(),
                        now(),
                    ),
                )
                continue

            # Fallback: minimal entry (shouldn't normally happen)
            logger.info(
                "Creating minimal entry for predicate '%s' (not found in YAML catalog)",
                pid,
            )
            self.db.execute(
                "INSERT OR IGNORE INTO predicates "
                "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
                "VALUES (?, 'manual', '{}', '{}', '[]', ?, ?)",
                (pid, now(), now()),
            )

    # ── Type node lookup ─────────────────────────────────────────────

    def get_type_node_id(self, media_type: str) -> str | None:
        """Return the node ID for a built-in type, or None if unknown.

        Args:
            media_type: One of ``"photo"``, ``"video"``, ``"file"``, ``"code"``.

        Returns:
            The node ID (e.g. ``"PHOTO"``) or ``None``.
        """
        mapping = {
            "photo": "PHOTO",
            "video": "VIDEO",
            "file": "DOCUMENT",
            "code": "SOURCE_CODE",
        }
        return mapping.get(media_type)


# ── Module-level convenience re-export ─────────────────────────────────

# Re-exported so predicate_service.py can import from either location.
from semantika.graph.builtin_loader import get_core_predicate_ids as get_core_predicate_ids  # noqa: F811
