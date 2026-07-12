"""Command handlers for triple template management (primarily for LLM tool use).

Provides ``!template list``, ``!template view``, ``!template save`` so the LLM
can discover, inspect, and persist YAML triple templates, and ``!template use``
to apply a template (creating nodes from labels, then triples).

Users typically edit YAML files directly in
``~/.config/semantika/templates/`` — these commands are mainly intended
for LLM tool-calling use.
"""

from __future__ import annotations

import json
import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.helpers import parse_lang_tag_pairs
from semantika.server.command.registry import command
from semantika.server.templates.executor import execute_template
from semantika.server.templates.loader import list_templates, load_template

logger = logging.getLogger(__name__)


@command(
    "template.list",
    description="List available triple templates (name + description + param count)",
    permission_level=PermissionLevel.READ,
)
def cmd_template_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List available triple templates. READ-level — no confirmation needed."""
    templates = list_templates()
    return {
        "templates": [
            {
                "name": t.name,
                "description": t.description,
                "param_count": len(t.params),
            }
            for t in templates
        ],
        "count": len(templates),
    }


@command(
    "template.view",
    description="View a triple template's full structure (params + triples)",
    params=[{"name": "name", "type": "string", "required": True, "description": "Template name"}],
    permission_level=PermissionLevel.READ,
)
def cmd_template_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a specific template's full structure. READ-level."""
    name = flags.get("name", "").strip() or (remaining[0] if remaining else "")
    if not name:
        raise CommandValidationError("Template name is required — use !template list to see available names")

    tpl = load_template(name)
    if tpl is None:
        available = [t.name for t in list_templates()]
        raise CommandValidationError(
            f"Template '{name}' not found. Available: {', '.join(available) or '(none)'}"
        )

    return {
        "name": tpl.name,
        "description": tpl.description,
        "params": [
            {
                "name": p.name,
                "label": p.label,
                "type": p.type,
                "required": p.required,
                "help": p.help,
                "languages": list(p.languages) if p.languages else None,
            }
            for p in tpl.params
        ],
        "triples": [t.raw for t in tpl.triples],
        "param_count": len(tpl.params),
        "triple_count": len(tpl.triples),
    }


@command(
    "template.save",
    description="Save a reusable triple pattern as a named template for repeated use",
    params=[{"name": "yaml", "type": "string", "required": True, "description": "Full template definition content"}],
)
def cmd_template_save(remaining: list[str], flags: dict[str, str]) -> dict:
    """Save a YAML triple template to disk.

    WRITE-level — triggers HITL user confirmation before the file is written.
    Users can reject the save and provide feedback for the LLM to adjust.
    """
    from pathlib import Path

    import yaml as pyyaml

    from lightercore.paths import config_dir

    yaml_content = flags.get("yaml", "").strip()
    if not yaml_content:
        raise CommandValidationError("--yaml is required — the full YAML content for the template")

    # Validate YAML structure
    try:
        parsed = pyyaml.safe_load(yaml_content)
    except Exception as e:
        raise CommandValidationError(f"Invalid YAML: {e}")

    if not isinstance(parsed, dict):
        raise CommandValidationError("YAML root must be a dict with a 'name' field")
    if not parsed.get("name"):
        raise CommandValidationError("YAML must include a top-level 'name' field")
    if "triples" not in parsed:
        raise CommandValidationError("YAML must include a 'triples' list")

    # Validate triple format — must be strings like "{subject} rs:xxx {object} [--flag]"
    raw_triples = parsed.get("triples", [])
    for i, t in enumerate(raw_triples):
        if not isinstance(t, str):
            raise CommandValidationError(
                f"Triple #{i + 1} must be a string, got {type(t).__name__}. "
                f"Expected format: '{{subject}} rs:predicate {{object}} [--flag]'\n"
                f"Instead of dict format:\n"
                f"  bad:  - subject: '{{subject}}'\n"
                f"        - predicate: 'rs:predicate'\n"
                f"        - object: '{{object}}'\n"
                f"  good: - '{{subject}} rs:predicate {{object}}'       # URI ref (no flag)\n"
                f"  good: - '{{subject}} rs:predicate {{object}} --str' # string literal"
            )

    name = parsed["name"]
    templates_dir = config_dir() / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    dest = templates_dir / f"{name}.yaml"
    tmp = dest.with_suffix(".yaml.tmp")
    try:
        tmp.write_text(yaml_content, encoding="utf-8")
        tmp.rename(dest)
    except OSError as e:
        raise CommandValidationError(f"Failed to save template '{name}': {e}")

    logger.info("Template '%s' saved to %s", name, dest)

    # Build usage string for LLM to include in its final answer
    params_list = parsed.get("params", [])
    param_names = [
        p["name"] for p in params_list
        if isinstance(p, dict) and isinstance(p.get("name"), str) and p["name"].strip()
    ]
    usage_parts = [f"!template use {name}"]
    usage_parts += [f"--{p} <{p}>" for p in param_names]
    usage = " \\\n    ".join(usage_parts)

    return {
        "message": f"Template '{name}' saved to {dest}",
        "path": str(dest),
        "name": name,
        "param_count": len(params_list),
        "triple_count": len(parsed.get("triples", [])),
        "usage": usage,
    }


# ── !template use — apply a template ────────────────────────────────────────


@command(
    "template.use",
    description="Apply a reusable template: create nodes from labels, then add triples",
    interactive=True,
    params=[{"name": "name", "type": "string", "required": True,
             "description": "Template name to apply"}],
)
def cmd_template_use(remaining: list[str], flags: dict[str, str]) -> dict:
    """Apply a template: create nodes from labels, then create triples.

    Phase 1 — For each ``type: node`` parameter, the value is treated
    as a label (plain text, ``LANG::TEXT`` pairs, or JSON dict), and a
    node is created (or an existing one reused).

    Phase 2 — Delegates to :func:`~semantika.server.templates.executor.execute_template`
    to create all triples using the resolved node IDs.

    Examples::

        !template use book --subject "The Great Gatsby" --author "F. Scott Fitzgerald"
        !template use book --subject '{"en":"Gatsby","fr":"Gatsby le Magnifique"}'
        !template use book --subject "en::Gatsby, fr::Gatsby le Magnifique"
    """
    from semantika.server.templates.executor import execute_template
    from semantika.server.templates.loader import list_templates, load_template

    template_name = flags.get("name") or (remaining[0] if remaining else "")
    if not template_name:
        raise CommandValidationError(
            "Specify a template name — use !template list to see available ones"
        )

    tpl = load_template(template_name)
    if tpl is None:
        available = [t.name for t in list_templates()]
        raise CommandValidationError(
            f"Template '{template_name}' not found. "
            f"Available: {', '.join(available) or '(none)'}"
        )

    svc = get_services()
    values: dict[str, str] = {}
    remaining_copy = list(remaining)

    # Phase 1: collect values, creating nodes for type:node params
    for param in tpl.params:
        val = flags.get(param.name, "")
        if not val and remaining_copy:
            val = remaining_copy.pop(0)
        if not val:
            continue

        if param.type == "node":
            values[param.name] = _resolve_or_create_node(svc, val)
        else:
            values[param.name] = val

    # Check required params
    missing = [p.name for p in tpl.params if p.required and not values.get(p.name, "").strip()]
    if missing:
        return {
            "type": "form-required",
            "data": {
                "form": f"template-{template_name}",
                "templateName": template_name,
                "params": [
                    {
                        "name": p.name, "label": p.label,
                        "type": p.type, "required": p.required,
                        "languages": list(p.languages) if p.languages else None,
                    }
                    for p in tpl.params
                ],
                "initialData": {},
                "missing": missing,
                "message": f"Missing required parameters: {', '.join(missing)}",
            },
        }

    # Phase 2: execute template (create triples)
    return execute_template(tpl, values)


def _resolve_or_create_node(svc: dict, raw: str) -> str:
    """Resolve a label value to a node ID, creating the node if needed.

    Accepts the same formats as ``!node add --labels``:

    - Plain string: creates ``{"en": raw}``
    - ``LANG::TEXT`` pairs: ``"en::Title, fr::Titre"``
    - JSON dict: ``'{"en": "Title", "fr": "Titre"}'``

    Before creating, searches for an existing node by the English label
    (or first available label) to avoid duplicates.
    """
    # Parse labels from the raw value
    if raw.startswith("{"):
        try:
            labels = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            labels = {"en": raw}
    elif "::" in raw:
        labels = parse_lang_tag_pairs(raw)
    else:
        labels = {"en": raw}

    if not isinstance(labels, dict) or not labels:
        labels = {"en": raw}

    # Search for existing node by English label or first label
    search_term = labels.get("en") or next(iter(labels.values()), "")
    if search_term:
        existing = svc["node"].search(search_term)
        if existing:
            return existing[0]["node_id"]

    # Create new node
    try:
        node = svc["node"].create({"labels": labels})
    except ValueError as e:
        raise CommandValidationError(f"Failed to create node from label '{raw}': {e}")
    return node["node_id"]
