"""Re-exported from lightercore -- see ``lightercore.backup``."""
from __future__ import annotations

from lightercore.backup import (  # noqa: F401
    BackupStrategy,
    add_strategy,
    backup_all_strategies,
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
    _backup_dir,
    _backup_filename,
    _config_path,
    _timestamp,
)

# Private helpers used by tests — not in __all__
from lightercore.paths import data_dir

# ── Semantika-specific helpers (not in lightercore) ─────────────────────


def _db_path() -> Path:
    """Return the path to the Semantika database file."""
    return data_dir() / "semantika.db"


def _parse_backup_filename(
    filename: str,
) -> dict[str, str] | None:
    """Parse a semantika backup filename into components.

    Supports new format: ``semantika_<strategy>_<timestamp>.db``
    and legacy format: ``semantika_<timestamp>.db``.
    """
    import re
    m = re.match(r"^(.+?)_(.+?)_(\d{8}T\d+)\.(db|bak)$", filename)
    if m:
        return {"stem": m.group(1), "strategy": m.group(2),
                "timestamp": m.group(3), "suffix": m.group(4)}
    m = re.match(r"^(.+?)_(\d{8}T\d+)\.(db|bak)$", filename)
    if m:
        return {"stem": m.group(1), "strategy": "legacy",
                "timestamp": m.group(2), "suffix": m.group(3)}
    return None
