"""Core utilities — vendored from A-core.

Provides database connection management, XDG path resolution,
CRUD service base, FTS5 configuration, and custom exceptions.
"""

from semantika.core.db import SemantikaDB
from semantika.core.paths import config_dir, data_dir, ensure_dirs
from semantika.core.exceptions import (
    AmbiguousIDError,
    ProtectedPathError,
    SemantikaError,
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
