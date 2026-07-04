"""Background task scheduler — backup worker.

Provides a simple daemon thread that periodically checks for overdue
backup strategies and runs backups automatically.

Started/stopped by ``server/app.py`` lifespan events.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Backup scheduler ─────────────────────────────────────────────────────


class BackupScheduler:
    """Background worker that runs scheduled backups per strategy.

    On startup, checks if any strategy with a positive interval is overdue
    and runs it immediately. Then checks every 60 seconds.

    Usage::

        scheduler = BackupScheduler()
        scheduler.start()
        # ... app runs ...
        scheduler.stop()

    Thread is daemon — it exits when the main process exits.
    """

    CHECK_INTERVAL = 60  # seconds between scheduler checks

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the scheduler daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="backup-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("[backup] Backup scheduler started")

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the scheduler to stop and wait for it.

        Args:
            timeout: Max seconds to wait for the thread to finish.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            logger.info("[backup] Backup scheduler stopped")

    def _run(self) -> None:
        """Main loop: immediate check, then periodic checks."""
        logger.info("[backup] Worker loop started")

        # On startup, run an immediate check for overdue strategies
        self._check_and_backup_if_due()

        while not self._stop_event.is_set():
            try:
                self._check_and_backup_if_due()
            except Exception as exc:
                logger.error(
                    "[backup] Backup check failed: %s", exc, exc_info=True
                )
            # Sleep in short intervals so we can react to stop signal
            self._stop_event.wait(self.CHECK_INTERVAL)

        logger.info("[backup] Worker loop exited")

    @staticmethod
    def _check_and_backup_if_due() -> None:
        """Check all strategies and run backups for those that are due."""
        try:
            from semantika.core.backup import (
                backup_all_strategies,
                load_config,
                save_config,
            )

            cfg = load_config()
            strategies = cfg.get("strategies", [])
            now = datetime.now(timezone.utc)
            triggered: list[str] = []

            for s in strategies:
                interval = s.get("interval_minutes", 0)
                if interval <= 0:
                    continue
                if not s.get("enabled", True):
                    continue

                last_raw = s.get("last_backup_at", "")
                if last_raw:
                    try:
                        last_dt = datetime.fromisoformat(last_raw)
                        elapsed = (now - last_dt).total_seconds() / 60.0
                    except (ValueError, TypeError):
                        elapsed = float("inf")
                else:
                    elapsed = float("inf")

                if elapsed >= interval:
                    logger.info(
                        "[backup] Strategy '%s' is due (%.1f min elapsed, interval %d min)",
                        s["id"], elapsed, interval,
                    )
                    triggered.append(s["id"])

            if triggered:
                logger.info("[backup] Running scheduled backup for: %s", triggered)
                backup_all_strategies()
                # Update last_backup_at for triggered strategies
                now_iso = now.isoformat()
                for s in cfg["strategies"]:
                    if s["id"] in triggered:
                        s["last_backup_at"] = now_iso
                save_config(cfg)
                logger.info("[backup] Scheduled backup complete for: %s", triggered)
        except Exception as exc:
            logger.error("[backup] Scheduler check error: %s", exc, exc_info=True)


# ── Global singleton ──────────────────────────────────────────────────────

_scheduler: BackupScheduler | None = None


def init_backup_scheduler() -> BackupScheduler:
    """Initialize and start the global backup scheduler.

    Called from ``server/app.py`` on startup.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackupScheduler()
    _scheduler.start()
    return _scheduler


def shutdown_backup_scheduler(timeout: float = 5.0) -> None:
    """Stop the global backup scheduler.

    Called from ``server/app.py`` on shutdown.
    """
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop(timeout=timeout)
        _scheduler = None


__all__ = [
    "BackupScheduler",
    "init_backup_scheduler",
    "shutdown_backup_scheduler",
]
