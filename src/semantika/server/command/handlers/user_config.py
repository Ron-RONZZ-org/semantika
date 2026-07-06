"""Command handler for user configuration (!user config).

Supports locale setting and other user preferences.
"""

from __future__ import annotations

import logging

from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command, group_command
from semantika.server.user_config import load_config, save_config, set_locale

logger = logging.getLogger(__name__)


@group_command("user", description="User configuration: locale, preferences")
def cmd_user_root(remaining: list[str], flags: dict[str, str]) -> dict:
    """User config help."""
    cfg = load_config()
    locale = cfg.get("locale", "en")
    return {"type": "status", "title": "User Config", "data": {
        "_summary": f"Current locale: {locale}\n\n"
                     "Available !user commands:\n"
                     "  !user config                — Show current config\n"
                     "  !user config --locale CODE  — Set locale (e.g. en, fr, de, es, eo)\n"
                     "\n"
                     "GUI: Click the locale badge in the status bar to change."}}


@command("user.config", description="Show or modify user configuration",
         flags=[{"name": "locale", "type": "string", "help": "Set locale code (e.g. en, fr, de)"}])
def cmd_user_config(remaining: list[str], flags: dict[str, str]) -> dict:
    """Show or modify user configuration."""
    locale_val = flags.get("locale", "")
    if locale_val:
        if len(locale_val) != 2 and len(locale_val) != 5:
            raise CommandValidationError(
                "Locale should be a 2-letter code (e.g. 'en', 'fr') "
                "or 5-letter code with territory (e.g. 'en-US', 'zh-CN')"
            )
        set_locale(locale_val)
        return {"type": "status", "data": {
            "message": f"Locale set to '{locale_val}'",
            "locale": locale_val,
        }}

    cfg = load_config()
    return {"type": "status", "data": {
        "locale": cfg.get("locale", "en"),
        "message": f"Current locale: {cfg.get('locale', 'en')}",
    }}
