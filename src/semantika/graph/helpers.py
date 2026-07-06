"""Shared helpers for graph services."""

from __future__ import annotations


def escape_like(s: str) -> str:
    """Escape special characters for SQLite LIKE with ESCAPE '\\'.

    Escapes ``\\``, ``%``, and ``_`` characters so user-supplied strings
    can be safely used in LIKE patterns.
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
