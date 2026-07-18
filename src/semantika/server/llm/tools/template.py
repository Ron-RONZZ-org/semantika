"""LLM tools for triple template operations.

Templates are reusable triple patterns stored as YAML files.

.. note::
    Imports from ``server.templates`` are done inside function bodies
    to avoid a circular import chain:
    ``tools/template → templates/loader → templates/executor → handlers/triple → handlers/__init__ → handlers/template → templates/executor``
"""

from __future__ import annotations

import logging
from typing import Any

from lightercore.permissions import PermissionLevel

from semantika.server.llm.tools import llm_tool

logger = logging.getLogger(__name__)


@llm_tool(
    name="template.list",
    description="List all available triple templates.  Templates are "
    "reusable triple patterns that can be applied with "
    "template.apply.",
    permission_level=PermissionLevel.READ,
)
def llm_template_list(**kwargs) -> dict:
    """List all available triple templates."""
    from semantika.server.templates.loader import list_templates

    try:
        templates = list_templates()
        return {
            "success": True,
            "data": [
                {
                    "name": t.name,
                    "description": t.description,
                    "param_count": len(t.params),
                    "params": [p.name for p in t.params],
                }
                for t in templates
            ],
        }
    except Exception as exc:
        logger.exception("template.list failed")
        return {"success": False, "error": str(exc)}


@llm_tool(
    name="template.view",
    description="View a triple template's full structure including its "
    "parameters, triple patterns, and descriptions.",
    params=[
        {"name": "name", "type": "string", "description": "Template name", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_template_view(name: str = "", **kwargs) -> dict:
    """View a triple template's full structure."""
    from semantika.server.templates.loader import load_template

    if not name:
        return {"success": False, "error": "Template name is required"}

    try:
        template = load_template(name)
        if not template:
            return {"success": False, "error": f"Template not found: {name}"}

        return {
            "success": True,
            "data": {
                "name": template.name,
                "description": template.description,
                "params": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description,
                        "required": p.required,
                    }
                    for p in template.params
                ],
                "triple_patterns": [
                    {
                        "subject": tp.subject,
                        "predicate": tp.predicate,
                        "object": tp.object,
                        "subject_type": tp.subject_type,
                        "object_type": tp.object_type,
                    }
                    for tp in template.patterns
                ],
            },
        }
    except Exception as exc:
        logger.exception("template.view failed")
        return {"success": False, "error": str(exc)}


@llm_tool(
    name="template.apply",
    description="Apply a triple template to create nodes and triples "
    "from labels.  Provide the template name and a JSON "
    "dict of parameter values.  Node-type parameters accept "
    "either existing node IDs or labels that will be used "
    "to create new nodes.",
    params=[
        {"name": "name", "type": "string", "description": "Template name", "required": True},
        {"name": "params", "type": "string", "description": "JSON dict of template parameter values, e.g. {'subject':'Alice','author':'Bob'}", "required": True},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_template_apply(**kwargs) -> dict:
    """Apply a triple template with the given parameter values."""
    import json

    from semantika.server.templates.executor import execute_template

    name = kwargs.get("name", "").strip()
    if not name:
        return {"success": False, "error": "Template name is required"}

    raw_params = kwargs.get("params", "")
    if not raw_params:
        return {"success": False, "error": "Template parameters are required"}

    try:
        params = json.loads(raw_params) if isinstance(raw_params, str) else raw_params
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON in 'params' parameter"}

    if not isinstance(params, dict):
        return {"success": False, "error": "'params' must be a JSON object"}

    try:
        result = execute_template(name, params)
        if result:
            return {
                "success": True,
                "data": {
                    "created_nodes": result.get("created_nodes", []),
                    "created_triples": result.get("created_triples", 0),
                },
            }
        return {"success": False, "error": f"Failed to apply template: {name}"}
    except Exception as exc:
        logger.exception("template.apply failed for %s", name)
        return {"success": False, "error": str(exc)}
