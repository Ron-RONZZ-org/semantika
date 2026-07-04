"""Tests for server/tasks.py — BackupScheduler, init/shutdown."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestBackupScheduler:
    """Test BackupScheduler start/stop and run loop."""

    def test_start_stop(self) -> None:
        from semantika.server.tasks import BackupScheduler

        scheduler = BackupScheduler()
        scheduler.start()

        # Should have a running thread
        assert scheduler._thread is not None
        assert scheduler._thread.is_alive()

        scheduler.stop(timeout=2.0)
        assert scheduler._thread is not None
        assert not scheduler._thread.is_alive()

    def test_start_twice_is_noop(self) -> None:
        from semantika.server.tasks import BackupScheduler

        scheduler = BackupScheduler()
        scheduler.start()
        thread_id = id(scheduler._thread)

        scheduler.start()  # second start
        assert id(scheduler._thread) == thread_id

        scheduler.stop()

    def test_stop_no_thread(self) -> None:
        from semantika.server.tasks import BackupScheduler

        scheduler = BackupScheduler()
        # Should not raise
        scheduler.stop()


class TestBackupSchedulerCheckAndBackup:
    """Test _check_and_backup_if_due logic in isolation."""

    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.backup_all_strategies")
    @patch("semantika.core.backup.save_config")
    def test_no_strategies(
        self,
        mock_save: pytest.MagicMock,
        mock_backup: pytest.MagicMock,
        mock_cfg: pytest.MagicMock,
    ) -> None:
        from semantika.server.tasks import BackupScheduler

        mock_cfg.return_value = {"strategies": []}
        # Should not raise, no-op
        BackupScheduler._check_and_backup_if_due()
        mock_backup.assert_not_called()

    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.backup_all_strategies")
    @patch("semantika.core.backup.save_config")
    def test_disabled_strategy_skipped(
        self,
        mock_save: pytest.MagicMock,
        mock_backup: pytest.MagicMock,
        mock_cfg: pytest.MagicMock,
    ) -> None:
        from semantika.server.tasks import BackupScheduler

        mock_cfg.return_value = {
            "strategies": [
                {"id": "daily", "enabled": False, "interval_minutes": 1440},
            ]
        }
        BackupScheduler._check_and_backup_if_due()
        mock_backup.assert_not_called()

    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.backup_all_strategies")
    @patch("semantika.core.backup.save_config")
    def test_on_demand_strategy_skipped(
        self,
        mock_save: pytest.MagicMock,
        mock_backup: pytest.MagicMock,
        mock_cfg: pytest.MagicMock,
    ) -> None:
        from semantika.server.tasks import BackupScheduler

        mock_cfg.return_value = {
            "strategies": [
                {"id": "ondemand", "enabled": True, "interval_minutes": 0},
            ]
        }
        BackupScheduler._check_and_backup_if_due()
        mock_backup.assert_not_called()

    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.backup_all_strategies")
    @patch("semantika.core.backup.save_config")
    def test_strategy_overdue_runs_backup(
        self,
        mock_save: pytest.MagicMock,
        mock_backup: pytest.MagicMock,
        mock_cfg: pytest.MagicMock,
    ) -> None:
        from semantika.server.tasks import BackupScheduler

        mock_cfg.return_value = {
            "strategies": [
                {
                    "id": "daily",
                    "enabled": True,
                    "interval_minutes": 1440,
                    "last_backup_at": "20200101T000000",
                },
            ]
        }
        BackupScheduler._check_and_backup_if_due()
        mock_backup.assert_called_once()

    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.backup_all_strategies")
    @patch("semantika.core.backup.save_config")
    def test_strategy_recently_backed_up_skipped(
        self,
        mock_save: pytest.MagicMock,
        mock_backup: pytest.MagicMock,
        mock_cfg: pytest.MagicMock,
    ) -> None:
        from semantika.server.tasks import BackupScheduler
        from datetime import datetime, timezone, timedelta

        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        mock_cfg.return_value = {
            "strategies": [
                {
                    "id": "daily",
                    "enabled": True,
                    "interval_minutes": 1440,
                    "last_backup_at": recent,
                },
            ]
        }
        BackupScheduler._check_and_backup_if_due()
        mock_backup.assert_not_called()

    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.backup_all_strategies")
    @patch("semantika.core.backup.save_config")
    def test_strategy_bad_timestamp(
        self,
        mock_save: pytest.MagicMock,
        mock_backup: pytest.MagicMock,
        mock_cfg: pytest.MagicMock,
    ) -> None:
        from semantika.server.tasks import BackupScheduler

        mock_cfg.return_value = {
            "strategies": [
                {
                    "id": "daily",
                    "enabled": True,
                    "interval_minutes": 1440,
                    "last_backup_at": "not-a-timestamp",
                },
            ]
        }
        # Bad timestamp should treat as overdue
        BackupScheduler._check_and_backup_if_due()
        mock_backup.assert_called_once()

    @patch("semantika.core.backup.load_config")
    @patch("semantika.core.backup.backup_all_strategies")
    @patch("semantika.core.backup.save_config")
    def test_check_error_handled(
        self,
        mock_save: pytest.MagicMock,
        mock_backup: pytest.MagicMock,
        mock_cfg: pytest.MagicMock,
    ) -> None:
        from semantika.server.tasks import BackupScheduler

        # load_config raises — should be caught
        mock_cfg.side_effect = RuntimeError("Config corrupted")
        # Should not propagate
        BackupScheduler._check_and_backup_if_due()
        mock_backup.assert_not_called()


class TestBackupSchedulerSingletons:
    """Test init_backup_scheduler and shutdown_backup_scheduler."""

    def setup_method(self) -> None:
        # Reset the global _scheduler
        from semantika.server import tasks

        tasks._scheduler = None

    def test_init(self) -> None:
        from semantika.server.tasks import init_backup_scheduler, shutdown_backup_scheduler

        sched = init_backup_scheduler()
        assert sched is not None
        assert sched._thread is not None
        assert sched._thread.is_alive()

        shutdown_backup_scheduler()

    def test_init_twice_returns_same(self) -> None:
        from semantika.server.tasks import init_backup_scheduler, shutdown_backup_scheduler, _scheduler

        s1 = init_backup_scheduler()
        s2 = init_backup_scheduler()
        assert s1 is s2

        shutdown_backup_scheduler()

    def test_shutdown_noop(self) -> None:
        from semantika.server.tasks import shutdown_backup_scheduler

        # No scheduler running — should not raise
        shutdown_backup_scheduler()
