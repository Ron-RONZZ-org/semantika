"""Tests for core/reset.py — reset_to_fresh_state.

Uses monkeypatched data_dir and mocked keyring to avoid side effects.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from semantika.core.reset import reset_to_fresh_state


@pytest.fixture
def mock_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect data_dir to a temp directory and create a minimal DB."""
    ddir = tmp_path / "semantika"
    ddir.mkdir(parents=True, exist_ok=True)
    # Create a dummy DB so _db_path() exists
    db_path = ddir / "semantika.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS nodes (node_id TEXT PRIMARY KEY)")
    conn.execute(
        "INSERT INTO nodes (node_id) VALUES ('test-node')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "semantika.core.reset.data_dir", lambda: ddir,
    )
    # Make backup module see the same temp dir
    monkeypatch.setattr(
        "semantika.core.backup.data_dir", lambda: ddir,
    )
    return ddir


class TestResetToFreshState:
    """Direct tests of reset_to_fresh_state()."""

    def test_reset_removes_databases(self, mock_data_dir: Path) -> None:
        """Should remove all .db files."""
        result = reset_to_fresh_state()
        assert len(result["databases_removed"]) >= 1
        assert any("semantika.db" in p for p in result["databases_removed"])

    def test_reset_backup(self, mock_data_dir: Path) -> None:
        """Should create backup before deletion."""
        backup_path = mock_data_dir / "backups" / "pre_reset.db"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        result = reset_to_fresh_state(backup_path=str(backup_path))
        assert result["backup_path"] is not None
        assert backup_path.exists()
        # DB should still be removed
        assert len(result["databases_removed"]) >= 1

    @patch("keyring.delete_password")
    def test_reset_clears_credentials(
        self, mock_delete: pytest.MagicMock, mock_data_dir: Path,
    ) -> None:
        """Should attempt to clear known keyring services."""
        from semantika.core.reset import _KNOWN_CREDENTIAL_SERVICES
        result = reset_to_fresh_state()
        assert result["credentials_cleared"] == len(_KNOWN_CREDENTIAL_SERVICES)
        assert mock_delete.call_count == len(_KNOWN_CREDENTIAL_SERVICES)

    def test_reset_no_side_effects_on_other_dirs(
        self, mock_data_dir: Path,
    ) -> None:
        """Should not remove files outside data_dir."""
        outside = mock_data_dir.parent / "important.txt"
        outside.write_text("keep me")
        reset_to_fresh_state()
        assert outside.exists()

    def test_reset_double_reset_idempotent(
        self, mock_data_dir: Path,
    ) -> None:
        """Running reset twice should not error (idempotent)."""
        reset_to_fresh_state()
        # Second reset: no DBs to remove, no credentials to clear
        result = reset_to_fresh_state()
        # Should still report, just nothing happened
        assert isinstance(result, dict)
        assert "databases_removed" in result

    def test_reset_with_files_dir(self, mock_data_dir: Path) -> None:
        """Should remove file attachments."""
        files_dir = mock_data_dir / "semantika" / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        (files_dir / "test.txt").write_text("hello")
        assert files_dir.exists()
        reset_to_fresh_state()
        assert not files_dir.exists()

    def test_known_credential_services_list(self) -> None:
        """Known credential services constant should match implementation."""
        from semantika.core.reset import _KNOWN_CREDENTIAL_SERVICES
        assert "semantika-llm" in _KNOWN_CREDENTIAL_SERVICES
        assert "semantika-key" in _KNOWN_CREDENTIAL_SERVICES

    def test_register_credential_service(self) -> None:
        """register_credential_service adds to the known set."""
        from semantika.core.reset import _KNOWN_CREDENTIAL_SERVICES, register_credential_service
        register_credential_service("semantika-test-service")
        assert "semantika-test-service" in _KNOWN_CREDENTIAL_SERVICES
        # Must not replace the existing set
        assert "semantika-llm" in _KNOWN_CREDENTIAL_SERVICES
