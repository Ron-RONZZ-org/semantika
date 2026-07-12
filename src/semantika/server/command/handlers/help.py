"""Command handler for ``!help`` — auto-generated command reference.

Returns the full command tree grouped by domain, with descriptions, params,
and flags sourced entirely from ``@command()`` decorator metadata.
"""

from __future__ import annotations

from semantika.server.command.registry import (
    command,
    get_command_definitions,
)


@command("help",
         description="Show the command reference with all available !commands "
                     "grouped by domain",
         flags=[{"name": "q", "type": "string", "help": "Filter commands by keyword"},
                {"name": "domain", "type": "string", "help": "Show only a specific domain (e.g. node, triple)"}])
def cmd_help(remaining: list[str], flags: dict[str, str]) -> dict:
    """Show help for all commands, or for a specific command.

    Usage:
        ``!help`` — full command reference grouped by domain
        ``!help node list`` — details for a specific command
    """
    defs = get_command_definitions()

    if remaining:
        # Looking up a specific command: remaining holds the path tokens
        # e.g. !help node list -> remaining = ["node", "list"]
        target = [t.lower() for t in remaining]
        for cmd in defs:
            if [p.lower() for p in cmd["path"]] == target:
                return {
                    "type": "help",
                    "title": f"!{' '.join(cmd['path'])}",
                    "data": {"command": cmd, "groups": None},
                }
        return {
            "type": "help",
            "title": "Command Not Found",
            "data": {
                "error": f"No command !{' '.join(remaining)} found",
                "groups": None,
            },
        }

    # Full reference: group commands by first-level domain
    groups: dict[str, list[dict]] = {}
    for cmd in defs:
        domain = cmd["path"][0] if cmd["path"] else "general"
        groups.setdefault(domain, []).append(cmd)

    return {
        "type": "help",
        "title": "Command Reference",
        "data": {
            "groups": dict(sorted(groups.items())),
            "total": len(defs),
            "group_count": len(groups),
        },
    }
