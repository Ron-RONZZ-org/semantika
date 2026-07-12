"""Shared helper functions for graph services.

Ported from A-semantika's ``_node_helpers.py`` with EO→EN rename.
"""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)


def extract_label_text(labels: str | dict) -> str:
    """Denormalize labels JSON into a flat searchable string."""
    try:
        parsed = json.loads(labels) if isinstance(labels, str) else labels
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    return " ".join(str(v) for v in parsed.values() if v)


def extract_definition_text(definitions: str | dict) -> str:
    """Denormalize definitions JSON into a flat searchable string."""
    try:
        parsed = json.loads(definitions) if isinstance(definitions, str) else definitions
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    return " ".join(str(v) for v in parsed.values() if v)


def get_label_from_node(node: dict, preferred_lang: str | None = None) -> str:
    """Extract display label from a pre-resolved node dict.

    Resolution priority:
    1. ``preferred_lang`` language (if given)
    2. First defined language (any order)
    3. ``node_id[:16]``
    """
    labels_raw = node.get("labels", "{}")
    try:
        labels = json.loads(labels_raw) if isinstance(labels_raw, str) else labels_raw
    except (json.JSONDecodeError, TypeError):
        return _truncate_id(node.get("node_id", ""))

    if not isinstance(labels, dict):
        return _truncate_id(node.get("node_id", ""))

    if preferred_lang and preferred_lang in labels and labels[preferred_lang]:
        return labels[preferred_lang]

    for val in labels.values():
        if val and isinstance(val, str):
            return val
    return _truncate_id(node.get("node_id", ""))


# ── Wikidata helpers ──────────────────────────────────────────────────────

_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_WIKIDATA_ENTITY_API = "https://www.wikidata.org/wiki/Special:EntityData"


def search_wikidata(query: str, lang: str = "en", limit: int = 5) -> list[dict]:
    """Search Wikidata entities by label.

    Args:
        query: Search string.
        lang: Language code for results.
        limit: Max results.

    Returns:
        List of dicts with ``predicate_id`` (Q-ID), ``label``, and
        ``description`` keys.
    """
    try:
        resp = httpx.get(
            _WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": query,
                "language": lang,
                "format": "json",
                "limit": min(limit, 50),
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[dict] = []
        for item in data.get("search", []):
            results.append({
                "predicate_id": item["id"],
                "label": item.get("label", item["id"]),
                "description": item.get("description", ""),
            })
        return results
    except Exception as exc:
        logger.debug("Wikidata search failed for %r: %s", query, exc)
        return []


def fetch_wikidata_details(entity_id: str, lang: str = "en") -> dict | None:
    """Fetch labels and descriptions for a Wikidata entity.

    Args:
        entity_id: Wikidata Q-ID (e.g. ``Q42``).
        lang: Language code.

    Returns:
        Dict with ``labels`` and ``descriptions`` (each a ``{lang: text}``
        mapping), or ``None`` if the entity cannot be resolved.
    """
    if not entity_id.startswith(("Q", "P")):
        return None
    try:
        url = f"{_WIKIDATA_ENTITY_API}/{entity_id}.json"
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        entities = data.get("entities", {})
        entity = entities.get(entity_id)
        if not entity:
            return None

        labels_raw = entity.get("labels", {})
        descriptions_raw = entity.get("descriptions", {})

        labels = {k: v.get("value", "") for k, v in labels_raw.items() if v.get("value")}
        descriptions = {k: v.get("value", "") for k, v in descriptions_raw.items() if v.get("value")}

        return {"labels": labels, "descriptions": descriptions}
    except Exception as exc:
        logger.debug("Wikidata detail fetch failed for %s: %s", entity_id, exc)
        return None


def _truncate_id(node_id: str) -> str:
    """Truncate a node_id for display."""
    if len(node_id) < 32:
        return node_id
    return node_id[:16]


# Re-export from lightercore for backward compatibility.
# These functions have moved to the shared library so they can be
# used by multiple projects (lighterbird, semantika) without duplication.
from lightercore.text_utils import (  # noqa: F401  — re-exported
    normalize_label_to_id,
    sanitize_node_id,
    strip_diacritics,
)
