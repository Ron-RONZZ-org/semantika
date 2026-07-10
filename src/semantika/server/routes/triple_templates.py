"""API routes for triple template management.

Endpoints:
- GET  /api/v1/triple-templates/list       — autocomplete source
- GET  /api/v1/triple-templates/{name}      — full template definition
- POST /api/v1/triple-templates/expand      — preview expanded triples
- POST /api/v1/triple-templates/execute     — expand and add all triples
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from semantika.server.templates.executor import execute_template, expand_template
from semantika.server.templates.loader import list_templates, load_template

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/triple-templates", tags=["triple-templates"])


# ── GET /list ────────────────────────────────────────────────────────────────


@router.get("/list")
async def list_templates_endpoint() -> list[dict[str, Any]]:
    """Return all available triple templates (name + description).

    Used by the frontend for autocomplete.
    """
    templates = list_templates()
    return [
        {
            "name": t.name,
            "description": t.description,
            "param_count": len(t.params),
        }
        for t in templates
    ]


# ── GET /{name} ──────────────────────────────────────────────────────────────


@router.get("/{name}")
async def get_template_endpoint(name: str) -> dict[str, Any]:
    """Return a full template definition (for dynamic form generation)."""
    tpl = load_template(name)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

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
    }


# ── POST /expand ─────────────────────────────────────────────────────────────


@router.post("/expand")
async def expand_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Preview expanded triples without adding them."""
    name = data.get("name", "").strip()
    values = data.get("values", {}) or {}

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    tpl = load_template(name)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    try:
        triples = expand_template(tpl, values)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "template": name,
        "triples": triples,
        "count": len(triples),
    }


# ── POST /execute ────────────────────────────────────────────────────────────


@router.post("/execute")
async def execute_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand and add all triples from a template."""
    name = data.get("name", "").strip()
    values = data.get("values", {}) or {}

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    tpl = load_template(name)
    if tpl is None:
        available = [t.name for t in list_templates()]
        raise HTTPException(
            status_code=404,
            detail=(
                f"Template '{name}' not found. "
                f"Available: {', '.join(available) or '(none)'}"
            ),
        )

    # Validate required params
    missing = [p.name for p in tpl.params if p.required and not values.get(p.name, "").strip()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required parameters: {', '.join(missing)}",
        )

    try:
        result = execute_template(tpl, values)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


# ── POST /save ────────────────────────────────────────────────────────────────


@router.post("/save")
async def save_template_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Save a generated YAML template to ``~/.config/semantika/templates/``.

    Expects ``{"yaml": "...", "name": "..."}``.  If ``name`` is omitted,
    the ``name:`` field from the YAML itself is used.  The file is written
    atomically (temp + rename) to avoid corruption.
    """

    yaml_content = data.get("yaml", "").strip()
    name = data.get("name", "").strip()

    if not yaml_content:
        raise HTTPException(status_code=400, detail="'yaml' content is required.")

    # Infer name from YAML if not provided
    if not name:
        import yaml as pyyaml
        try:
            parsed = pyyaml.safe_load(yaml_content)
            if isinstance(parsed, dict) and parsed.get("name"):
                name = parsed["name"]
        except Exception:
            logger.debug("Could not parse YAML to infer template name")

    if not name:
        raise HTTPException(status_code=400, detail="Could not infer template name from YAML. Provide a 'name' field.")

    from lightercore.paths import config_dir
    templates_dir = config_dir() / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    dest = templates_dir / f"{name}.yaml"
    # Atomic write: write to temp, then rename
    tmp = dest.with_suffix(".yaml.tmp")
    try:
        tmp.write_text(yaml_content, encoding="utf-8")
        tmp.rename(dest)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to save template: {e}")

    return {
        "type": "status",
        "data": {
            "message": f"Template '{name}' saved to {dest}",
            "path": str(dest),
        },
    }
