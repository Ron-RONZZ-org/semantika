"""BuiltinTypeService — lazy seeding of built-in predicates and type nodes.

Follows the same lazy-seeding pattern as :class:`UnitService._ensure_base_units`.
Predicates and type nodes are auto-created on first access so they are
always available without a separate seed step.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from semantika.core.crud import now
from semantika.graph.builtin_seed_data import BUILTIN_PREDICATES, BUILTIN_TYPE_NODES, REQUIRED_PREDICATES
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

    def ensure_builtins(self) -> None:
        """Seed built-in predicates and type nodes on first call.

        Idempotent — safe to call multiple times.
        """
        if self._builtins_ensured:
            return

        now_iso = now()

        # 1. Ensure built-in predicates exist
        for pid, source, labels, descriptions in BUILTIN_PREDICATES:
            self.db.execute(
                "INSERT OR IGNORE INTO predicates "
                "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, '[]', ?, ?)",
                (pid, source, json.dumps(labels), json.dumps(descriptions), now_iso, now_iso),
            )

        # 2a. Ensure rdf:type predicate exists (needed for triple FK)
        self.db.execute(
            "INSERT OR IGNORE INTO predicates "
            "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
            "VALUES ('rdf:type', 'rdf', ?, ?, '[]', ?, ?)",
            (json.dumps({"en": "type"}), json.dumps({"en": "Is a type of"}), now_iso, now_iso),
        )

        # 2b. Ensure file metadata predicates (reused from seed_defaults)
        file_predicates = [
            (":hasFilePath", {"en": "file path"}, {"en": "Path to attached file"}),
            (":hasFileMime", {"en": "MIME type"}, {"en": "MIME type of attached file"}),
            (":hasFileSize", {"en": "file size"}, {"en": "File size in bytes"}),
            (":hasFileSource", {"en": "file source"}, {"en": "Original source path/URL"}),
        ]
        for pid, lbls, descs in file_predicates:
            self.db.execute(
                "INSERT OR IGNORE INTO predicates "
                "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
                "VALUES (?, 'manual', ?, ?, '[]', ?, ?)",
                (pid, json.dumps(lbls), json.dumps(descs), now_iso, now_iso),
            )

        # 3. Create type nodes + rdf:type in a transaction
        # Note: explicit BEGIN is needed because the transaction context
        # manager does not auto-begin, and PRAGMA defer_foreign_keys only
        # takes effect within an explicit transaction.
        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")
            conn.execute("BEGIN")

            for type_node in BUILTIN_TYPE_NODES:
                labels = json.dumps(type_node["labels"])
                label_text = extract_label_text(type_node["labels"])
                definitions = json.dumps(type_node.get("definitions", {}))
                def_text = extract_label_text(type_node.get("definitions", {}))
                conn.execute(
                    "INSERT OR IGNORE INTO nodes "
                    "(node_id, labels, label_text, definitions, definition_text, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (type_node["node_id"], labels, label_text, definitions, def_text, now_iso, now_iso),
                )

                # Auto-assign rdf:type = PHOTO etc. referencing itself as a type concept
                # Each builtin type node is an instance of itself (self-typing convention).
                conn.execute(
                    "INSERT OR IGNORE INTO triples "
                    "(subject_id, predicate_id, object_value, object_type, created_at) "
                    "VALUES (?, 'rdf:type', ?, 'uri', ?)",
                    (type_node["node_id"], type_node["node_id"], now_iso),
                )

        self._builtins_ensured = True

    def ensure_predicates(self, predicate_ids: list[str]) -> None:
        """Ensure specific predicates exist, creating them if missing.

        Args:
            predicate_ids: List of predicate IDs to ensure (e.g.
                ``["sm:depicts", "rdf:type"]``).
        """
        self.ensure_builtins()
        for pid in predicate_ids:
            existing = self.db.execute_one(
                "SELECT predicate_id FROM predicates WHERE predicate_id = ?", (pid,)
            )
            if existing is None:
                # Create a minimal entry — the caller is responsible for labels
                self.db.execute(
                    "INSERT OR IGNORE INTO predicates "
                    "(predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
                    "VALUES (?, 'manual', '{}', '{}', '[]', ?, ?)",
                    (pid, now(), now()),
                )

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
