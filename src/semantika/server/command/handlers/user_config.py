"""Command handler for user configuration (!user config).

Supports locale setting and ID normalization toggles:
- ``--locale CODE`` — set locale (e.g. en, fr)
- ``--normalise-node-ids on|off`` — strip diacritics from node IDs on create
- ``--strip-predicate-diacritics on|off`` — strip diacritics from predicate IDs on create
"""

from __future__ import annotations

import logging

from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command, group_command
from semantika.server.user_config import (
    get_bool,
    get_locale,
    load_config,
    set_bool,
    set_locale,
)

logger = logging.getLogger(__name__)


@group_command("user", description="User configuration: locale, preferences")
def cmd_user_root(remaining: list[str], flags: dict[str, str]) -> dict:
    """User config help — opens the settings tab."""
    cfg = load_config()
    return {"type": "settings", "title": "Settings", "data": {
        "locale": cfg.get("locale", "en"),
        "normalise_node_ids": get_bool("normalise_node_ids", False),
        "strip_diacritics_from_predicate_ids": get_bool("strip_diacritics_from_predicate_ids", False),
    }}


@command("user.config", description="Show or modify user configuration",
         flags=[
             {"name": "locale", "type": "string", "help": "Set locale code (e.g. en, fr, de)"},
             {"name": "normalise-node-ids", "type": "string", "help": "Toggle node ID normalisation (on|off)"},
             {"name": "strip-predicate-diacritics", "type": "string", "help": "Toggle predicate diacritic stripping (on|off)"},
         ])
def cmd_user_config(remaining: list[str], flags: dict[str, str]) -> dict:
    """Show or modify user configuration."""
    errors: list[str] = []

    locale_val = flags.get("locale", "")
    if locale_val:
        if len(locale_val) < 2 or len(locale_val) > 5:
            raise CommandValidationError(
                "Locale should be a 2-letter code (e.g. 'en', 'fr') "
                "or 5-letter code with territory (e.g. 'en-US', 'zh-CN')"
            )
        set_locale(locale_val)

    norm_flag = flags.get("normalise-node-ids", "")
    if norm_flag:
        if norm_flag.lower() in ("on", "true", "1", "yes"):
            set_bool("normalise_node_ids", True)
        elif norm_flag.lower() in ("off", "false", "0", "no"):
            set_bool("normalise_node_ids", False)
        else:
            errors.append("--normalise-node-ids must be 'on' or 'off'")

    strip_flag = flags.get("strip-predicate-diacritics", "")
    if strip_flag:
        if strip_flag.lower() in ("on", "true", "1", "yes"):
            set_bool("strip_diacritics_from_predicate_ids", True)
        elif strip_flag.lower() in ("off", "false", "0", "no"):
            set_bool("strip_diacritics_from_predicate_ids", False)
        else:
            errors.append("--strip-predicate-diacritics must be 'on' or 'off'")

    if errors:
        raise CommandValidationError("; ".join(errors))

    cfg = load_config()
    had_changes = bool(locale_val or norm_flag or strip_flag)
    data = {
        "locale": cfg.get("locale", "en"),
        "normalise_node_ids": get_bool("normalise_node_ids", False),
        "strip_diacritics_from_predicate_ids": get_bool("strip_diacritics_from_predicate_ids", False),
    }
    if had_changes:
        data["message"] = "Configuration updated."
        return {"type": "status", "data": data}
    # No flags — open settings tab
    return {"type": "settings", "title": "Settings", "data": data}
