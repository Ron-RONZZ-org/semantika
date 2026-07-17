"""YAML-based seed data loader with Python fallback.

Loads ontology seed data from YAML files.  The lookup order is:
  1. User-editable YAML in the config directory
     (``~/.config/semantika/builtins.yaml``, ``~/.config/semantika/units.yaml``)
  2. Shipped default YAML bundled with the package
     (``src/semantika/graph/builtins.yaml``, ``src/semantika/graph/units.yaml``)

Required predicates (those referenced by built-in command handlers) have a
Python fallback in :mod:`_required_predicates`.  If a required predicate
is missing from the YAML, a warning is logged and the Python fallback is used.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from semantika.graph._required_predicates import REQUIRED_PREDICATES, REQUIRED_PREDICATE_IDS

logger = logging.getLogger(__name__)

# ── Shipped default paths ──────────────────────────────────────────────
# These are relative to this module file.

_PACKAGE_DIR = Path(__file__).resolve().parent
_SHIPPED_BUILTINS = _PACKAGE_DIR / "builtins.yaml"
_SHIPPED_UNITS = _PACKAGE_DIR / "units.yaml"

# ── Config dir paths ──────────────────────────────────────────────────
# These are where user edits live.

_CONFIG_BUILTINS_NAME = "builtins.yaml"
_CONFIG_UNITS_NAME = "units.yaml"


# ── YAML loading ──────────────────────────────────────────────────────


def _get_config_dir() -> Path:
    """Return the Semantika config directory (``~/.config/semantika/``)."""
    from lightercore.paths import config_dir
    return config_dir()


def _load_yaml_file(path: Path, label: str) -> dict[str, Any] | None:
    """Load a YAML file and return its parsed content.

    Args:
        path: Path to the YAML file.
        label: Human-readable label for log messages.

    Returns:
        Parsed dict, or ``None`` if the file does not exist or is unparseable.
    """
    if not path.exists():
        logger.debug("YAML file not found: %s (%s)", path, label)
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            logger.warning("YAML file %s (%s) did not produce a dict", path, label)
            return None
        return data
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse YAML file %s (%s): %s", path, label, exc)
        return None


def load_builtins_yaml() -> dict[str, Any]:
    """Load the builtins seed data (predicates + type nodes).

    Resolution order:
      1. User-editable ``~/.config/semantika/builtins.yaml``
      2. Shipped ``builtins.yaml`` in the package

    Returns:
        A dict with keys ``predicates`` (list) and ``type_nodes`` (list),
        or an empty dict if neither file is available.
    """
    # 1. User config dir
    config_path = _get_config_dir() / _CONFIG_BUILTINS_NAME
    data = _load_yaml_file(config_path, "config")
    if data is not None:
        return data

    # 2. Shipped default
    data = _load_yaml_file(_SHIPPED_BUILTINS, "shipped")
    if data is not None:
        return data

    logger.error("No builtins.yaml found — neither config dir nor shipped default")
    return {}


def load_units_yaml() -> dict[str, Any]:
    """Load the unit ontology seed data.

    Resolution order:
      1. User-editable ``~/.config/semantika/units.yaml``
      2. Shipped ``units.yaml`` in the package

    Returns:
        A dict with keys ``unit_types``, ``base_units``, ``derived_units``,
        ``prefixes`` (each a list), or an empty dict if neither file is
        available.
    """
    # 1. User config dir
    config_path = _get_config_dir() / _CONFIG_UNITS_NAME
    data = _load_yaml_file(config_path, "config")
    if data is not None:
        return data

    # 2. Shipped default
    data = _load_yaml_file(_SHIPPED_UNITS, "shipped")
    if data is not None:
        return data

    logger.error("No units.yaml found — neither config dir nor shipped default")
    return {}


# ── Combined predicate catalog from YAML ───────────────────────────────


def _predicates_from_yaml(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract a predicate_id → entry dict from loaded YAML data.

    Args:
        data: Parsed ``builtins.yaml`` content.

    Returns:
        Dict mapping predicate_id to its seed entry (including ``tier``).
    """
    result: dict[str, dict[str, Any]] = {}
    for entry in data.get("predicates", []):
        pid = entry.get("id", "")
        if pid:
            result[pid] = entry
    return result


# ── Tier normalisation ─────────────────────────────────────────────────


def _normalize_tier(raw: str | int | None) -> str:
    """Normalise a YAML tier value to a string.

    YAML may parse ``tier: 1`` as an integer — this function converts
    it to the canonical string form (``"1"``, ``"2"``, ``"w3c"``,
    ``"file"``).
    """
    if raw is None:
        return "2"
    if isinstance(raw, int):
        return str(raw)
    return raw


# ── Cached predicate catalog ───────────────────────────────────────────
#
# We cache the predicate catalog and the core ID set so that frequent
# calls to ``is_core_predicate()`` don't re-parse the YAML every time.
# Caches are invalidated when the YAML file timestamp changes (via
# :func:`invalidate_caches`).

_predicate_catalog_cache: dict[str, dict[str, Any]] | None = None
_core_ids_cache: frozenset[str] | None = None


def invalidate_caches() -> None:
    """Clear cached predicate catalog and core ID set.

    Call after reloading the YAML files so the next access re-reads
    from disk.
    """
    global _predicate_catalog_cache, _core_ids_cache
    _predicate_catalog_cache = None
    _core_ids_cache = None


def get_predicate_catalog() -> dict[str, dict[str, Any]]:
    """Return the full predicate catalog merging YAML + Python fallback.

    For each required predicate (in :data:`REQUIRED_PREDICATE_IDS`):
      - If present in YAML → use YAML's labels/descriptions
      - If missing from YAML → use the Python fallback and log a warning

    Non-required predicates come from YAML only.

    Returns:
        Dict mapping predicate_id → seed entry dict with keys:
        ``id``, ``tier``, ``source``, ``labels``, ``descriptions``.
    """
    global _predicate_catalog_cache
    if _predicate_catalog_cache is not None:
        return _predicate_catalog_cache

    yaml_data = load_builtins_yaml()
    yaml_preds = _predicates_from_yaml(yaml_data)

    catalog: dict[str, dict[str, Any]] = {}

    # 1. All YAML predicates (includes tier info)
    for pid, entry in yaml_preds.items():
        catalog[pid] = {
            "id": pid,
            "tier": _normalize_tier(entry.get("tier", "2")),
            "source": entry.get("source", "manual"),
            "labels": entry.get("labels", {}),
            "descriptions": entry.get("descriptions", {}),
        }

    # 2. Required predicates: ensure present; warn + fallback if missing
    for pid in REQUIRED_PREDICATE_IDS:
        if pid in catalog:
            continue
        fallback = REQUIRED_PREDICATES.get(pid)
        if fallback is not None:
            logger.warning(
                "Required predicate '%s' is missing from builtins.yaml — "
                "using Python fallback.  Check your builtins.yaml for accidental deletion.",
                pid,
            )
            catalog[pid] = {
                "id": pid,
                "tier": _normalize_tier("1"),  # Required predicates default to Tier 1 protection
                "source": fallback.get("source", "manual"),
                "labels": fallback.get("labels", {}),
                "descriptions": fallback.get("descriptions", {}),
            }
        else:
            logger.warning(
                "Required predicate '%s' is missing from both builtins.yaml "
                "and the Python fallback — skipping.",
                pid,
            )

    _predicate_catalog_cache = catalog
    return catalog


def get_core_predicate_ids() -> frozenset[str]:
    """Return the set of core (soft-protected) predicate IDs.

    These are derived from the YAML ``tier`` field: entries with
    ``tier: 1`` or ``tier: w3c`` are considered core.

    The result is cached; call :func:`invalidate_caches` to clear
    after YAML reload.
    """
    global _core_ids_cache
    if _core_ids_cache is not None:
        return _core_ids_cache

    catalog = get_predicate_catalog()
    core: set[str] = set()
    for pid, entry in catalog.items():
        tier = entry.get("tier", "2")
        # Only Tier 1 predicates are core/soft-protected.
        # W3C predicates (rdf:, rdfs:, owl:) have tier "w3c" and are NOT
        # soft-protected — users may delete/recreate them freely.
        if tier == "1":
            core.add(pid)
    result = frozenset(core)
    _core_ids_cache = result
    return result


def get_type_nodes_from_yaml() -> list[dict[str, Any]]:
    """Return the list of built-in type nodes from YAML.

    Returns:
        List of dicts with keys ``id``, ``labels``, ``definitions``.
        Returns an empty list if the YAML file is unavailable.
    """
    data = load_builtins_yaml()
    return data.get("type_nodes", [])


# ── Unit data from YAML ────────────────────────────────────────────────


def get_unit_data() -> dict[str, list[dict[str, Any]]]:
    """Return all unit ontology data from YAML.

    Returns:
        Dict with keys ``unit_types``, ``base_units``, ``derived_units``,
        ``prefixes``, each a list of dicts.
    """
    data = load_units_yaml()
    return {
        "unit_types": data.get("unit_types", []),
        "base_units": data.get("base_units", []),
        "derived_units": data.get("derived_units", []),
        "prefixes": data.get("prefixes", []),
    }
