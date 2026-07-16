"""Semantika global configuration — reads ``~/.config/semantika/semantika.jsonc``.

Provides:
- ``get_config()`` — cached dict of parsed config values
- ``reload_config()`` — clear cache so next ``get_config()`` re-reads the file
- ``get_iri_template(kind)`` — convenience for ``node_iri`` / ``predicate_iri``

File format (JSONC — JSON with ``//`` line comments):

.. code-block:: jsonc

    {
        // IRI templates — $id is replaced with the entity's internal ID
        "node_iri": "https://sm.ronzz.org/nodes/$id",
        "predicate_iri": "https://sm.ronzz.org/predicates/$id"
    }

The config file is optional.  If it does not exist, built-in defaults are used.
"""

from __future__ import annotations

import logging
from pathlib import Path

from semantika.core import config_dir, ensure_dirs

logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────────

DEFAULT_NODE_IRI = "https://sm.ronzz.org/nodes/$id"
DEFAULT_PREDICATE_IRI = "https://sm.ronzz.org/predicates/$id"

_CONFIG_FILENAMES = ("semantika.jsonc", "semantika.json")

# ── Cache ───────────────────────────────────────────────────────────────

_config_cache: dict | None = None
_config_path: Path | None = None


def get_config() -> dict:
    """Return the parsed config dict, loading from disk on first call.

    Results are cached in memory for the lifetime of the process.  Call
    :func:`reload_config` to re-read the file (e.g. after a template change).
    """
    global _config_cache, _config_path
    if _config_cache is not None:
        return _config_cache

    ensure_dirs()
    cfg_dir = config_dir()
    path: Path | None = None
    for name in _CONFIG_FILENAMES:
        candidate = cfg_dir / name
        if candidate.exists():
            path = candidate
            break

    if path is None:
        _config_cache = {}
        _config_path = None
        logger.debug("No semantika.jsonc found — using built-in defaults")
        return _config_cache

    try:
        import commentjson

        raw = commentjson.loads(path.read_text(encoding="utf-8"))
        _config_cache = raw if isinstance(raw, dict) else {}
        _config_path = path
        logger.info("Loaded config from %s", path)
    except Exception as exc:
        logger.warning("Failed to parse %s: %s — using defaults", path, exc)
        _config_cache = {}

    return _config_cache


def reload_config() -> dict:
    """Clear the in-memory cache and re-read the config file."""
    global _config_cache, _config_path
    _config_cache = None
    _config_path = None
    return get_config()


def get_iri_template(kind: str) -> str:
    """Return the IRI template string for *kind* (``"node"`` or ``"predicate"``).

    Falls back to the built-in default if the config key is missing.
    """
    key = f"{kind}_iri"
    cfg = get_config()
    return cfg.get(key, DEFAULT_NODE_IRI if kind == "node" else DEFAULT_PREDICATE_IRI)
