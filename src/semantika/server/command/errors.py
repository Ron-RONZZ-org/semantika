"""Command dispatch error classes.

Ported from lighterbird's ``server/command/errors.py``.
"""

from __future__ import annotations


class CommandError(Exception):
    """Base error for command dispatch."""


class CommandNotFound(CommandError):
    """No handler registered for the given command path."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        super().__init__(f"Unknown command: !{' '.join(tokens)}")


class CommandValidationError(CommandError):
    """Invalid or missing arguments for a command."""

    def __init__(self, message: str, suggestion: str = "") -> None:
        self.suggestion = suggestion
        super().__init__(message)
