"""Tests for the backup/export/import module — ported to lightercore API."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from lightercore.backup import (
    BackupStrategy,
    _backup_dir,
    _backup_filename,
    _config_path,
    _timestamp,
    add_strategy,
    backup_all_strategies,
    backup_database,
    export_data,
    get_strategy,
    import_data,
    list_backups,
    list_strategies,
    load_config,
    prune_backups,
    remove_strategy,
    resolve_target_path,
    restore_by_timestamp,
    restore_latest,
    save_config,
    update_strategy,
    verify_strategy_target,
)
from lightercore.paths import data_dir as lc_data_dir, config_dir as lc_config_dir


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect data_dir and config_dir to isolated temp paths."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("SEMANTIKA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(config_dir))


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    """Create a minimal SQLite database for backup tests."""
    import sqlite3

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "semantika.db"

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello')")
    conn.commit()
    conn.close()

    return db_path


# ── Filename helpers ──────────────────────────────────────────────────────


def test_backup_filename_generates_correct_name() -> None:
    """_backup_filename produces the expected format."""
    name = _backup_filename("semantika", "daily", "20260704T120000123456")
    assert name == "semantika_daily_20260704T120000123456.db"


def test_timestamp_format() -> None:
    """_timestamp returns an ISO-like string without colons."""
    ts = _timestamp()
    assert "T" in ts
    assert ":" not in ts
    assert len(ts) >= 15


# ── BackupDatabase ────────────────────────────────────────────────────────


class TestBackupDatabase:
    def test_backup_creates_file(self, seeded_db: Path) -> None:
        """backup_database creates a timestamped copy in .backups/."""
        result = backup_database(seeded_db, retention=10)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".db"
        assert ".backups" in str(result.parent)

    def test_backup_nonexistent_file(self) -> None:
        """backup_database returns None for missing source."""
        result = backup_database(Path("/nonexistent/path.db"))
        assert result is None


# ── ListBackups ───────────────────────────────────────────────────────────


class TestListBackups:
    def test_list_empty(self) -> None:
        """list_backups returns empty list when no backups exist."""
        assert list_backups() == []

    def test_list_after_backup(self, seeded_db: Path) -> None:
        """list_backups returns the backup after backup_database."""
        backup_database(seeded_db, retention=10)
        entries = list_backups()
        assert len(entries) >= 1
        assert entries[0]["stem"] in ("semantika", "test")


# ── Strategy CRUD ─────────────────────────────────────────────────────────


class TestStrategyCRUD:
    def test_list_strategies_default(self) -> None:
        """list_strategies returns at least the default."""
        strategies = list_strategies()
        assert len(strategies) >= 1
        assert strategies[0]["id"] == "default"

    def test_add_strategy(self) -> None:
        """add_strategy adds a new strategy."""
        s = add_strategy(BackupStrategy(id="hourly", label="Hourly",
                                        interval_minutes=60, max_copies=5))
        assert s["id"] == "hourly"
        assert s["max_copies"] == 5

    def test_get_strategy(self) -> None:
        """get_strategy returns a strategy by id."""
        s = get_strategy("default")
        assert s is not None
        assert s["id"] == "default"

    def test_update_strategy(self) -> None:
        """update_strategy modifies fields."""
        updated = update_strategy("default", max_copies=3, label="Changed")
        assert updated is not None
        assert updated["max_copies"] == 3
        assert updated["label"] == "Changed"

    def test_update_strategy_not_found(self) -> None:
        """update_strategy returns None for unknown id."""
        assert update_strategy("nope", max_copies=1) is None

    def test_remove_strategy(self) -> None:
        """remove_strategy removes a strategy."""
        add_strategy(BackupStrategy(id="toremove", label="Remove me"))
        remove_strategy("toremove")
        assert get_strategy("toremove") is None

    def test_remove_strategy_not_found(self) -> None:
        """remove_strategy returns False for unknown id."""
        assert remove_strategy("nope") is False

    def test_test_strategy_local(self) -> None:
        """test_strategy succeeds for local target."""
        s = get_strategy("default")
        assert s is not None
        result = verify_strategy_target(s)
        assert result["success"] is True
        assert "writable" in result["message"]


# ── Config ────────────────────────────────────────────────────────────────


class TestBackupConfig:
    def test_load_default_config(self) -> None:
        """load_config returns defaults when no config file exists."""
        cfg = load_config()
        assert cfg["version"] == 3
        assert len(cfg["strategies"]) == 1
        assert cfg["strategies"][0]["id"] == "default"

    def test_save_and_load(self) -> None:
        """save_config persists and load_config retrieves."""
        cfg = load_config()
        cfg["strategies"].append({
            "id": "nightly", "label": "Nightly",
            "enabled": True, "interval_minutes": 1440,
            "max_copies": 7, "target": "local",
        })
        save_config(cfg)
        loaded = load_config()
        ids = [s["id"] for s in loaded["strategies"]]
        assert "nightly" in ids


# ── Export / Import ──────────────────────────────────────────────────────


class TestExportImport:
    def _make_db_files(self, tmp_path: Path, names: list[str]) -> None:
        import sqlite3
        for name in names:
            db_path = tmp_path / "data" / name
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE t (x TEXT)")
            conn.execute("INSERT INTO t VALUES (?)", (f"{name} data",))
            conn.commit()
            conn.close()

    def test_export_creates_archive(self, tmp_path: Path) -> None:
        """export_data creates a timestamped 7z archive."""
        self._make_db_files(tmp_path, ["semantika.db"])
        result = export_data(str(tmp_path / "exports"))
        assert result.exists()
        assert result.suffix == ".7z"
        # Verify archive content
        import py7zr
        with py7zr.SevenZipFile(str(result), "r") as arc:
            names = arc.getnames()
            assert "manifest.json" in names
            assert "semantika.db" in names

    def test_export_manifest_valid(self, tmp_path: Path) -> None:
        """Export manifest contains valid metadata."""
        self._make_db_files(tmp_path, ["semantika.db"])
        result = export_data(str(tmp_path / "exports"))
        import py7zr, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with py7zr.SevenZipFile(str(result), "r") as arc:
                arc.extractall(path=tmp)
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            assert "version" in manifest
            assert "files" in manifest
            assert "semantika.db" in manifest["files"]

    def test_import_restores_files(self, tmp_path: Path) -> None:
        """import_data restores files from 7z archive."""
        self._make_db_files(tmp_path, ["semantika.db"])
        export_path = export_data(str(tmp_path / "exports"))
        (tmp_path / "data" / "semantika.db").unlink()
        result = import_data(str(export_path), force=True)
        assert "semantika.db" in result["imported"]
        assert (tmp_path / "data" / "semantika.db").exists()

    def test_import_missing_archive(self, tmp_path: Path) -> None:
        """import_data raises on nonexistent archive."""
        with pytest.raises(FileNotFoundError):
            import_data(str(tmp_path / "nonexistent.7z"))


# ── Semantika-specific helpers ────────────────────────────────────────────


class TestSemantikaBackupHelpers:
    """Tests for semantika-specific backup helpers (core/backup.py)."""

    def test_db_path(self) -> None:
        from semantika.core.backup import _db_path
        path = _db_path()
        assert str(path).endswith("semantika.db")
        assert path.name == "semantika.db"

    def test_parse_backup_filename_new_format(self) -> None:
        from semantika.core.backup import _parse_backup_filename
        result = _parse_backup_filename("semantika_daily_20260704T120000.db")
        assert result is not None
        assert result["stem"] == "semantika"
        assert result["strategy"] == "daily"
        assert result["timestamp"] == "20260704T120000"
        assert result["suffix"] == "db"

    def test_parse_backup_filename_new_format_bak(self) -> None:
        from semantika.core.backup import _parse_backup_filename
        result = _parse_backup_filename("semantika_weekly_20260704T120000.bak")
        assert result is not None
        assert result["stem"] == "semantika"
        assert result["strategy"] == "weekly"
        assert result["suffix"] == "bak"

    def test_parse_backup_filename_legacy_format(self) -> None:
        from semantika.core.backup import _parse_backup_filename
        result = _parse_backup_filename("semantika_20260704T120000.db")
        assert result is not None
        assert result["stem"] == "semantika"
        assert result["strategy"] == "legacy"
        assert result["timestamp"] == "20260704T120000"

    def test_parse_backup_filename_no_match(self) -> None:
        from semantika.core.backup import _parse_backup_filename
        assert _parse_backup_filename("random_file.txt") is None
        assert _parse_backup_filename("") is None

    def test_parse_backup_filename_custom_stem(self) -> None:
        from semantika.core.backup import _parse_backup_filename
        result = _parse_backup_filename("myapp_daily_20260704T120000.db")
        assert result is not None
        assert result["stem"] == "myapp"
        assert result["strategy"] == "daily"
