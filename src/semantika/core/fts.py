"""FTS5 search configuration and shared index manager.

Vendored from A-core's ``A.data.search.FTSConfig``.

The :class:`FTS5Manager` eliminates the duplicated FTS5 lifecycle code that
was previously inlined in both :class:`semantika.graph.node_fts.NodeFtsMixin`
and :class:`semantika.graph.predicate_service.PredicateService`.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from semantika.core import SemantikaDB

logger = logging.getLogger(__name__)


@dataclass
class FTSConfig:
    """Configuration for an FTS5 virtual table.

    Attributes:
        table: Content table name.
        fts_columns: Column names in the FTS index.
        fts_table: FTS virtual table name (default: ``{table}_fts``).
        tokenize: Tokenizer for FTS5 (default: ``unicode61``).
        normalize: Optional per-column normalizer callables.
    """

    table: str
    fts_columns: list[str]
    fts_table: str = ""
    tokenize: str = "unicode61"
    normalize: dict[str, Callable[[str], str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fts_table:
            self.fts_table = f"{self.table}_fts"


class FTS5Manager:
    """Manages FTS5 virtual table lifecycle and single-row operations.

    Provides a shared implementation of the ``_ensure_fts``, ``_populate_fts``,
    ``_index_fts``, ``_remove_from_fts``, ``_rebuild_fts``, and ``optimize_fts``
    pattern that was previously duplicated across :class:`NodeFtsMixin` and
    :class:`PredicateService`.

    Connection-aware: all methods accept an optional *conn* parameter.  When
    *conn* is provided, the operation runs on that connection (inside a
    caller-managed transaction).  When *conn* is ``None``, the operation uses
    ``self.db.execute()`` (its own connection).

    Args:
        db: Database instance.
        fts_table: FTS virtual table name (e.g. ``nodes_fts``).
        content_table: Content table name (e.g. ``nodes``).
        pk_column: Primary-key column name (must be UNINDEXED in the FTS).
        fts_columns: Columns to index (e.g. ``["label_text", "definition_text"]``).
            These are stored in the FTS index and searched.
    """

    def __init__(
        self,
        db: SemantikaDB,
        *,
        fts_table: str,
        content_table: str,
        pk_column: str,
        fts_columns: list[str],
    ) -> None:
        self.db = db
        self.fts_table = fts_table
        self.content_table = content_table
        self.pk_column = pk_column
        self.fts_columns = fts_columns

    # ── Helpers ──────────────────────────────────────────────────────────

    def _resolve_conn(self, conn: sqlite3.Connection | None = None) -> SemantikaDB | sqlite3.Connection:
        """Return *conn* if given, otherwise ``self.db``."""
        return conn if conn is not None else self.db

    def _all_col_defs(self) -> str:
        """Return column definitions for ``CREATE VIRTUAL TABLE`` DDL.

        The PK column is marked ``UNINDEXED``; the rest are full-text indexed.
        """
        parts = [f"{self.pk_column} UNINDEXED"]
        parts.extend(self.fts_columns)
        return ",\n            ".join(parts)

    def _col_list(self) -> str:
        """Return comma-separated column names (PK first, then indexed columns)."""
        cols = [self.pk_column]
        cols.extend(self.fts_columns)
        return ", ".join(cols)

    # ── Lifecycle ────────────────────────────────────────────────────────

    def ensure(self) -> None:
        """Ensure the FTS virtual table exists and is populated.

        Idempotent — uses ``CREATE VIRTUAL TABLE IF NOT EXISTS``.

        Always calls :meth:`populate` after table creation.  The underlying
        ``INSERT OR IGNORE`` handles idempotency so repeated calls do not
        create duplicate index entries.

        Note: ``SELECT COUNT(*)`` on a ``content=`` FTS5 table returns the
        **content-table** row count (not the FTS index entry count), so we
        cannot use it to decide whether to populate.
        """
        col_defs = self._all_col_defs()
        self.db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {self.fts_table} USING fts5(\n"
            f"            {col_defs},\n"
            f"            content={self.content_table},\n"
            f"            content_rowid=rowid,\n"
            f"            tokenize='unicode61'\n"
            "        )"
        )
        self.populate()

    def populate(self) -> None:
        """Populate the FTS index from the content table.

        Uses ``INSERT OR IGNORE`` so that concurrent callers do not fail on
        duplicate rowids (race condition on concurrent startup).
        """
        col_list = self._col_list()
        try:
            self.db.execute(
                f"INSERT OR IGNORE INTO {self.fts_table} (rowid, {col_list})"
                f" SELECT rowid, {col_list} FROM {self.content_table}"
            )
        except sqlite3.DatabaseError:
            logger.warning(
                "Failed to populate %s — LIKE fallback will be used",
                self.fts_table,
                exc_info=True,
            )

    # ── Single-row operations ────────────────────────────────────────────

    def index(self, pk: str, conn: sqlite3.Connection | None = None) -> None:
        """Index a single row in the FTS table."""
        c = self._resolve_conn(conn)
        col_list = self._col_list()

        if isinstance(c, sqlite3.Connection):
            row = c.execute(
                f"SELECT rowid, {col_list} FROM {self.content_table} WHERE {self.pk_column} = ?",
                (pk,),
            ).fetchone()
            if not row:
                return
            rowid = row[0]
            # row is sqlite3.Row — access by index
            values = [str(row[i + 2] or "") if row[i + 2] is not None else "" for i in range(len(self.fts_columns))]
        else:
            row = self.db.execute_one(
                f"SELECT rowid, {col_list} FROM {self.content_table} WHERE {self.pk_column} = ?",
                (pk,),
            )
            if not row:
                return
            rowid = row["rowid"]
            values = [row.get(c, "") or "" for c in self.fts_columns]

        col_list_full = f"rowid, {self._col_list()}"
        placeholders = ", ".join(["?"] * (2 + len(self.fts_columns)))
        try:
            c.execute(
                f"INSERT INTO {self.fts_table} ({col_list_full}) VALUES ({placeholders})",
                (rowid, pk, *values),
            )
        except sqlite3.DatabaseError as exc:
            logger.warning(
                "FTS index insert failed for %s=%s: %s",
                self.pk_column, pk, exc,
            )

    def remove(self, pk: str, conn: sqlite3.Connection | None = None, rowid: int | None = None) -> bool:
        """Remove a row from the FTS index.

        If *rowid* is not given, it is fetched first (extra query).

        Returns:
            ``True`` if the removal was successful, ``False`` otherwise.
        """
        if rowid is None:
            c = self._resolve_conn(conn)
            if isinstance(c, sqlite3.Connection):
                row = c.execute(
                    f"SELECT rowid FROM {self.content_table} WHERE {self.pk_column} = ?",
                    (pk,),
                ).fetchone()
                rowid_val = row[0] if row else None
            else:
                row = self.db.execute_one(
                    f"SELECT rowid FROM {self.content_table} WHERE {self.pk_column} = ?",
                    (pk,),
                )
                rowid_val = row["rowid"] if row else None
            if rowid_val is None:
                return False
            rowid = rowid_val
        return self.remove_by_rowid(pk, rowid, conn)

    def remove_by_rowid(self, pk: str, rowid: int, conn: sqlite3.Connection | None = None) -> bool:
        """Remove a rowid from the FTS index.

        Uses ``DELETE FROM {fts_table} WHERE rowid = ?``, which is the
        correct FTS5 row-deletion syntax for modern SQLite (3.20+).
        When called without an explicit connection (standalone), wraps the
        operation in a ``db.transaction()`` context.

        The older ``INSERT INTO ... VALUES('delete', ?)`` syntax is not
        supported in all FTS5 configurations.
        """
        if conn is not None:
            try:
                conn.execute(
                    f"DELETE FROM {self.fts_table} WHERE rowid = ?",
                    (rowid,),
                )
                return True
            except sqlite3.DatabaseError as exc:
                logger.warning(
                    "FTS delete failed for %s=%s (rowid=%s): %s",
                    self.pk_column, pk, rowid, exc,
                )
                return False
        else:
            try:
                self.db.execute(
                    f"DELETE FROM {self.fts_table} WHERE rowid = ?",
                    (rowid,),
                )
                return True
            except sqlite3.DatabaseError as exc:
                logger.warning(
                    "FTS delete failed for %s=%s (rowid=%s): %s",
                    self.pk_column, pk, rowid, exc,
                )
                return False

    # ── Maintenance ──────────────────────────────────────────────────────

    def optimize(self) -> None:
        """Optimize the FTS5 index — merges b-tree segments.

        Non-critical — failures are silently logged.  Should be called
        periodically (e.g. every ~50 creates) to prevent search-performance
        degradation from accumulated incremental updates.
        """
        try:
            self.db.execute(
                f"INSERT INTO {self.fts_table}({self.fts_table}) VALUES('optimize')"
            )
        except sqlite3.DatabaseError as exc:
            logger.debug("FTS5 optimize failed (non-critical): %s", exc)

    def rebuild(self) -> None:
        """Rebuild the FTS index from the content table.

        If the ``rebuild`` command fails (corruption), drops the FTS table
        and recreates it from scratch.
        """
        try:
            self.db.execute(
                f"INSERT INTO {self.fts_table}({self.fts_table}) VALUES('rebuild')"
            )
        except sqlite3.DatabaseError:
            logger.warning("%s FTS rebuild failed — recreating table", self.content_table)
            for suffix in ("_data", "_idx", "_docsize", "_config", "_content"):
                try:
                    self.db.execute(f"DROP TABLE IF EXISTS {self.fts_table}{suffix}")
                except sqlite3.DatabaseError:
                    pass
            try:
                self.db.execute(f"DROP TABLE IF EXISTS {self.fts_table}")
            except sqlite3.DatabaseError:
                pass
            self.ensure()

    # ── Query helpers ────────────────────────────────────────────────────

    @staticmethod
    def sanitize_query(query: str, keywords: frozenset[str] | None = None) -> str:
        """Sanitize a user query string for FTS5 MATCH.

        Strips non-alphanumeric characters from each token and lowercases
        FTS5 keywords so they are treated as content terms rather than
        operators.

        Returns the cleaned query, or an empty string if no valid tokens
        remain.
        """
        if not query or "_" in query or "%" in query:
            return ""
        if keywords is None:
            from semantika.graph.constants import FTS5_KEYWORDS
            keywords = FTS5_KEYWORDS
        safe_tokens: list[str] = []
        for word in query.strip().split():
            cleaned = "".join(c for c in word if c.isalnum())
            if not cleaned:
                continue
            if cleaned.upper() in keywords:
                cleaned = cleaned.lower()
            safe_tokens.append(f"{cleaned}*")
        if not safe_tokens:
            return ""
        return " OR ".join(safe_tokens)

    def col_list(self) -> str:
        """Public accessor for the column list (used in search queries)."""
        return self._col_list()

    def pk_column_name(self) -> str:
        """Public accessor for the PK column name."""
        return self.pk_column
