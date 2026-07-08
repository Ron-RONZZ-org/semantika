"""Reset-to-fresh-state: backup (optional), then purge all data & credentials.

This is the dangerous "nuclear option" — invoked by ``!reset``.
"""

from __future__ import annotations

import logging
import shutil

from lightercore.paths import data_dir

from semantika.core.backup import _db_path

logger = logging.getLogger(__name__)


# When adding a new keyring service name, add it here so reset clears it.
_KNOWN_CREDENTIAL_SERVICES: tuple[str, ...] = ("semantika-llm", "semantika-key")


def reset_to_fresh_state(
    backup_path: str | None = None,
) -> dict:
    """Reset Semantika to a fresh state.

    If *backup_path* is provided, the current database is copied there
    before deletion.  All SQLite databases, file attachments, and
    keyring credentials are removed.

    Returns a summary dict with keys:
      - ``backup_path`` (str | None) — where the backup was saved
      - ``databases_removed`` (list[str]) — paths of removed databases
      - ``credentials_cleared`` (int) — number of credentials removed
    """
    from pathlib import Path

    ddir = data_dir()
    db_path = _db_path()

    result: dict = {
        "backup_path": None,
        "databases_removed": [],
        "credentials_cleared": 0,
    }

    # 1. Backup if requested (simple file copy — no strategy tracking)
    if backup_path:
        dest = Path(backup_path)
        if db_path.exists():
            shutil.copy2(str(db_path), str(dest))
        result["backup_path"] = str(dest.resolve())

    # 2. Remove SQLite databases
    for db_file in ddir.glob("*.db*"):
        try:
            db_file.unlink()
            result["databases_removed"].append(str(db_file))
        except OSError as exc:
            logger.warning("Could not remove database %s: %s", db_file, exc)

    # 3. Remove file attachments
    files_dir = ddir / "semantika" / "files"
    if files_dir.exists():
        try:
            shutil.rmtree(files_dir)
        except OSError as exc:
            logger.warning("Could not remove files dir %s: %s", files_dir, exc)

    # 4. Clear keyring credentials
    try:
        import keyring as _kr
    except ImportError:
        logger.debug("keyring not available — skipping credential cleanup")
    else:
        # Central list of known credential services.  When adding a new
        # service name, add it here so ``reset`` clears it too.
        for service in _KNOWN_CREDENTIAL_SERVICES:
            try:
                _kr.delete_password(service, "api_key")
                result["credentials_cleared"] += 1
            except _kr.errors.PasswordDeleteError:
                pass
            except Exception:
                logger.exception("Could not clear keyring %s", service)

    return result
