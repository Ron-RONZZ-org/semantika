"""Command handlers for triple management: list, view, add, delete, modify."""

from __future__ import annotations

import logging
from pathlib import Path

from semantika.core.exceptions import AmbiguousIDError
from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command

logger = logging.getLogger(__name__)


# ── Shared helpers ─────────────────────────────────────────────────────────


def _is_flag_set(flag_name: str, flags: dict[str, str]) -> bool:
    """Check if a flag was passed, supporting bare flags and --name value forms."""
    return flag_name in flags or flags.get(flag_name, "").lower() in ("true", "1", "yes")


def _resolve_triple_type(
    raw_object: str,
    flags: dict[str, str],
) -> tuple[str, str, str | None, str | None]:
    """Resolve object type/datatype/lang from user flags.

    Handles the if/elif chain for katex → str_dosiero → str → int → float → bool → uri fallback.

    Returns:
        (object_value, object_type, object_datatype, object_lang)
    """
    str_flag = _is_flag_set("str", flags)
    int_flag = _is_flag_set("int", flags)
    float_flag = _is_flag_set("float", flags)
    bool_flag = _is_flag_set("bool", flags)
    lang = flags.get("lang", None)
    katex = flags.get("katex", None)
    str_dosiero = flags.get("str_dosiero", None) or flags.get("str-dosiero", None)
    kodlingvo = flags.get("kodlingvo", None)

    object_value = raw_object
    object_type = "uri"
    object_datatype: str | None = None
    object_lang: str | None = None
    was_str = False

    if katex is not None:
        object_value = katex.strip().strip("$")
        object_type = "literal"
        object_datatype = "text/katex"
    elif str_dosiero is not None:
        try:
            object_value = Path(str_dosiero).read_text(encoding="utf-8")
        except (FileNotFoundError, OSError) as e:
            raise CommandValidationError(f"Could not read file: {e}")
        object_type = "literal"
        object_datatype = "text/plain" if not kodlingvo else f"text/x-{kodlingvo}"
        was_str = True
    elif str_flag:
        object_type = "literal"
        was_str = True
    elif int_flag:
        object_type = "literal"
        object_datatype = "xsd:integer"
    elif float_flag:
        object_type = "literal"
        object_datatype = "xsd:decimal"
    elif bool_flag:
        object_type = "literal"
        object_datatype = "xsd:boolean"

    if was_str and lang:
        object_lang = lang

    return (object_value, object_type, object_datatype, object_lang)


def _resolve_object_node(svc: dict, object_value: str) -> str:
    """Resolve an object value to a confirmed node ID (prefix match).

    Raises:
        CommandValidationError: If the node is not found or reference is ambiguous.
    """
    try:
        obj_node = svc["node"].resolve_node_id_prefix(object_value)
    except AmbiguousIDError as e:
        raise CommandValidationError(str(e))
    if not obj_node:
        raise CommandValidationError(f"Object node not found: {object_value}")
    return obj_node["node_id"]


def _find_triple(
    svc: dict,
    subject: str,
    predicate: str,
    object_val: str,
) -> dict | None:
    """Find a triple matching subject/predicate/object.

    Tries literal match first, then URI match, then prefix resolution.
    """
    triple = svc["triple"].get_one(subject, predicate, object_val, object_type="literal")
    if not triple:
        triple = svc["triple"].get_one(subject, predicate, object_val, object_type="uri")
    if not triple:
        try:
            resolved = _resolve_object_node(svc, object_val)
        except CommandValidationError:
            resolved = None
        if resolved:
            triple = svc["triple"].get_one(subject, predicate, resolved, object_type="uri")
    return triple


# ── Triple commands ───────────────────────────────────────────────────────


@command("triple.list", description="List all triples")
def cmd_triple_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List triples, optionally filtered by subject."""
    svc = get_services()
    triples = svc["triple"].db.execute("SELECT * FROM triples ORDER BY subject_id, predicate_id LIMIT ?", (100,))
    return {"type": "triple-list", "data": triples}


@command("triple.search", description="Search triples by subject/predicate/object",
         params=[{"name": "q", "type": "string", "required": True}],
         flags=[{"name": "limit", "type": "number", "help": "Max results"}])
def cmd_triple_search(remaining: list[str], flags: dict[str, str]) -> dict:
    """Search triples where subject, predicate, or object matches the query.

    Uses a unified OR query across all three fields, resolving partial
    node/predicate IDs and labels via FTS5.
    """
    svc = get_services()
    q = flags.get("q") or (remaining[0] if remaining else "") or ""
    if not q:
        raise CommandValidationError("Enter a search query")
    raw_limit = flags.get("limit", "50")
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 50

    # Resolve matching node IDs (subject + object) and predicate IDs.
    # Strategy (matching A-semantika's multi-step resolution):
    #   1. Node ID prefix resolution (covers short human-readable IDs)
    #   2. FTS5/label search for nodes and predicates
    #   3. Always include object_value LIKE fallback for literal matches
    node_ids: list[str] = []

    # Step 1: Node ID prefix resolution
    prefix_node = svc["node"].resolve_node_id_prefix(q)
    if prefix_node:
        node_ids.append(prefix_node["node_id"])
    else:
        # Step 2: FTS5/label search
        matching_nodes = svc["node"].search(q, limit=5)
        node_ids = [n["node_id"] for n in matching_nodes]

    # Predicate resolution: prefix ID then label search
    pred_ids: list[str] = []
    prefix_pred = svc["predicate"].resolve_predicate_id_prefix(q)
    if prefix_pred:
        pred_ids.append(prefix_pred["predicate_id"])
    else:
        matching_preds = svc["predicate"].search(q, limit=5)
        pred_ids = [p["predicate_id"] for p in matching_preds]

    # Build unified OR query across subject, predicate, and object_value
    clauses: list[str] = []
    params: list = []

    if node_ids:
        placeholders = ", ".join(["?"] * len(node_ids))
        clauses.append(f"subject_id IN ({placeholders})")
        params.extend(node_ids)
        # Also match URI objects (triples where object is a matching node)
        clauses.append(f"(object_type = 'uri' AND object_value IN ({placeholders}))")
        params.extend(node_ids)

    if pred_ids:
        placeholders = ", ".join(["?"] * len(pred_ids))
        clauses.append(f"predicate_id IN ({placeholders})")
        params.extend(pred_ids)

    # Literal object value LIKE matching (for string literals, numbers, etc.)
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    clauses.append("object_value LIKE ? ESCAPE '\\'")
    params.append(f"%{escaped}%")

    where = " OR ".join(clauses)
    rows = svc["triple"].db.execute(
        f"SELECT DISTINCT * FROM triples WHERE {where} ORDER BY subject_id, predicate_id LIMIT ?",
        params + [limit],
    )
    return {"type": "triple-list", "data": rows, "label": f"Triples matching '{q}'"}


@command("triple.view", description="View triples for a node",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_triple_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a single triple by ID."""
    svc = get_services()
    node_id = flags.get("id") or (remaining[0] if remaining else "") or ""
    if not node_id:
        raise CommandValidationError("Specify a node ID")
    triples = svc["triple"].get_by_subject(node_id)
    if not triples:
        return {"type": "status", "data": {"message": f"No triples found for {node_id}", "triples": []}}
    return {"type": "table", "data": triples, "label": f"Triples for {node_id}"}


@command("triple.add", description="Add a triple", interactive=True,
         params=[{"name": "subject_id", "type": "string", "required": True},
                 {"name": "predicate_id", "type": "string", "required": True},
                 {"name": "object_value", "type": "string", "required": True}],
         flags=[{"name": "str", "type": "flag", "help": "Treat object as string literal"},
                {"name": "int", "type": "flag", "help": "Treat object as integer literal"},
                {"name": "float", "type": "flag", "help": "Treat object as float literal"},
                {"name": "bool", "type": "flag", "help": "Treat object as boolean literal"},
                {"name": "lang", "type": "string", "help": "Language tag"},
                {"name": "unit", "type": "string", "help": "Unit for numeric literals"},
                {"name": "katex", "type": "string", "help": "KaTeX math expression"},
                {"name": "str-dosiero", "type": "string", "help": "Read content from file"},
                {"name": "template", "type": "string", "help": "Triple template name"}])
def cmd_triple_add(remaining: list[str], flags: dict[str, str]) -> dict:
    """Add a triple (or batch from template).

    When ``--template <name>`` is given, loads the named template from
    ``~/.config/semantika/templates/``, fills placeholders from remaining
    args / flags, and adds all triples in a batch.

    Without ``--template``, behaves as the standard single-triple add.
    """
    template_name = flags.get("template", "").strip()
    if template_name:
        return _handle_template_add(template_name, flags, remaining)

    svc = get_services()
    subject_id = flags.get("subject_id") or (remaining[0] if remaining else "") or ""
    predicate_id = flags.get("predicate_id") or (remaining[1] if len(remaining) > 1 else "") or ""
    object_value = flags.get("object_value") or (remaining[2] if len(remaining) > 2 else "") or ""
    if not subject_id or not predicate_id or not object_value:
        raise CommandValidationError("Specify subject_id, predicate_id, and object_value")
    unit = flags.get("unit", None)

    object_value, object_type, object_datatype, object_lang = _resolve_triple_type(
        object_value, flags
    )
    if object_type == "uri":
        object_value = _resolve_object_node(svc, object_value)

    try:
        triple = svc["triple"].add(
            subject_id=subject_id, predicate_id=predicate_id, object_value=object_value,
            object_type=object_type, object_lang=object_lang, object_datatype=object_datatype, object_unit=unit)
        return {"type": "status", "data": {"message": f"Added triple: {subject_id} → {predicate_id} → {object_value}", "triple": triple}}
    except ValueError as e:
        existing = svc["triple"].get_one(subject_id, predicate_id, object_value, object_type)
        if existing:
            changes = {}
            if object_lang is not None and object_lang != existing.get("object_lang"):
                changes["object_lang"] = object_lang
            if object_datatype is not None and object_datatype != existing.get("object_datatype"):
                changes["object_datatype"] = object_datatype
            if unit is not None and unit != existing.get("object_unit"):
                changes["object_unit"] = unit
            if changes:
                svc["triple"].update_metadata(subject_id, predicate_id, object_value, object_type, **changes)
                return {"type": "status", "data": {"message": "Triple already existed — metadata updated", "changes": changes}}
            return {"type": "status", "data": {"message": "Triple already exists with identical metadata"}}
        raise CommandValidationError(str(e))


@command("triple.delete", description="Delete a triple", interactive=True,
         params=[{"name": "subject", "type": "string", "required": True},
                 {"name": "predicate", "type": "string"},
                 {"name": "object", "type": "string"}])
def cmd_triple_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    """Delete a triple by ID."""
    svc = get_services()
    subject = flags.get("subject") or (remaining[0] if remaining else "") or ""
    predicate = flags.get("predicate") or (remaining[1] if len(remaining) > 1 else "") or ""
    object_val = flags.get("object") or (remaining[2] if len(remaining) > 2 else "") or ""
    if not subject:
        raise CommandValidationError("Specify a subject")
    if predicate and object_val:
        triple = _find_triple(svc, subject, predicate, object_val)
        if not triple:
            raise CommandValidationError("Triple not found")
        object_val = triple["object_value"]
        svc["proof"].cascade_delete_proofs(subject, predicate, object_val)
        svc["triple"].remove(subject_id=subject, predicate_id=predicate, object_value=object_val)
        return {"type": "status", "data": {"message": "Triple deleted"}}
    elif predicate:
        triples = svc["triple"].get_by_sp(subject, predicate)
        count = 0
        for t in triples:
            svc["proof"].cascade_delete_proofs(t["subject_id"], t["predicate_id"], t["object_value"])
            svc["triple"].remove(subject_id=t["subject_id"], predicate_id=t["predicate_id"],
                                 object_value=t["object_value"], object_type=t.get("object_type", "uri"))
            count += 1
        return {"type": "status", "data": {"message": f"Deleted {count} triple(s)"}}
    else:
        triples = svc["triple"].get_by_subject(subject)
        count = 0
        for t in triples:
            svc["proof"].cascade_delete_proofs(t["subject_id"], t["predicate_id"], t["object_value"])
            svc["triple"].remove(subject_id=t["subject_id"], predicate_id=t["predicate_id"],
                                 object_value=t["object_value"], object_type=t.get("object_type", "uri"))
            count += 1
        return {"type": "status", "data": {"message": f"Deleted {count} triple(s)"}}


@command("triple.modify", description="Modify a triple", interactive=True,
         params=[{"name": "subject", "type": "string", "required": True},
                 {"name": "predicate", "type": "string"},
                 {"name": "object", "type": "string"}],
         flags=[{"name": "new-subject", "type": "string"}, {"name": "new-predicate", "type": "string"},
                {"name": "new-object", "type": "string"}, {"name": "str", "type": "flag"},
                {"name": "int", "type": "flag"}, {"name": "float", "type": "flag"},
                {"name": "bool", "type": "flag"}, {"name": "lang", "type": "string"},
                {"name": "katex", "type": "string"}, {"name": "str-dosiero", "type": "string"}])
def cmd_triple_modify(remaining: list[str], flags: dict[str, str]) -> dict:
    """Modify a triple's predicate or object."""
    svc = get_services()
    subject = flags.get("subject") or (remaining[0] if remaining else "") or ""
    predicate = flags.get("predicate") or (remaining[1] if len(remaining) > 1 else "") or ""
    object_val = flags.get("object") or (remaining[2] if len(remaining) > 2 else "") or ""
    if not subject:
        raise CommandValidationError("Specify a subject")
    triple = _find_triple(svc, subject, predicate, object_val) if predicate and object_val else None
    if not triple:
        raise CommandValidationError("Triple not found")

    new_subject = flags.get("new_subject", None) or flags.get("new-subject", None) or triple["subject_id"]
    new_predicate = flags.get("new_predicate", None) or flags.get("new-predicate", None) or triple["predicate_id"]
    new_object_raw = flags.get("new_object", None) or flags.get("new-object", None) or triple["object_value"]
    unit = flags.get("unit", None)

    new_object, new_type, new_datatype, new_lang = _resolve_triple_type(new_object_raw, flags)
    # For modify, if no type flag was specified, preserve the original triple's type/datatype/lang
    flags_specified = any(k in flags for k in ("str", "int", "float", "bool", "katex", "str_dosiero", "str-dosiero"))
    if not flags_specified:
        new_type = triple.get("object_type", "uri")
        new_datatype = triple.get("object_datatype", None)
        new_lang = triple.get("object_lang", None)
    else:
        str_flag = _is_flag_set("str", flags)
        new_lang = flags.get("lang", None) if str_flag else triple.get("object_lang", None)

    new_unit = unit or triple.get("object_unit", None)
    noop = (triple["subject_id"] == new_subject and triple["predicate_id"] == new_predicate
            and triple["object_value"] == new_object and triple.get("object_type", "uri") == new_type
            and triple.get("object_unit") == new_unit)
    if noop:
        return {"type": "status", "data": {"message": "No change — triple remains unchanged"}}
    old_type = triple.get("object_type", "uri")
    # Migrate proofs to the new triple key instead of deleting them
    svc["proof"].migrate_proofs(
        old=(triple["subject_id"], triple["predicate_id"], triple["object_value"]),
        new=(new_subject, new_predicate, new_object),
    )
    svc["triple"].remove(subject_id=triple["subject_id"], predicate_id=triple["predicate_id"],
                         object_value=triple["object_value"], object_type=old_type)
    svc["triple"].add(subject_id=new_subject, predicate_id=new_predicate, object_value=new_object,
                      object_type=new_type, object_lang=new_lang, object_datatype=new_datatype, object_unit=new_unit)
    return {"type": "status", "data": {"message": "Triple modified"}}


# ── Template-based triple add ────────────────────────────────────────────────


def _handle_template_add(template_name: str, flags: dict[str, str], remaining: list[str]) -> dict:
    """Handle ``!triple add --template <name> ...``.

    Loads the template, fills values from flags and remaining args,
    and either executes (all params present) or returns a
    ``form-required`` response for the frontend.
    """
    from semantika.server.templates import execute_template, load_template

    tpl = load_template(template_name)
    if tpl is None:
        from semantika.server.templates import list_templates
        available = [t.name for t in list_templates()]
        raise CommandValidationError(
            f"Template '{template_name}' not found. "
            f"Available: {', '.join(available) or '(none)'}"
        )

    # Extract values from flags and remaining positional args
    values: dict[str, str] = {}
    remaining_copy = list(remaining)

    for param in tpl.params:
        val = flags.get(param.name, "")
        if not val and remaining_copy:
            val = remaining_copy.pop(0)
        if val:
            values[param.name] = val

    # Check required params
    missing = [p.name for p in tpl.params if p.required and not values.get(p.name, "").strip()]
    if missing:
        return {
            "type": "form-required",
            "data": {
                "form": f"triple-template-{template_name}",
                "templateName": template_name,
                "params": [
                    {"name": p.name, "label": p.label, "type": p.type, "required": p.required}
                    for p in tpl.params
                ],
                "initialData": values,
                "missing": missing,
                "message": f"Missing required parameters: {', '.join(missing)}",
            },
        }

    return execute_template(tpl, values)
