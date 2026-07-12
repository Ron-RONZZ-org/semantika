"""Data models for triple templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TemplateParam:
    """A single parameter in a triple template."""

    name: str
    label: str
    type: str = "string"  # "node" | "string" | "number"
    required: bool = False
    help: str = ""
    languages: list[str] = field(default_factory=list)
    """Expected label languages for node-type params (e.g. ``["en", "fr"]``).
    Informational only — the handler accepts JSON, LANG::TEXT, or plain text
    regardless.  When specified, appears in ``!template view`` output."""


@dataclass
class TriplePattern:
    """A single parsed triple pattern within a template."""

    raw: str
    """Original pattern text (e.g. ``"{subject} hasAuthor {author}"``)."""

    subject_template: str
    """Subject expression with ``{param}`` placeholders."""

    predicate_template: str
    """Predicate expression with ``{param}`` placeholders."""

    object_template: str
    """Object expression with ``{param}`` placeholders."""

    flags: dict[str, str] = field(default_factory=dict)
    """Type flags from the pattern (e.g. ``{"str": "", "lang": "en"}``)."""


@dataclass
class TripleTemplate:
    """A parsed triple template loaded from a YAML file."""

    name: str
    description: str = ""
    params: list[TemplateParam] = field(default_factory=list)
    triples: list[TriplePattern] = field(default_factory=list)
    path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    """Raw YAML dict — preserved for round-tripping."""
