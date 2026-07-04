"""Server-side command tokenizer for expanded template strings.

Must produce the same output as the frontend ``parser.js:parseCommand()``
for the same input.

Ported from lighterbird's ``server/command/parser.py``.
"""

from __future__ import annotations

import shlex


def parse_expanded(cmd_str: str) -> tuple[list[str], dict[str, str]]:
    """Parse an expanded command string into tokens and flags.

    Uses ``shlex`` for robust quoting (handles double quotes, escapes).

    Args:
        cmd_str: Command string, e.g. ``node add --labels '{"en":"Dog"}'``.

    Returns:
        ``(tokens, flags)`` where tokens are positional arguments and
        flags is a dict of flag name → value.
    """
    text = cmd_str.strip()
    if text.startswith("!"):
        text = text[1:].strip()

    tokens: list[str] = []
    flags: dict[str, str] = {}
    in_flag: str | None = None

    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()

    for part in parts:
        if part.startswith("--"):
            if in_flag is not None:
                flags[in_flag] = "true"
                in_flag = None
            if "=" in part:
                name, value = part[2:].split("=", 1)
                flags[name] = value
            else:
                in_flag = part[2:]
        elif part.startswith("-") and len(part) == 2 and not part[1].isdigit():
            in_flag = part[1]
        elif in_flag is not None:
            flags[in_flag] = part
            in_flag = None
        else:
            tokens.append(part)

    if in_flag is not None:
        flags[in_flag] = "true"

    return tokens, flags
