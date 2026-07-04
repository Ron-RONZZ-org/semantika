"""XDG-compliant path resolution for Semantika.

Supports ``SEMANTIKA_DIR`` environment variable override.
Vendored from A-core's ``A.core.paths``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_SEMANTIKA_DIR_ENV = "SEMANTIKA_DIR"
_SENTINEL_NAME = ".semantika-protected"


def _base() -> Path | None:
    """Return the base directory from ``SEMANTIKA_DIR`` env var, or None."""
    val = os.environ.get(_SEMANTIKA_DIR_ENV, "").strip()
    if not val:
        return None
    return Path(val).resolve()


def data_dir() -> Path:
    """Return the Semantika data directory.

    Default: ``~/.local/share/semantika``
    Override: ``SEMANTIKA_DIR`` → ``$SEMANTIKA_DIR/data``
    Also: ``SEMANTIKA_DATA_DIR`` env var.
    """
    override = os.environ.get("SEMANTIKA_DATA_DIR")
    if override:
        return Path(override)
    base = _base()
    if base is not None:
        return base / "data"
    return Path.home() / ".local" / "share" / "semantika"


def config_dir() -> Path:
    """Return the Semantika config directory.

    Default: ``~/.config/semantika``
    """
    override = os.environ.get("SEMANTIKA_CONFIG_DIR")
    if override:
        return Path(override)
    base = _base()
    if base is not None:
        return base / "config"
    return Path.home() / ".config" / "semantika"


def cache_dir() -> Path:
    """Return the Semantika cache directory.

    Default: ``~/.cache/semantika``
    """
    override = os.environ.get("SEMANTIKA_CACHE_DIR")
    if override:
        return Path(override)
    base = _base()
    if base is not None:
        return base / "cache"
    return Path.home() / ".cache" / "semantika"


def state_dir() -> Path:
    """Return the Semantika state directory.

    Default: ``~/.local/state/semantika``
    """
    override = os.environ.get("SEMANTIKA_STATE_DIR")
    if override:
        return Path(override)
    base = _base()
    if base is not None:
        return base / "state"
    return Path.home() / ".local" / "state" / "semantika"


def ensure_dirs() -> None:
    """Ensure all Semantika directories exist and are protected."""
    for d in [data_dir(), config_dir(), cache_dir(), state_dir()]:
        d.mkdir(parents=True, exist_ok=True)
        _protect_directory(d)


def _protect_directory(path: Path) -> Path:
    """Create a sentinel marker in *path*. Idempotent."""
    path.mkdir(parents=True, exist_ok=True)
    sentinel = path / _SENTINEL_NAME
    sentinel.touch(exist_ok=True)
    return path


def is_protected(path: Path) -> bool:
    """Check if *path* or any ancestor is protected."""
    for parent in [path, *path.parents]:
        if (parent / _SENTINEL_NAME).exists():
            return True
    return False


def safe_rmtree(path: Path, *, force: bool = False) -> None:
    """Remove a directory tree, refusing if protected."""
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not force and is_protected(path):
        from semantika.core.exceptions import ProtectedPathError
        raise ProtectedPathError(path, "delete")
    shutil.rmtree(path)
