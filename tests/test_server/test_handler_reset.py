"""Tests for reset command handler via dispatch().

Uses mocked ``reset_to_fresh_state`` (lazy-imported inside the handler)
to avoid destructive side effects.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# Trigger handler registration
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch


class TestResetHandler:
    """!reset command handler"""

    @patch("semantika.core.reset.reset_to_fresh_state")
    def test_reset_with_backup_path(
        self, mock_reset: pytest.MagicMock
    ) -> None:
        mock_reset.return_value = {
            "backup_path": "/tmp/backup.db",
            "databases_removed": ["semantika.db"],
            "credentials_cleared": 2,
        }
        result = dispatch(["reset", "/tmp/backup.db"], {})
        assert result["type"] == "status"
        assert "Reset Complete" in result["title"]
        assert "backup_path" in result["data"]

    @patch("semantika.core.reset.reset_to_fresh_state")
    def test_reset_no_backup_confirmed(
        self, mock_reset: pytest.MagicMock
    ) -> None:
        mock_reset.return_value = {
            "databases_removed": ["semantika.db"],
            "credentials_cleared": 2,
        }
        result = dispatch(
            ["reset"],
            {"no-backup": "", "confirmed": "true"},
        )
        assert result["type"] == "status"
        assert "Reset Complete" in result["title"]

    def test_reset_no_backup_not_confirmed(self) -> None:
        """Without --confirmed, returns form-required."""
        result = dispatch(["reset"], {"no-backup": ""})
        assert result["type"] == "form-required"
        assert "Confirm Reset" in result["title"]

    def test_reset_no_path_no_flag(self) -> None:
        """Missing both --no-backup and path raises validation error."""
        with pytest.raises(Exception, match="Provide either"):
            dispatch(["reset"], {})

    def test_reset_path_and_no_backup_conflict(self) -> None:
        """Can't specify both path and --no-backup."""
        with pytest.raises(Exception, match="Cannot specify both"):
            dispatch(["reset", "/tmp/backup.db"], {"no-backup": ""})

    @patch("semantika.core.reset.reset_to_fresh_state")
    def test_reset_file_not_found(
        self, mock_reset: pytest.MagicMock
    ) -> None:
        mock_reset.side_effect = FileNotFoundError("No such file")
        with pytest.raises(Exception, match="Reset failed"):
            dispatch(["reset"], {"no-backup": "", "confirmed": "true"})

    @patch("semantika.core.reset.reset_to_fresh_state")
    def test_reset_os_error(
        self, mock_reset: pytest.MagicMock
    ) -> None:
        mock_reset.side_effect = OSError("Permission denied")
        with pytest.raises(Exception, match="Reset failed"):
            dispatch(["reset"], {"no-backup": "", "confirmed": "true"})
