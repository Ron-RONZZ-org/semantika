"""Core utilities — re-exported from lightercore where possible.

``lightercore`` is the canonical source for DB, paths, exceptions, CRUD,
and backup.  FTS5 config remains local.
"""

from lightercore.db import LighterbirdDB as SemantikaDB
from lightercore.paths import config_dir, data_dir, ensure_dirs
from lightercore.exceptions import (
    AmbiguousIDError,
    ProtectedPathError,
    LighterbirdError as SemantikaError,
)

__all__ = [
    "SemantikaDB",
    "config_dir",
    "data_dir",
    "ensure_dirs",
    "AmbiguousIDError",
    "ProtectedPathError",
    "SemantikaError",
]
