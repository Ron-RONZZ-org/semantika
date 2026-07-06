"""Shared helper functions for graph services.

Ported from A-semantika's ``_node_helpers.py`` with EO→EN rename.
"""

from __future__ import annotations

import json
import re
import unicodedata


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


def _truncate_id(node_id: str) -> str:
    """Truncate a node_id for display."""
    if len(node_id) < 32:
        return node_id
    return node_id[:16]


def sanitize_node_id(raw_id: str) -> str:
    """Strip invisible Unicode characters from a node_id."""
    return "".join(
        ch for ch in raw_id.strip()
        if unicodedata.category(ch) not in ("Cf", "Cc")
        or ch in (" ", "\t")
    )


def normalize_label_to_id(label: str) -> str:
    """Convert a human label into a node_id-safe ASCII string.

    Pipeline: NFKD decomposition → ASCII only → collapse non-alpha → UPPERCASE.
    """
    nfkd = unicodedata.normalize("NFKD", label)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_str)
    safe = safe.strip("_")
    if not safe:
        return "_UNLABELED"
    return safe.upper()
