"""Re-exported from lightercore -- see ``lightercore.backup``.

Keeps backward-compatible aliases for semantika-specific internal APIs.
"""
from lightercore.backup import *  # noqa: F401, F403

from lightercore.backup import (  # noqa: F401
    BackupStrategy,
    get_strategy,
    prune_backups as prune_backups_alias,
    resolve_target_path,
)
