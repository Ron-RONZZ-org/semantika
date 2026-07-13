"""Core utilities — re-exported from lightercore where possible.

``lightercore`` is the canonical source for DB, paths, exceptions, CRUD,
and backup.  FTS5 config remains local.
"""

from lightercore import set_app_name
from lightercore.db import LighterbirdDB as SemantikaDB
from lightercore.exceptions import (
    AmbiguousIDError,
    ProtectedPathError,
)
from lightercore.exceptions import (
    LighterbirdError as SemantikaError,
)
from lightercore.paths import config_dir, data_dir, ensure_dirs

from semantika.core.config import get_config, get_iri_template, reload_config

# Ensure semantika uses its own path namespace, not lighterbird's default
set_app_name("semantika")

__all__ = [
    "AmbiguousIDError",
    "ProtectedPathError",
    "SemantikaDB",
    "SemantikaError",
    "config_dir",
    "data_dir",
    "ensure_dirs",
    "get_config",
    "get_iri_template",
    "reload_config",
]
