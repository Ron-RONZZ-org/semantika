"""Reset-to-fresh-state: backup (optional), then purge all data & credentials.

This is the dangerous "nuclear option" — invoked by ``!reset``.
"""

from __future__ import annotations

import logging
import shutil

from lightercore.paths import data_dir

from semantika.core.backup import _db_path

logger = logging.getLogger(__name__)


# Mutable set of known credential service names.  Other modules can
# register additional services via :func:`register_credential_service`.
_KNOWN_CREDENTIAL_SERVICES: set[str] = {"semantika-llm", "semantika-key"}


def register_credential_service(service_name: str) -> None:
    """Register a credential service name so ``!reset`` clears it.

    Call this from any module that stores credentials in the system
    keyring under a ``semantika-*`` service name.
    """
    _KNOWN_CREDENTIAL_SERVICES.add(service_name)


def _discover_semantika_credentials() -> set[str]:
    """Attempt to discover ``semantika-*`` credential services dynamically.

    Uses the active keyring backend's ``list_credential_services()`` method
    if available (some backends support this).  Falls back to the statically
    registered service names otherwise.
    """
    discovered: set[str] = set()
    try:
        import keyring as _kr
        backend = _kr.get_keyring()
        # Some backends (e.g. SecretService DBus) support listing
        list_method = getattr(backend, "list_credential_services", None)
        if list_method is not None:
            try:
                for svc in list_method():
                    if isinstance(svc, str) and svc.startswith("semantika-"):
                        discovered.add(svc)
            except Exception:
                logger.debug("Keyring list_credential_services failed", exc_info=True)
    except Exception:
        logger.debug("Could not access keyring for credential discovery", exc_info=True)
    return discovered


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

    # 4. Clear keyring credentials — dynamically discovered + known list
    services_to_clear = _KNOWN_CREDENTIAL_SERVICES | _discover_semantika_credentials()
    try:
        import keyring as _kr
    except ImportError:
        logger.debug("keyring not available — skipping credential cleanup")
    else:
        for service in services_to_clear:
            try:
                _kr.delete_password(service, "api_key")
                result["credentials_cleared"] += 1
            except _kr.errors.PasswordDeleteError:
                pass
            except Exception:
                logger.exception("Could not clear keyring %s", service)

    return result
