"""Custom exceptions for Semantika."""

from __future__ import annotations

from pathlib import Path


class SemantikaError(Exception):
    """Base exception for all Semantika errors."""


class AmbiguousIDError(ValueError):
    """Raised when an ID prefix matches multiple entities.

    Attributes:
        message: Human-readable error message.
        matches: List of matching entity dicts (for interactive selection).
    """

    def __init__(self, message: str, matches: list[dict] | None = None) -> None:
        super().__init__(message)
        self.matches: list[dict] = matches or []


class ProtectedPathError(SemantikaError):
    """Raised when attempting to delete a protected directory."""

    def __init__(self, path: Path, operation: str) -> None:
        self.path = path
        self.operation = operation
        super().__init__(f"Cannot {operation} protected path: {path}")
