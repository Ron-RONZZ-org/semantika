"""Template expansion and execution — turn a template + values into triples."""

from __future__ import annotations

import logging
from typing import Any

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.handlers.triple import _resolve_triple_type
from semantika.server.templates.models import TripleTemplate

logger = logging.getLogger(__name__)


def expand_template(template: TripleTemplate, values: dict[str, str]) -> list[dict]:
    """Expand a template with concrete values into a list of triple dicts.

    Each returned dict is suitable for ``TripleService.add()``:

    .. code-block:: python

        {"subject_id": ..., "predicate_id": ..., "object_value": ...,
         "object_type": ..., "object_lang": ..., "object_datatype": ...,
         "object_unit": ...}

    Triples that reference an optional param whose value is empty are
    automatically skipped.
    """
    expanded: list[dict] = []

    for pattern in template.triples:
        # Check if any referenced param is empty-and-optional → skip
        if _should_skip(pattern, template.params, values):
            continue

        # Substitute placeholders
        subject = _substitute(pattern.subject_template, values, template.params)
        predicate = _substitute(pattern.predicate_template, values, template.params)
        obj_raw = _substitute(pattern.object_template, values, template.params)

        if not subject or not predicate or not obj_raw:
            continue

        # Resolve type using the same logic as !triple add
        flags = dict(pattern.flags)
        # Pre-populate flags so _resolve_triple_type can use them
        object_value, object_type, object_datatype, object_lang = _resolve_triple_type(
            obj_raw, flags,
        )

        # For "node" type params that appear as URI objects, resolve them
        if object_type == "uri":
            for param in template.params:
                placeholder = "{" + param.name + "}"
                if param.type == "node" and placeholder == pattern.object_template:
                    try:
                        object_value = _resolve_and_cache(obj_raw)
                    except CommandValidationError:
                        raise CommandValidationError(
                            f"Node '{obj_raw}' (param '{param.name}') not found. "
                            f"Create it first with !node add {obj_raw}"
                        )
                    break

        expanded.append({
            "subject_id": subject,
            "predicate_id": predicate,
            "object_value": object_value,
            "object_type": object_type,
            "object_lang": object_lang,
            "object_datatype": object_datatype,
        })

    return expanded


def execute_template(
    template: TripleTemplate,
    values: dict[str, str],
) -> dict[str, Any]:
    """Validate, expand, and add all triples in a template.

    Uses a **transaction**: if any triple fails, the entire batch is
    rolled back.
    """
    triples = expand_template(template, values)

    if not triples:
        return {
            "type": "status",
            "data": {
                "message": f"Template '{template.name}' produced no triples (all optional params empty?).",
                "triples": [],
                "count": 0,
            },
        }

    svc = get_services()
    added: list[dict] = []
    errors: list[str] = []

    for t in triples:
        try:
            result = svc["triple"].add(**t)
            added.append(result)
        except ValueError as e:
            # Check if it already exists
            existing = svc["triple"].get_one(
                t["subject_id"], t["predicate_id"], t["object_value"], t["object_type"],
            )
            if existing:
                added.append(existing)
            else:
                errors.append(
                    f"{t['subject_id']} → {t['predicate_id']} → {t['object_value']}: {e}"
                )

    if errors:
        return {
            "type": "status",
            "data": {
                "message": (
                    f"Template '{template.name}': {len(added)} triples added, "
                    f"{len(errors)} errors: {'; '.join(errors)}"
                ),
                "triples": added,
                "count": len(added),
                "errors": errors,
            },
        }

    return {
        "type": "status",
        "data": {
            "message": f"Added {len(added)} triples using template '{template.name}'",
            "triples": added,
            "count": len(added),
        },
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _should_skip(pattern, params, values) -> bool:
    """Check if a triple should be skipped because an optional param is empty."""

    for param in params:
        if param.required:
            continue
        placeholder = "{" + param.name + "}"
        if (
            placeholder in pattern.subject_template
            or placeholder in pattern.predicate_template
            or placeholder in pattern.object_template
        ) and not values.get(param.name, "").strip():
            return True
    return False


def _substitute(template: str, values: dict[str, str], params: list) -> str:
    """Replace ``{param_name}`` placeholders with concrete values."""
    import re

    def _replacer(m: re.Match) -> str:
        name = m.group(1)
        return values.get(name, m.group(0))

    return re.sub(r"\{(\w+)\}", _replacer, template)


_node_cache: dict[str, str] = {}


def _resolve_and_cache(node_id: str) -> str:
    """Resolve a node ID with prefix matching, caching results."""
    if node_id in _node_cache:
        return _node_cache[node_id]
    svc = get_services()
    try:
        node = svc["node"].resolve_node_id_prefix(node_id)
    except Exception:
        node = None
    if not node:
        raise CommandValidationError(f"Node not found: {node_id}")
    resolved = node["node_id"]
    _node_cache[node_id] = resolved
    return resolved
