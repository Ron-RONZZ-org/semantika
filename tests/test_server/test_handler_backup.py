"""Tests for backup command handlers via dispatch().

Tests all !backup commands with mocked lightercore.backup functions.
Uses isolated DB and services (same pattern as test_handler_dispatch.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from semantika.core import SemantikaDB
from semantika.graph.db import SCHEMA, REVIEW_SCHEMA, PROOF_SCHEMA
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.predicate_group_service import PredicateGroupService
from semantika.graph.triple_service import TripleService
from semantika.graph.review_service import ReviewService
from semantika.graph.proof_service import ProofService

# Trigger handler registration
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> SemantikaDB:
    """Create an isolated test database."""
    db_path = tmp_path / "test.db"
    db = SemantikaDB(db_path)
    for table, sql in SCHEMA.items():
        db.init_schema({table: sql})
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_triples_pos ON triples(predicate_id, object_value, subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_triples_osp ON triples(object_value, object_type, predicate_id, subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_triples_pred_subj ON triples(predicate_id, subject_id)",
    ]:
        db.execute(idx)
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
        "  node_id UNINDEXED, label_text, definition_text,"
        "  content=nodes, content_rowid=rowid, tokenize='unicode61'"
        ")"
    )
    for table, sql in {**REVIEW_SCHEMA, **PROOF_SCHEMA}.items():
        db.init_schema({table: sql})
    db.execute("PRAGMA foreign_keys=ON")
    return db


@pytest.fixture
def services(db: SemantikaDB) -> dict:
    """Return all services initialized on the test DB."""
    return {
        "node": NodeService(db),
        "predicate": PredicateService(db),
        "predicate_group": PredicateGroupService(db),
        "triple": TripleService(db),
        "review": ReviewService(db),
        "proof": ProofService(db),
    }


@pytest.fixture(autouse=True)
def mock_services(monkeypatch: pytest.MonkeyPatch, services: dict) -> None:
    """Mock get_services() to return the isolated services."""
    import semantika.graph.db as graph_db

    monkeypatch.setattr(graph_db, "get_services", lambda: services)


@pytest.fixture(autouse=True)
def mock_get_db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Mock get_db_path to return a path under tmp_path."""

    def _fake_get_db_path() -> Path:
        return tmp_path / "semantika.db"

    import semantika.graph.db as graph_db

    monkeypatch.setattr(graph_db, "get_db_path", _fake_get_db_path)


# ── Backup handler tests ─────────────────────────────────────────────────


class TestBackupNow:
    """!backup now"""

    @patch("semantika.core.backup.backup_all_strategies")
    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.resolve_target_path")
    def test_backup_now_creates_backups(
        self,
        mock_resolve: pytest.MagicMock,
        mock_config: pytest.MagicMock,
        mock_backup: pytest.MagicMock,
    ) -> None:
        mock_backup.return_value = [Path("/backups/semantika_daily_20260704T120000.db")]
        mock_config.return_value = {
            "strategies": [{"id": "daily", "label": "Daily", "max_copies": 5}]
        }
        mock_resolve.return_value = Path("/backups")
        result = dispatch(["backup", "now"], {})
        assert result["type"] == "status"
        assert "Backup Complete" in result["title"]

    @patch("semantika.core.backup.backup_all_strategies")
    def test_backup_now_no_data(self, mock_backup: pytest.MagicMock) -> None:
        """backup_all_strategies returns empty list -> no data message."""
        mock_backup.return_value = []
        result = dispatch(["backup", "now"], {})
        assert result["type"] == "status"
        assert "No data files found" in result["data"]["message"]


class TestBackupList:
    """!backup list"""

    @patch("semantika.core.backup.list_backups")
    def test_backup_list(self, mock_list: pytest.MagicMock) -> None:
        mock_list.return_value = [
            {
                "path": Path("semantika_daily_20260704T120000.db"),
                "timestamp": "20260704T120000",
                "size_bytes": 4096,
                "stem": "semantika",
                "strategy": "daily",
            }
        ]
        result = dispatch(["backup", "list"], {})
        assert result["type"] == "status"
        assert "Backups" in result["title"]
        assert len(result["data"]["entries"]) == 1

    @patch("semantika.core.backup.list_backups")
    def test_backup_list_empty(self, mock_list: pytest.MagicMock) -> None:
        mock_list.return_value = []
        result = dispatch(["backup", "list"], {})
        assert result["type"] == "status"
        assert "No backups found" in result["data"]["message"]

    @patch("semantika.core.backup.list_backups")
    def test_backup_list_filter_stem(self, mock_list: pytest.MagicMock) -> None:
        mock_list.return_value = [
            {
                "path": Path("semantika_daily_20260704T120000.db"),
                "timestamp": "20260704T120000",
                "size_bytes": 4096,
                "stem": "semantika",
                "strategy": "daily",
            },
            {
                "path": Path("other_weekly_20260705T120000.db"),
                "timestamp": "20260705T120000",
                "size_bytes": 2048,
                "stem": "other",
                "strategy": "weekly",
            },
        ]
        result = dispatch(["backup", "list"], {"stem": "semantika"})
        assert len(result["data"]["entries"]) == 1
        assert result["data"]["entries"][0]["database"] == "semantika"

    @patch("semantika.core.backup.list_backups")
    def test_backup_list_filter_strategy(self, mock_list: pytest.MagicMock) -> None:
        mock_list.return_value = [
            {
                "path": Path("semantika_daily.db"),
                "timestamp": "20260704T120000",
                "size_bytes": 4096,
                "stem": "semantika",
                "strategy": "daily",
            },
            {
                "path": Path("semantika_weekly.db"),
                "timestamp": "20260705T120000",
                "size_bytes": 2048,
                "stem": "semantika",
                "strategy": "weekly",
            },
        ]
        result = dispatch(["backup", "list"], {"strategy": "weekly"})
        assert len(result["data"]["entries"]) == 1
        assert result["data"]["entries"][0]["strategy"] == "weekly"


class TestBackupRestore:
    """!backup restore"""

    @patch("semantika.core.backup.restore_latest")
    @patch("semantika.graph.db.close_db")
    @patch("semantika.graph.db.get_db_path")
    @patch("semantika.graph.db.init_db")
    def test_restore_latest(
        self,
        mock_init: pytest.MagicMock,
        mock_path: pytest.MagicMock,
        mock_close: pytest.MagicMock,
        mock_restore: pytest.MagicMock,
    ) -> None:
        mock_path.return_value = Path("/tmp/semantika.db")
        mock_restore.return_value = Path("/tmp/.backups/semantika_daily_20260704T120000.db")
        result = dispatch(["backup", "restore"], {})
        assert result["data"]["file"] is not None
        mock_close.assert_called_once()
        mock_init.assert_called_once()

    @patch("semantika.core.backup.restore_by_timestamp")
    @patch("semantika.graph.db.close_db")
    @patch("semantika.graph.db.get_db_path")
    @patch("semantika.graph.db.init_db")
    def test_restore_with_timestamp(
        self,
        mock_init: pytest.MagicMock,
        mock_path: pytest.MagicMock,
        mock_close: pytest.MagicMock,
        mock_restore: pytest.MagicMock,
    ) -> None:
        mock_path.return_value = Path("/tmp/semantika.db")
        mock_restore.return_value = Path("/tmp/.backups/semantika_daily_20260704T120000.db")
        result = dispatch(["backup", "restore"], {"timestamp": "20260704T120000"})
        assert result["type"] == "status"
        mock_restore.assert_called_with("20260704T120000", str(Path("/tmp/semantika.db").parent))

    @patch("semantika.core.backup.restore_latest")
    @patch("semantika.graph.db.close_db")
    @patch("semantika.graph.db.get_db_path")
    def test_restore_not_found(
        self,
        mock_path: pytest.MagicMock,
        mock_close: pytest.MagicMock,
        mock_restore: pytest.MagicMock,
    ) -> None:
        mock_path.return_value = Path("/tmp/semantika.db")
        mock_restore.side_effect = FileNotFoundError("No backups found")
        with pytest.raises(Exception, match="No backups found"):
            dispatch(["backup", "restore"], {})


class TestBackupPrune:
    """!backup prune"""

    @patch("semantika.core.backup.prune_backups")
    def test_backup_prune(self, mock_prune: pytest.MagicMock) -> None:
        mock_prune.return_value = 3
        result = dispatch(["backup", "prune"], {"keep": "5"})
        assert "Deleted 3" in result["data"]["message"]

    @patch("semantika.core.backup.prune_backups")
    def test_backup_prune_no_keep(self, mock_prune: pytest.MagicMock) -> None:
        mock_prune.return_value = 0
        result = dispatch(["backup", "prune"], {})
        assert "Deleted 0" in result["data"]["message"]

    def test_backup_prune_invalid_keep(self) -> None:
        with pytest.raises(Exception, match="Invalid --keep"):
            dispatch(["backup", "prune"], {"keep": "abc"})


class TestBackupConfig:
    """!backup config"""

    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.resolve_target_path")
    def test_config_view(
        self, mock_resolve: pytest.MagicMock, mock_cfg: pytest.MagicMock
    ) -> None:
        mock_cfg.return_value = {
            "strategies": [
                {"id": "daily", "label": "Daily", "interval_minutes": 1440, "max_copies": 7, "enabled": True},
            ]
        }
        mock_resolve.return_value = Path("/backups")
        result = dispatch(["backup", "config"], {})
        assert result["type"] == "status"
        assert "Backup Config" in result["title"]

    @patch("semantika.core.backup.list_strategies")
    @patch("semantika.core.backup.resolve_target_path")
    def test_config_list(
        self, mock_resolve: pytest.MagicMock, mock_list: pytest.MagicMock
    ) -> None:
        mock_list.return_value = [
            {"id": "daily", "label": "Daily", "interval_minutes": 1440, "max_copies": 7, "enabled": True},
        ]
        mock_resolve.return_value = Path("/backups")
        result = dispatch(["backup", "config", "list"], {})
        assert result["type"] == "status"
        assert "Backup Strategies" in result["title"]


class TestBackupConfigAdd:
    """!backup config add"""

    @patch("semantika.core.backup.add_strategy")
    @patch("semantika.core.backup.BackupStrategy")
    def test_config_add(
        self, mock_strategy: pytest.MagicMock, mock_add: pytest.MagicMock
    ) -> None:
        mock_add.return_value = {"id": "hourly", "label": "Hourly"}
        result = dispatch(
            ["backup", "config", "add"],
            {"id": "hourly", "label": "Hourly backups", "interval": "60", "max_copies": "24"},
        )
        assert result["type"] == "status"
        assert "Strategy Added" in result["title"]

    def test_config_add_missing_id(self) -> None:
        with pytest.raises(Exception, match="Missing --id"):
            dispatch(["backup", "config", "add"], {})

    @patch("semantika.core.backup.add_strategy")
    def test_config_add_invalid_interval(
        self, mock_add: pytest.MagicMock
    ) -> None:
        with pytest.raises(Exception, match="Invalid --interval"):
            dispatch(["backup", "config", "add"], {"id": "test", "interval": "abc"})

    @patch("semantika.core.backup.add_strategy")
    def test_config_add_invalid_max_copies(
        self, mock_add: pytest.MagicMock
    ) -> None:
        with pytest.raises(Exception, match="Invalid --max-copies"):
            dispatch(["backup", "config", "add"], {"id": "test", "max_copies": "xyz"})

    def test_config_add_negative_interval(self) -> None:
        with pytest.raises(Exception, match=">= 0"):
            dispatch(["backup", "config", "add"], {"id": "test", "interval": "-1"})

    @patch("semantika.core.backup.add_strategy")
    @patch("semantika.core.backup.BackupStrategy")
    def test_config_add_value_error(
        self, mock_strategy: pytest.MagicMock, mock_add: pytest.MagicMock
    ) -> None:
        mock_add.side_effect = ValueError("Duplicate strategy")
        with pytest.raises(Exception, match="Duplicate strategy"):
            dispatch(["backup", "config", "add"], {"id": "daily"})


class TestBackupConfigModify:
    """!backup config modify"""

    @patch("semantika.core.backup.get_strategy")
    @patch("semantika.core.backup.update_strategy")
    def test_config_modify(
        self, mock_update: pytest.MagicMock, mock_get: pytest.MagicMock
    ) -> None:
        mock_get.return_value = {"id": "daily", "max_copies": 7}
        result = dispatch(
            ["backup", "config", "modify", "daily"],
            {"max_copies": "10", "label": "Updated"},
        )
        assert result["title"] == "Strategy Modified"
        assert "max_copies" in result["data"]["changed"]

    def test_config_modify_missing_id(self) -> None:
        with pytest.raises(Exception, match="Missing strategy id"):
            dispatch(["backup", "config", "modify"], {})

    @patch("semantika.core.backup.get_strategy")
    def test_config_modify_not_found(self, mock_get: pytest.MagicMock) -> None:
        mock_get.return_value = None
        with pytest.raises(Exception, match="not found"):
            dispatch(["backup", "config", "modify", "nope"], {})

    @patch("semantika.core.backup.get_strategy")
    @patch("semantika.core.backup.update_strategy")
    def test_config_modify_no_changes(
        self, mock_update: pytest.MagicMock, mock_get: pytest.MagicMock
    ) -> None:
        mock_get.return_value = {"id": "daily"}
        with pytest.raises(Exception, match="No changes"):
            dispatch(["backup", "config", "modify", "daily"], {})

    @patch("semantika.core.backup.get_strategy")
    def test_config_modify_invalid_interval(
        self, mock_get: pytest.MagicMock
    ) -> None:
        mock_get.return_value = {"id": "daily"}
        with pytest.raises(Exception, match="Invalid interval"):
            dispatch(["backup", "config", "modify", "daily"], {"interval": "abc"})

    @patch("semantika.core.backup.get_strategy")
    @patch("semantika.core.backup.update_strategy")
    def test_config_modify_update_value_error(
        self, mock_update: pytest.MagicMock, mock_get: pytest.MagicMock
    ) -> None:
        mock_get.return_value = {"id": "daily"}
        mock_update.side_effect = ValueError("Bad update")
        with pytest.raises(Exception, match="Bad update"):
            dispatch(["backup", "config", "modify", "daily"], {"max_copies": "5"})


class TestBackupConfigDelete:
    """!backup config delete"""

    def test_config_delete_missing_id(self) -> None:
        with pytest.raises(Exception, match="Missing strategy id"):
            dispatch(["backup", "config", "delete"], {})

    @patch("semantika.core.backup.remove_strategy")
    def test_config_delete_value_error(
        self, mock_remove: pytest.MagicMock
    ) -> None:
        mock_remove.side_effect = ValueError("Strategy not found")
        with pytest.raises(Exception, match="Strategy not found"):
            dispatch(["backup", "config", "delete", "nope"], {})

    @patch("semantika.core.backup.remove_strategy")
    def test_config_delete_ok(
        self, mock_remove: pytest.MagicMock
    ) -> None:
        result = dispatch(["backup", "config", "delete", "daily"], {})
        assert result["title"] == "Strategy Deleted"


class TestBackupConfigTest:
    """!backup config test"""

    def test_config_test_missing_id(self) -> None:
        with pytest.raises(Exception, match="Missing strategy id"):
            dispatch(["backup", "config", "test"], {})

    @patch("semantika.core.backup.verify_strategy_target")
    def test_config_test_success(
        self, mock_verify: pytest.MagicMock
    ) -> None:
        mock_verify.return_value = {"success": True, "message": "Target is writable"}
        result = dispatch(["backup", "config", "test", "daily"], {})
        assert result["title"] == "Test Passed"

    @patch("semantika.core.backup.verify_strategy_target")
    def test_config_test_failure(
        self, mock_verify: pytest.MagicMock
    ) -> None:
        mock_verify.return_value = {
            "success": False,
            "message": "Target not writable",
            "error": "Permission denied",
        }
        result = dispatch(["backup", "config", "test", "daily"], {})
        assert result["type"] == "error"

    @patch("semantika.core.backup.verify_strategy_target")
    def test_config_test_value_error(
        self, mock_verify: pytest.MagicMock
    ) -> None:
        mock_verify.side_effect = ValueError("Bad strategy")
        with pytest.raises(Exception, match="Bad strategy"):
            dispatch(["backup", "config", "test", "daily"], {})


class TestBackupExport:
    """!backup export"""

    @patch("semantika.core.backup.export_data")
    def test_export(self, mock_export: pytest.MagicMock) -> None:
        mock_export.return_value = Path("/tmp/exports/semantika_20260704T120000.7z")
        result = dispatch(["backup", "export"], {})
        assert result["type"] == "status"
        assert "Export Complete" in result["title"]

    @patch("semantika.core.backup.export_data")
    def test_export_with_output(self, mock_export: pytest.MagicMock) -> None:
        mock_export.return_value = Path("/custom/export.7z")
        result = dispatch(["backup", "export"], {"output": "/custom"})
        assert result["type"] == "status"

    @patch("semantika.core.backup.export_data")
    def test_export_os_error(self, mock_export: pytest.MagicMock) -> None:
        mock_export.side_effect = OSError("Disk full")
        with pytest.raises(Exception, match="Disk full"):
            dispatch(["backup", "export"], {})


class TestBackupImport:
    """!backup import"""

    @patch("semantika.graph.db.close_db")
    @patch("semantika.core.backup.import_data")
    @patch("semantika.graph.db.init_db")
    def test_import(
        self,
        mock_init: pytest.MagicMock,
        mock_import: pytest.MagicMock,
        mock_close: pytest.MagicMock,
    ) -> None:
        mock_import.return_value = {
            "imported": ["semantika.db"],
            "skipped": [],
            "errors": [],
        }
        result = dispatch(["backup", "import", "/tmp/export.7z"], {})
        assert result["type"] == "status"
        assert "Import Complete" in result["title"]
        mock_close.assert_called_once()
        mock_init.assert_called_once()

    @patch("semantika.core.backup.import_data")
    def test_import_missing_path(self, mock_import: pytest.MagicMock) -> None:
        with pytest.raises(Exception, match="Missing export path"):
            dispatch(["backup", "import"], {})

    @patch("semantika.graph.db.close_db")
    @patch("semantika.core.backup.import_data")
    def test_import_with_errors(
        self, mock_import: pytest.MagicMock, mock_close: pytest.MagicMock
    ) -> None:
        mock_import.return_value = {
            "imported": ["semantika.db"],
            "skipped": ["old.db"],
            "errors": ["corrupted.db"],
        }
        result = dispatch(["backup", "import", "/tmp/export.7z"], {"force": "true"})
        assert "Imported" in result["data"]["message"]
        assert result["data"]["imported"] == ["semantika.db"]
        assert result["data"]["errors"] == ["corrupted.db"]

    @patch("semantika.graph.db.close_db")
    @patch("semantika.core.backup.import_data")
    def test_import_empty(
        self, mock_import: pytest.MagicMock, mock_close: pytest.MagicMock
    ) -> None:
        mock_import.return_value = {
            "imported": [],
            "skipped": [],
            "errors": [],
        }
        result = dispatch(["backup", "import", "/tmp/export.7z"], {})
        assert "Imported 0" in result["data"]["message"]

    @patch("semantika.graph.db.close_db")
    @patch("semantika.core.backup.import_data")
    def test_import_file_not_found(
        self, mock_import: pytest.MagicMock, mock_close: pytest.MagicMock
    ) -> None:
        mock_import.side_effect = FileNotFoundError("No such file")
        with pytest.raises(Exception, match="No such file"):
            dispatch(["backup", "import", "/tmp/nope.7z"], {})


class TestBackupRoot:
    """!backup (root group)"""

    def test_backup_root(self) -> None:
        result = dispatch(["backup"], {})
        assert result["type"] == "status"
        assert "Backup Commands" in result["title"]
