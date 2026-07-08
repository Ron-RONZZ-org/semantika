"""FTS5 management mixin for NodeService.

Provides full-text search, index maintenance, and corruption recovery
for the ``nodes_fts`` virtual table.  Defers the actual FTS5 operations
to :class:`semantika.core.fts.FTS5Manager` to avoid code duplication with
:class:`semantika.graph.predicate_service.PredicateService`.
"""

from __future__ import annotations

import logging
import sqlite3

from semantika.core.fts import FTS5Manager
from semantika.graph.constants import FTS5_KEYWORDS
from semantika.graph.helpers import escape_like

logger = logging.getLogger(__name__)


class NodeFtsMixin:
    """Mixin that provides FTS5 methods for NodeService.

    Requires ``self.db`` (SemantikaDB) to be available on the host class.
    """

    @property
    def _fts_mgr(self) -> FTS5Manager:
        """Lazy-initialised shared FTS5 manager for nodes."""
        if not hasattr(self, "_fts_mgr_cache"):
            self._fts_mgr_cache = FTS5Manager(
                db=self.db,
                fts_table="nodes_fts",
                content_table="nodes",
                pk_column="node_id",
                fts_columns=["label_text", "definition_text"],
            )
        return self._fts_mgr_cache

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search on nodes via FTS5, falling back to LIKE."""
        if not query or not query.strip():
            return self.list(limit=limit)  # type: ignore[attr-defined]

        safe_tokens = []
        for word in query.strip().split():
            cleaned = "".join(c for c in word if c.isalnum() or c == "_")
            if not cleaned:
                continue
            if cleaned.upper() in FTS5_KEYWORDS:
                cleaned = cleaned.lower()
            safe_tokens.append(f"{cleaned}*")
        if not safe_tokens:
            return self.list(limit=limit)  # type: ignore[attr-defined]

        fts_query = " OR ".join(safe_tokens)
        # BM25 ranking with column weights:
        #   label_text (-5.0): most important — matches here ranked highest
        #   definition_text (-1.0): moderately important
        #   node_id (0.0): unindexed, zero weight
        fts_sql = """
            SELECT n.*, bm25(nodes_fts, 1.2, 0.75, 0.0, -5.0, -1.0) AS _rank
            FROM nodes n
            JOIN nodes_fts f ON n.node_id = f.node_id
            WHERE nodes_fts MATCH ?
            ORDER BY _rank
            LIMIT ?
        """
        try:
            results = self.db.execute(fts_sql, (fts_query, limit))
        except sqlite3.DatabaseError:
            logger.warning("FTS search failed — rebuilding and retrying")
            try:
                self._fts_mgr.rebuild()
                results = self.db.execute(fts_sql, (fts_query, limit))
            except sqlite3.DatabaseError:
                logger.error("FTS rebuild failed — using LIKE fallback")
                results = []

        if results:
            return results

        # Fallback: LIKE on label_text
        escaped = escape_like(query)
        return self.db.execute(
            "SELECT *, 0 AS _rank FROM nodes WHERE label_text LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT ?",
            (f"%{escaped}%", limit),
        )

    # ── FTS lifecycle (delegated to FTS5Manager) ─────────────────────────

    def _ensure_fts(self) -> None:
        """Ensure FTS5 virtual table exists and is populated."""
        self._fts_mgr.ensure()

    def _populate_fts(self) -> None:
        """Populate FTS from content table."""
        self._fts_mgr.populate()

    def _index_fts(self, node_id: str) -> None:
        """Index a single node in FTS5."""
        self._fts_mgr.index(node_id)

    def _remove_from_fts(self, node_id: str) -> None:
        """Remove a node from FTS index."""
        self._fts_mgr.remove(node_id)

    def _remove_fts_by_rowid(self, node_id: str, rowid: int) -> None:
        """Remove a rowid from the FTS index after node deletion."""
        self._fts_mgr.remove_by_rowid(node_id, rowid)

    def optimize_fts(self) -> None:
        """Optimize the FTS5 index — merges b-tree segments.

        Should be called periodically (e.g. every ~50 node creates) to
        prevent search-performance degradation from accumulated incremental
        updates. Non-critical — failures are silently logged.
        """
        self._fts_mgr.optimize()

    def _rebuild_fts(self) -> None:
        """Rebuild the nodes FTS index from the content table.

        Handles corruption by dropping and recreating the FTS table
        if the FTS5 'rebuild' command fails.
        """
        self._fts_mgr.rebuild()
