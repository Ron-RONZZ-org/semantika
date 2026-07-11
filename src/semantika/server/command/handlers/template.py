"""Command handlers for triple template management (primarily for LLM tool use).

Provides ``!template list``, ``!template view``, ``!template save`` so the LLM
can discover, inspect, and persist YAML triple templates during the
``/template`` prompt command flow.

Users typically edit YAML files directly in
``~/.config/semantika/templates/`` — these commands are mainly intended
for LLM tool-calling use.
"""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command
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
            }
            for p in tpl.params
        ],
        "triples": [t.raw for t in tpl.triples],
        "param_count": len(tpl.params),
        "triple_count": len(tpl.triples),
    }


@command(
    "template.save",
    description="Save a YAML triple template to disk (creates or overwrites a .yaml file in the templates directory)",
    params=[{"name": "yaml", "type": "string", "required": True, "description": "Full YAML content of the template"}],
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
    usage_parts = [f"!triple add --template {name}"]
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
