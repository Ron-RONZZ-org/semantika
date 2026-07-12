"""YAML-based triple template loader.

Templates live in ``~/.config/semantika/templates/*.yaml`` (or ``*.yml``).
Mirrors the pattern of ``lightercore.prompt_commands``.

Schema::

    name: <template-name>          # optional; defaults to file stem
    description: <short-description>
    params:                        # optional
      - name: <param-name>
        label: <human-label>
        type: node | string | number
        required: true
        help: <help-text>
    triples:                       # list of triple patterns
      - "{subject} hasAuthor {author}"
      - "{subject} hasTitle {title} --str"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lightercore.paths import config_dir

from semantika.server.templates.models import TemplateParam, TriplePattern, TripleTemplate

logger = logging.getLogger(__name__)

_TEMPLATES_DIR_NAME = "templates"


def _templates_dir() -> Path:
    """Return the templates directory (config_dir / 'templates')."""
    d = config_dir() / _TEMPLATES_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _find_yaml_files() -> list[Path]:
    """Return sorted list of ``.yaml`` / ``.yml`` files in templates dir."""
    d = _templates_dir()
    files: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        files.extend(sorted(d.glob(ext)))
    return files


def list_templates() -> list[TripleTemplate]:
    """Scan ``templates/*.{yaml,yml}`` and return parsed templates.

    Files with parse errors are silently skipped (logged at DEBUG level).
    """
    result: list[TripleTemplate] = []
    for path in _find_yaml_files():
        try:
            tpl = _parse_file(path)
            if tpl is not None:
                result.append(tpl)
        except Exception:
            logger.debug("Skipping invalid template file: %s", path, exc_info=True)
    return result


def load_template(name: str) -> TripleTemplate | None:
    """Load a single template by name (case-insensitive, stem or ``name`` field).

    Returns ``None`` if no matching template is found.
    """
    name_lower = name.lower()
    for path in _find_yaml_files():
        try:
            tpl = _parse_file(path)
            if tpl is not None and tpl.name.lower() == name_lower:
                return tpl
        except Exception:
            logger.debug("Error loading template %s: %s", path, exc_info=True)
    return None


# ── YAML parsing ─────────────────────────────────────────────────────────────


def _parse_file(path: Path) -> TripleTemplate | None:
    """Parse a single YAML file into a ``TripleTemplate``.

    Returns ``None`` if the file is empty or lacks a valid structure.
    """
    import yaml  # available via rdflib dependency chain

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None

    name = raw.get("name") or path.stem
    desc = raw.get("description", "")
    raw_params = raw.get("params", []) or []
    raw_triples = raw.get("triples", []) or []

    params = [_parse_param(p) for p in raw_params if isinstance(p, dict)]
    triples = [_parse_triple(t) for t in raw_triples if isinstance(t, str)]

    return TripleTemplate(
        name=name,
        description=desc,
        params=params,
        triples=triples,
        path=path,
        raw=raw,
    )


def _parse_param(raw: dict[str, Any]) -> TemplateParam:
    """Parse a single param dict."""
    return TemplateParam(
        name=raw.get("name", ""),
        label=raw.get("label", raw.get("name", "")),
        type=raw.get("type", "string"),
        required=bool(raw.get("required", False)),
        help=raw.get("help", ""),
        languages=raw.get("languages", []),
    )


def _parse_triple(pattern: str) -> TriplePattern:
    """Parse a triple pattern string into its components.

    Supports optional ``--flag`` suffixes at the end:
        ``"{subj} hasAuthor {obj}"``
        ``"{subj} hasTitle {title} --str --lang=en"``
    """
    parts = pattern.strip().split()

    # Split off flag-like tokens at the end
    flags: dict[str, str] = {}
    while parts and parts[-1].startswith("--"):
        flag = parts.pop()
        if "=" in flag:
            key, val = flag[2:].split("=", 1)
            flags[key] = val
        else:
            flags[flag[2:]] = ""

    if len(parts) < 3:
        # Not enough parts — store as-is
        return TriplePattern(
            raw=pattern,
            subject_template=pattern,
            predicate_template="",
            object_template="",
            flags=flags,
        )

    subject = parts[0]
    predicate = parts[1]
    obj = " ".join(parts[2:])

    return TriplePattern(
        raw=pattern,
        subject_template=subject,
        predicate_template=predicate,
        object_template=obj,
        flags=flags,
    )


if __name__ == "__main__":
    # Quick manual test
    for tpl in list_templates():
        print(f"  {tpl.name}: {tpl.description} ({len(tpl.params)} params, {len(tpl.triples)} triples)")
