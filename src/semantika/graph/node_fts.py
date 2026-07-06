"""FTS5 management mixin for NodeService.

Provides full-text search, index maintenance, and corruption recovery
for the ``nodes_fts`` virtual table.
"""

from __future__ import annotations

import logging
import sqlite3

from semantika.graph.constants import FTS5_KEYWORDS

logger = logging.getLogger(__name__)


class NodeFtsMixin:
    """Mixin that provides FTS5 methods for NodeService.

    Requires ``self.db`` (SemantikaDB) to be available on the host class.
    """

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
                self._rebuild_fts()
                results = self.db.execute(fts_sql, (fts_query, limit))
            except sqlite3.DatabaseError:
                logger.error("FTS rebuild failed — using LIKE fallback")
                results = []

        if results:
            return results

        # Fallback: LIKE on label_text
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return self.db.execute(
            "SELECT *, 0 AS _rank FROM nodes WHERE label_text LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT ?",
            (f"%{escaped}%", limit),
        )

    # ── FTS lifecycle ───────────────────────────────────────────────────

    def _ensure_fts(self) -> None:
        """Ensure FTS5 virtual table exists and is populated."""
        self.db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
            "  node_id UNINDEXED,"
            "  label_text,"
            "  definition_text,"
            "  content=nodes,"
            "  content_rowid=rowid,"
            "  tokenize='unicode61'"
            ")"
        )
        count = self.db.execute_one("SELECT COUNT(*) AS cnt FROM nodes_fts")
        if count and count["cnt"] == 0:
            self._populate_fts()

    def _populate_fts(self) -> None:
        """Populate FTS from content table."""
        try:
            self.db.execute(
                "INSERT INTO nodes_fts (rowid, node_id, label_text, definition_text)"
                " SELECT rowid, node_id, label_text, definition_text FROM nodes"
            )
        except sqlite3.DatabaseError:
            logger.warning("FTS population failed — using LIKE fallback")

    def _index_fts(self, node_id: str) -> None:
        """Index a single node in FTS5."""
        entry = self.db.execute_one(
            "SELECT rowid, node_id, label_text, definition_text "
            "FROM nodes WHERE node_id = ?",
            (node_id,),
        )
        if not entry:
            return
        try:
            self.db.execute(
                "INSERT INTO nodes_fts (rowid, node_id, label_text, definition_text) "
                "VALUES (?, ?, ?, ?)",
                (entry["rowid"], node_id, entry["label_text"] or "", entry["definition_text"] or ""),
            )
        except sqlite3.DatabaseError as exc:
            logger.warning("FTS index insert failed for node %s: %s", node_id, exc)

    def _remove_from_fts(self, node_id: str) -> None:
        """Remove a node from FTS index."""
        row = self.db.execute_one(
            "SELECT rowid FROM nodes WHERE node_id = ?", (node_id,)
        )
        if not row or row.get("rowid") is None:
            return
        self._remove_fts_by_rowid(node_id, row["rowid"])

    def _remove_fts_by_rowid(self, node_id: str, rowid: int) -> None:
        """Remove a rowid from the FTS index after node deletion."""
        try:
            self.db.execute(
                "INSERT INTO nodes_fts(nodes_fts, rowid) VALUES('delete', ?)",
                (rowid,),
            )
        except sqlite3.DatabaseError as exc:
            logger.warning(
                "FTS 'delete' failed for %s (rowid=%s): %s",
                node_id, rowid, exc,
            )

    def optimize_fts(self) -> None:
        """Optimize the FTS5 index — merges b-tree segments.

        Should be called periodically (e.g. every ~50 node creates) to
        prevent search-performance degradation from accumulated incremental
        updates. Non-critical — failures are silently logged.
        """
        try:
            self.db.execute(
                "INSERT INTO nodes_fts(nodes_fts) VALUES('optimize')"
            )
        except sqlite3.DatabaseError as exc:
            logger.debug("FTS5 optimize failed (non-critical): %s", exc)

    def _rebuild_fts(self) -> None:
        """Rebuild the nodes FTS index from the content table.

        Handles corruption by dropping and recreating the FTS table
        if the FTS5 'rebuild' command fails.
        """
        try:
            self.db.execute(
                "INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')"
            )
        except sqlite3.DatabaseError:
            logger.warning("Nodes FTS rebuild failed — recreating table")
            for suffix in ("_data", "_idx", "_docsize", "_config", "_content"):
                try:
                    self.db.execute(f"DROP TABLE IF EXISTS nodes_fts{suffix}")
                except sqlite3.DatabaseError:
                    pass
            try:
                self.db.execute("DROP TABLE IF EXISTS nodes_fts")
            except sqlite3.DatabaseError:
                pass
            self._ensure_fts()
            self._populate_fts()
