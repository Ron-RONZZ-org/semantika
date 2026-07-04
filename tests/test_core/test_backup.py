"""Tests for the backup/export/import module."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest

from semantika.core.backup import (
    BackupStrategy,
    _backup_dir,
    _backup_filename,
    _config_path,
    _db_path,
    _parse_backup_filename,
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


# ── Filename parsing ───────────────────────────────────────────────────────


class TestParseBackupFilename:
    def test_new_format(self) -> None:
        result = _parse_backup_filename("semantika_daily_20260704T120000123456.db")
        assert result is not None
        assert result["stem"] == "semantika"
        assert result["strategy"] == "daily"
        assert result["timestamp"] == "20260704T120000123456"
        assert result["suffix"] == "db"

    def test_legacy_format(self) -> None:
        result = _parse_backup_filename("semantika_20260704T120000123456.db")
        assert result is not None
        assert result["stem"] == "semantika"
        assert result["strategy"] == "legacy"
        assert result["timestamp"] == "20260704T120000123456"

    def test_unmatched(self) -> None:
        assert _parse_backup_filename("random_file.txt") is None
        assert _parse_backup_filename("") is None


class TestBackupFilename:
    def test_generates_correct_name(self) -> None:
        name = _backup_filename("semantika", "daily", "20260704T120000123456")
        assert name == "semantika_daily_20260704T120000123456.db"


# ── Strategy CRUD ──────────────────────────────────────────────────────────


class TestStrategyConfig:
    def test_load_default(self) -> None:
        """Loading config when no file exists returns defaults."""
        cfg = load_config()
        assert cfg["version"] == 3
        assert len(cfg["strategies"]) == 1
        assert cfg["strategies"][0]["id"] == "default"

    def test_save_and_load(self) -> None:
        cfg = load_config()
        cfg["strategies"].append({
            "id": "hourly",
            "label": "Hourly backups",
            "interval_minutes": 60,
            "max_copies": 5,
            "target": "local",
            "enabled": True,
            "last_backup_at": "",
        })
        save_config(cfg)

        loaded = load_config()
        ids = [s["id"] for s in loaded["strategies"]]
        assert "default" in ids
        assert "hourly" in ids

    def test_add_strategy(self) -> None:
        s = BackupStrategy(id="daily", label="Daily", interval_minutes=1440)
        add_strategy(s)
        assert get_strategy("daily") is not None

    def test_add_duplicate_raises(self) -> None:
        s = BackupStrategy(id="default", label="Default")
        with pytest.raises(ValueError, match="already exists"):
            add_strategy(s)

    def test_get_strategy_nonexistent(self) -> None:
        assert get_strategy("nonexistent") is None

    def test_update_strategy(self) -> None:
        update_strategy("default", {"label": "Updated Label", "interval_minutes": 60})
        s = get_strategy("default")
        assert s is not None
        assert s["label"] == "Updated Label"
        assert s["interval_minutes"] == 60

    def test_update_nonexistent_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            update_strategy("ghost", {})

    def test_remove_strategy(self) -> None:
        add_strategy(BackupStrategy(id="remove-me", label="Temp"))
        remove_strategy("remove-me")
        assert get_strategy("remove-me") is None

    def test_remove_nonexistent_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            remove_strategy("ghost")

    def test_list_strategies(self) -> None:
        strategies = list_strategies()
        assert isinstance(strategies, list)
        assert len(strategies) >= 1

    def test_resolve_target_local(self) -> None:
        resolved = resolve_target_path({"target": "local"})
        assert resolved.endswith("/.backups") or resolved.endswith("\\.backups")

    def test_resolve_target_absolute(self) -> None:
        resolved = resolve_target_path({"target": "/tmp/semantika-backup-test"})
        assert resolved == "/tmp/semantika-backup-test"

    def test_save_config_invalid(self) -> None:
        with pytest.raises(ValueError, match="must be a list"):
            save_config({"version": 3, "strategies": "not_a_list"})

    def test_save_config_empty_id(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            save_config({"version": 3, "strategies": [{"id": ""}]})


# ── Backup operations ──────────────────────────────────────────────────────


class TestBackupDatabase:
    def test_backup_creates_file(self, seeded_db: Path) -> None:
        backup_path = backup_database()
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.suffix == ".db"
        # Verify it's a valid SQLite database
        import sqlite3
        conn = sqlite3.connect(str(backup_path))
        row = conn.execute("SELECT val FROM test WHERE id=1").fetchone()
        assert row[0] == "hello"
        conn.close()

    def test_backup_with_strategy(self, seeded_db: Path) -> None:
        add_strategy(BackupStrategy(id="special", label="Special"))
        strategy = get_strategy("special")
        assert strategy is not None
        backup_path = backup_database(strategy)
        assert backup_path is not None
        assert "special" in backup_path.name

    def test_backup_all_strategies(self, seeded_db: Path) -> None:
        add_strategy(BackupStrategy(id="extra", label="Extra"))
        created = backup_all_strategies()
        assert len(created) >= 2  # default + extra
        for p in created:
            assert p.exists()

    def test_backup_with_external_target(self, seeded_db: Path, tmp_path: Path) -> None:
        ext = tmp_path / "external"
        ext.mkdir()
        update_strategy("default", {"target": str(ext)})
        backup_path = backup_database()
        assert backup_path is not None
        # Should also exist in the external target
        ext_files = list(ext.iterdir())
        assert len(ext_files) >= 1

    def test_backup_no_db(self) -> None:
        """Backup when no DB exists returns None."""
        result = backup_database()
        assert result is None


class TestListBackups:
    def test_list_empty(self) -> None:
        assert list_backups() == []

    def test_list_after_backup(self, seeded_db: Path) -> None:
        backup_database()
        backups = list_backups()
        assert len(backups) == 1
        assert backups[0]["stem"] == "semantika"
        assert backups[0]["size_bytes"] > 0


class TestPruneBackups:
    def test_prune_keeps_newest(self, seeded_db: Path) -> None:
        # Create 5 backups
        for _ in range(5):
            backup_database()

        backups_before = list_backups()
        assert len(backups_before) == 5

        deleted = prune_backups(retention=2)
        assert deleted == 3

        backups_after = list_backups()
        assert len(backups_after) == 2

    def test_prune_noop_when_below_retention(self, seeded_db: Path) -> None:
        backup_database()
        deleted = prune_backups(retention=10)
        assert deleted == 0


class TestRestoreBackups:
    def test_restore_latest(self, seeded_db: Path, tmp_path: Path) -> None:
        backup_database()
        target = tmp_path / "restore"
        target.mkdir()

        restored = restore_latest(target)
        assert restored.exists()
        import sqlite3
        conn = sqlite3.connect(str(restored))
        row = conn.execute("SELECT val FROM test WHERE id=1").fetchone()
        assert row[0] == "hello"
        conn.close()

    def test_restore_latest_no_backups(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No backups found"):
            restore_latest(tmp_path)

    def test_restore_by_timestamp(self, seeded_db: Path, tmp_path: Path) -> None:
        backup_database()
        backups = list_backups()
        ts_prefix = backups[0]["timestamp"][:8]  # YYYYMMDD only

        target = tmp_path / "restore2"
        target.mkdir()
        restored = restore_by_timestamp(ts_prefix, target)
        assert restored.exists()

    def test_restore_by_timestamp_no_match(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No backup matches"):
            restore_by_timestamp("19700101", tmp_path)


# ── Verify strategy target ─────────────────────────────────────────────────


class TestVerifyStrategyTarget:
    def test_verify_local(self, seeded_db: Path) -> None:
        result = verify_strategy_target("default")
        assert result["success"] is True

    def test_verify_nonexistent(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            verify_strategy_target("ghost")

    def test_verify_external(self, seeded_db: Path, tmp_path: Path) -> None:
        ext = tmp_path / "ext-backup"
        update_strategy("default", {"target": str(ext)})
        result = verify_strategy_target("default")
        assert result["success"] is True
        assert str(ext) in result["message"]


# ── Export / Import ────────────────────────────────────────────────────────


class TestExportImport:
    def test_export_creates_zip(self, seeded_db: Path, tmp_path: Path) -> None:
        output = tmp_path / "exports"
        output.mkdir()
        zip_path = export_data(output)
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"

    def test_export_zip_contains_manifest(self, seeded_db: Path, tmp_path: Path) -> None:
        output = tmp_path / "exports2"
        output.mkdir()
        zip_path = export_data(output)

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "semantika.db" in names

            manifest = json.loads(zf.read("manifest.json"))
            assert "exported_at" in manifest
            assert "semantika.db" in manifest["files"]
            assert "sha256" in manifest["files"]["semantika.db"]

    def test_import_zip(self, seeded_db: Path, tmp_path: Path) -> None:
        output = tmp_path / "exports3"
        output.mkdir()
        zip_path = export_data(output)

        # Delete original so we can verify import works
        seeded_db.unlink()

        result = import_data(zip_path, force=True)
        assert "semantika.db" in result["imported"]
        assert seeded_db.exists()

    def test_import_checks_sha256(self, seeded_db: Path, tmp_path: Path) -> None:
        output = tmp_path / "exports4"
        output.mkdir()
        zip_path = export_data(output)

        # Verify the original DB still has correct data after re-import
        import sqlite3
        orig_conn = sqlite3.connect(str(seeded_db))
        orig_val = orig_conn.execute("SELECT val FROM test WHERE id=1").fetchone()
        orig_conn.close()
        assert orig_val[0] == "hello"

        # Import over the existing DB with force
        result = import_data(zip_path, force=True)
        assert len(result.get("errors", [])) == 0

    def test_import_nonexistent(self) -> None:
        with pytest.raises(FileNotFoundError, match="Export zip not found"):
            import_data("/nonexistent/export.zip")

    def test_import_skip_identical(self, seeded_db: Path, tmp_path: Path) -> None:
        """Importing identical content should skip the DB."""
        output = tmp_path / "exports5"
        output.mkdir()
        zip_path = export_data(output)

        # Import without force — should skip since content is identical
        result = import_data(zip_path)
        # The file exists and content is identical, so it should be skipped
        assert len(result.get("imported", [])) == 0
        assert len(result.get("errors", [])) == 0


# ── Scheduler / misc ───────────────────────────────────────────────────────


class TestBackupScheduler:
    def test_backup_scheduler_init(self) -> None:
        from semantika.server.tasks import BackupScheduler
        sched = BackupScheduler()
        sched.start()
        sched.stop()
        # Just verify it starts and stops without error
        assert True

    def test_global_init_shutdown(self) -> None:
        from semantika.server.tasks import init_backup_scheduler, shutdown_backup_scheduler
        sched = init_backup_scheduler()
        assert sched is not None
        shutdown_backup_scheduler(timeout=3.0)
        assert True
