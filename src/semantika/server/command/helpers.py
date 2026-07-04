"""Shared helper functions for command handlers.

Ported from the bottom of the old command.py.
"""

from __future__ import annotations

import json
from typing import Any

from semantika.server.command.errors import CommandValidationError


def resolve_group(svc: dict, name: str) -> dict:
    """Resolve a predicate group by name."""
    group = svc["predicate_group"].resolve_group_name(name)
    if not group:
        raise CommandValidationError(f"Group not found: '{name}'")
    return group


def parse_lang_tag_pairs(text: str | list[str]) -> dict[str, str]:
    """Parse ``LANG::TEXT`` or ``LANG:TEXT`` pairs into a dict."""
    result: dict[str, str] = {}
    if isinstance(text, str):
        items = [t.strip() for t in text.replace(",", " ").split() if t.strip()]
    else:
        items = text
    for item in items:
        if "::" in item:
            lang, _, val = item.partition("::")
        elif ":" in item:
            lang, _, val = item.partition(":")
        else:
            continue
        lang = lang.strip()
        val = val.strip()
        if lang and val:
            result[lang] = val
    return result


def safe_json_loads(raw: Any) -> dict:
    """Safely parse a JSON string to a dict, returning {} on failure."""
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def fmt_size(b: int) -> str:
    """Format a byte count for human display."""
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KiB"
    return f"{b / (1024 * 1024):.1f} MiB"


def fmt_ts(ts: str) -> str:
    """Format a backup timestamp for human display."""
    if len(ts) >= 15:
        base = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
        if len(ts) > 15:
            base += f".{ts[15:21]}"
        return base
    return ts


def backup_dir_abs() -> str:
    """Return the absolute path of the default backup directory."""
    from semantika.core.paths import data_dir
    return str((data_dir() / ".backups").resolve())
