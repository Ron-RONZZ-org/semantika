"""Tests for the shared FTS5Manager class.

Verifies that the FTS5Manager correctly handles lifecycle, single-row
operations, maintenance, and query sanitization.  The actual integration
with NodeService and PredicateService is tested in their respective
service-test files — this file focuses on the manager itself.
"""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from semantika.core import SemantikaDB
from semantika.core.fts import FTS5Manager


@pytest.fixture
def db(tmp_path: Path) -> SemantikaDB:
    """Create an isolated test database with a simple content table."""
    db_path = tmp_path / "test.db"
    db = SemantikaDB(db_path)
    db.execute(
        "CREATE TABLE IF NOT EXISTS widgets ("
        "  widget_id TEXT PRIMARY KEY,"
        "  name TEXT NOT NULL DEFAULT '',"
        "  description TEXT NOT NULL DEFAULT ''"
        ")"
    )
    db.execute("PRAGMA foreign_keys=ON")
    return db


@pytest.fixture
def mgr(db: SemantikaDB) -> FTS5Manager:
    """Return an FTS5Manager for the widgets table."""
    return FTS5Manager(
        db=db,
        fts_table="widgets_fts",
        content_table="widgets",
        pk_column="widget_id",
        fts_columns=["name", "description"],
    )


class TestFTS5ManagerLifecycle:
    def test_ensure_creates_table(self, db: SemantikaDB, mgr: FTS5Manager):
        """ensure() creates the FTS virtual table."""
        mgr.ensure()
        row = db.execute_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='widgets_fts'"
        )
        assert row is not None

    def test_ensure_is_idempotent(self, mgr: FTS5Manager):
        """Calling ensure() twice does not raise."""
        mgr.ensure()
        mgr.ensure()  # should not raise

    def test_populate_after_insert(self, db: SemantikaDB, mgr: FTS5Manager):
        """Populate fills the FTS index from the content table."""
        db.execute(
            "INSERT INTO widgets (widget_id, name, description) VALUES (?, ?, ?)",
            ("w1", "Widget One", "The first widget"),
        )
        mgr.ensure()
        # Verify via MATCH (COUNT(*) on content= FTS reflects content table)
        results = db.execute(
            "SELECT widget_id FROM widgets_fts WHERE widgets_fts MATCH ?",
            ("Widget*",),
        )
        assert len(results) >= 1


class TestFTS5ManagerIndex:
    def test_index_single_row(self, db: SemantikaDB, mgr: FTS5Manager):
        """index() inserts a single row into the FTS index."""
        db.execute(
            "INSERT INTO widgets (widget_id, name, description) VALUES (?, ?, ?)",
            ("w1", "Widget", "A widget"),
        )
        mgr.ensure()
        mgr.index("w1")
        results = db.execute(
            "SELECT widget_id FROM widgets_fts WHERE widgets_fts MATCH ?",
            ("Widget*",),
        )
        assert len(results) >= 1

    def test_index_within_transaction(self, db: SemantikaDB, mgr: FTS5Manager):
        """index() works when called with an explicit connection."""
        db.execute(
            "INSERT INTO widgets (widget_id, name, description) VALUES (?, ?, ?)",
            ("w2", "Widget 2", "Second widget"),
        )
        mgr.ensure()
        with db.transaction() as conn:
            mgr.index("w2", conn=conn)
        results = db.execute(
            "SELECT widget_id FROM widgets_fts WHERE widgets_fts MATCH ?",
            ("Widget*",),
        )
        assert len(results) >= 1


class TestFTS5ManagerRemove:
    def test_remove_by_rowid(self, db: SemantikaDB, mgr: FTS5Manager):
        """remove_by_rowid removes a row from the FTS index.

        Note: ``SELECT COUNT(*)`` on a ``content=`` FTS table reflects the
        content-table row count, not the index.  We verify removal via MATCH.
        """
        db.execute(
            "INSERT INTO widgets (widget_id, name, description) VALUES (?, ?, ?)",
            ("w1", "Widget", "Desc"),
        )
        mgr.ensure()
        mgr.index("w1")

        # Verify it's findable first
        before = db.execute(
            "SELECT widget_id FROM widgets_fts WHERE widgets_fts MATCH ?",
            ("Widget*",),
        )
        assert len(before) >= 1

        row = db.execute_one("SELECT rowid FROM widgets WHERE widget_id = ?", ("w1",))
        assert row is not None
        mgr.remove_by_rowid("w1", row["rowid"])

        # Verify it's gone from search results (the 'delete' affects MATCH)
        after = db.execute(
            "SELECT widget_id FROM widgets_fts WHERE widgets_fts MATCH ?",
            ("Widget*",),
        )
        assert len(after) == 0

    def test_remove_by_pk(self, db: SemantikaDB, mgr: FTS5Manager):
        """remove() looks up rowid automatically."""
        db.execute(
            "INSERT INTO widgets (widget_id, name, description) VALUES (?, ?, ?)",
            ("w2", "Widget 2", "Desc 2"),
        )
        mgr.ensure()
        mgr.index("w2")

        # Verify it's findable first
        before = db.execute(
            "SELECT widget_id FROM widgets_fts WHERE widgets_fts MATCH ?",
            ("Widget*",),
        )
        assert len(before) >= 1

        mgr.remove("w2")

        # Verify it's gone from search results
        after = db.execute(
            "SELECT widget_id FROM widgets_fts WHERE widgets_fts MATCH ?",
            ("Widget*",),
        )
        assert len(after) == 0

    def test_remove_nonexistent_returns_false(self, mgr: FTS5Manager):
        """remove() returns False when the PK is not in the content table."""
        result = mgr.remove("nonexistent")
        assert result is False


class TestFTS5ManagerMaintenance:
    def test_optimize_does_not_raise(self, mgr: FTS5Manager):
        """optimize() runs without error (no-op on empty table)."""
        mgr.ensure()
        mgr.optimize()  # should not raise

    def test_rebuild_does_not_raise(self, mgr: FTS5Manager):
        """rebuild() runs without error."""
        mgr.ensure()
        mgr.rebuild()  # should not raise

    def test_rebuild_recreates_corrupted_table(self, db: SemantikaDB, mgr: FTS5Manager):
        """rebuild() drops and recreates the FTS table if corruption occurs."""
        from unittest.mock import patch

        # Force a DatabaseError on the first rebuild attempt
        original_execute = db.execute

        def fail_once(*args, **kwargs):
            if "rebuild" in str(args[0]):
                raise sqlite3.DatabaseError("simulated corruption")
            return original_execute(*args, **kwargs)

        with patch.object(db, "execute", side_effect=fail_once):
            mgr.ensure()
            mgr.rebuild()  # should fall back to drop + recreate

        # Table should still be usable
        row = db.execute_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='widgets_fts'"
        )
        assert row is not None


class TestFTS5ManagerSanitize:
    def test_sanitize_simple_query(self):
        """sanitize_query() preserves alphanumeric tokens."""
        result = FTS5Manager.sanitize_query("hello world")
        assert "hello*" in result
        assert "world*" in result

    def test_sanitize_fts5_keywords(self):
        """FTS5 keywords like AND, OR are lowercased."""
        result = FTS5Manager.sanitize_query("cat AND dog")
        assert "and*" in result  # not AND*
        assert "cat*" in result
        assert "dog*" in result

    def test_sanitize_strips_punctuation(self):
        """Non-alphanumeric characters are stripped from tokens."""
        result = FTS5Manager.sanitize_query("hello-world! test.value")
        assert "helloworld*" in result
        assert "testvalue*" in result

    def test_sanitize_empty_string(self):
        """Empty string returns empty string."""
        assert FTS5Manager.sanitize_query("") == ""

    def test_sanitize_wildcards_rejected(self):
        """Strings containing _ or % return empty."""
        assert FTS5Manager.sanitize_query("test_123") == ""
        assert FTS5Manager.sanitize_query("test%123") == ""

    def test_sanitize_no_valid_tokens(self):
        """String with only punctuation returns empty."""
        assert FTS5Manager.sanitize_query("!!! ???") == ""


class TestFTS5ManagerColList:
    def test_col_list_includes_pk_and_fts_columns(self, mgr: FTS5Manager):
        """col_list() returns the expected comma-separated columns."""
        cols = mgr.col_list()
        assert "widget_id" in cols
        assert "name" in cols
        assert "description" in cols

    def test_pk_column_name(self, mgr: FTS5Manager):
        """pk_column_name() returns the PK column."""
        assert mgr.pk_column_name() == "widget_id"
