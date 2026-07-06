"""User configuration persistence -- locale, preferences, etc.

Stored as a JSON file in the semantika data directory.

Uses atomic write pattern (write to temp, rename) to prevent corruption
from concurrent writes or partial writes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from semantika.core import data_dir


def _config_path() -> Path:
    """Return the path to the user config JSON file."""
    return data_dir() / "user_config.json"


def load_config() -> dict[str, str]:
    """Load user config from JSON file. Returns empty dict if missing."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(cfg: dict[str, str]) -> None:
    """Save user config to JSON file (atomic write via temp+rename)."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp",
        prefix="user_config_",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_locale() -> str:
    """Return the stored locale code, defaulting to 'en'."""
    cfg = load_config()
    return cfg.get("locale", "en")


def set_locale(code: str) -> None:
    """Set the locale code."""
    cfg = load_config()
    cfg["locale"] = code
    save_config(cfg)
