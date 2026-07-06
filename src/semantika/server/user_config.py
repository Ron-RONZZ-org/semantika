"""User configuration persistence -- locale, preferences, etc.

Stored as a JSON file in the semantika data directory.
"""

from __future__ import annotations

import json
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
    """Save user config to JSON file."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def get_locale() -> str:
    """Return the stored locale code, defaulting to 'en'."""
    cfg = load_config()
    return cfg.get("locale", "en")


def set_locale(code: str) -> None:
    """Set the locale code."""
    cfg = load_config()
    cfg["locale"] = code
    save_config(cfg)
