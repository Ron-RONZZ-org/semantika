"""Context store for multi-turn prompt command flows.

Stores discovered and created entities (nodes, predicates, templates)
between turns so downstream turns can retrieve exact IDs without
relying on free-text LLM summaries.

Used by:
- ``/text-to-triples`` (3-turn flow)
- ``/template`` (2-turn flow)

Public API:
    - :func:`init_context` — create a fresh context store for a session
    - :func:`clear_context` — remove a session's context
    - :func:`get_context` — retrieve full context dict for a session
    - :func:`collect_into_context` — extract entities from a dispatch result
    - :data:`_current_context_session` — contextvar for the active session ID
"""

from __future__ import annotations

import contextvars
import json
import logging
from typing import Any

from lightercore.permissions import PermissionLevel

from semantika.server.command.registry import command

logger = logging.getLogger(__name__)

# ── Context store ──────────────────────────────────────────────────────────

# In-memory dict keyed by session_id (UUID string).
# Structure per session:
# {
#     "nodes": {"created": [{"id": str, "labels": dict}], "found": [...]},
#     "predicates": {"created": [{"id": str, "labels": dict}], "found": [...]},
#     "templates": [{"name": str, "description": str, "params": int}]
# }
_turn_contexts: dict[str, dict] = {}

# ContextVar tracks the active session ID so the context.get handler
# can look up the right store without needing per-request plumbing.
_current_context_session: contextvars.ContextVar[str | None] = (
    contextvars.ContextVar("_current_context_session", default=None)
)


def init_context(session_id: str) -> dict:
    """Create a fresh context store for *session_id* and return it."""
    ctx: dict = {
        "nodes": {"created": [], "found": []},
        "predicates": {"created": [], "found": []},
        "templates": [],
    }
    _turn_contexts[session_id] = ctx
    return ctx


def clear_context(session_id: str) -> None:
    """Remove the context store for *session_id*."""
    _turn_contexts.pop(session_id, None)


def get_context(session_id: str) -> dict:
    """Return the context dict for *session_id*, or an empty dict."""
    return _turn_contexts.get(session_id, {})


def get_filtered_context(session_id: str, type_filter: str = "all") -> dict:
    """Return context filtered by *type_filter* (nodes/predicates/templates/all)."""
    ctx = get_context(session_id)
    if not ctx:
        return {"nodes": [], "predicates": [], "templates": []}

    if type_filter == "all":
        return {
            "nodes": ctx["nodes"]["created"] + ctx["nodes"]["found"],
            "predicates": ctx["predicates"]["created"] + ctx["predicates"]["found"],
            "templates": ctx["templates"],
        }
    elif type_filter == "nodes":
        return {"nodes": ctx["nodes"]["created"] + ctx["nodes"]["found"]}
    elif type_filter == "predicates":
        return {"predicates": ctx["predicates"]["created"] + ctx["predicates"]["found"]}
    elif type_filter == "templates":
        return {"templates": ctx["templates"]}
    return {}


# ── Collect entities from dispatch results ────────────────────────────────


def _id_in(nid: str, items: list[dict]) -> bool:
    """Check if an ID already exists in a list of {id, ...} dicts."""
    return any(item.get("id") == nid for item in items)


def collect_into_context(session_id: str, path: str, result: dict) -> None:
    """Extract entities from a dispatch result and add them to the context store.

    Called by the dispatch wrapper after every tool execution in a
    multi-turn flow.  Handles:
    - ``node.add``, ``node.search``, ``node.list``
    - ``predicate.add``, ``predicate.search``, ``predicate.list``
    - ``template.list``
    """
    ctx = _turn_contexts.get(session_id)
    if ctx is None:
        return

    data = result.get("data", result)

    # ── node.add ────────────────────────────────────────────────────
    if path == "node.add":
        node = data.get("node")
        if node:
            nid = node.get("node_id", "")
            if nid and not _id_in(nid, ctx["nodes"]["created"]):
                ctx["nodes"]["created"].append({
                    "id": nid,
                    "labels": _normalise_labels(node.get("labels", {})),
                })

    # ── predicate.add ───────────────────────────────────────────────
    elif path == "predicate.add":
        pred = data.get("predicate")
        if pred:
            pid = pred.get("predicate_id", "")
            if pid and not _id_in(pid, ctx["predicates"]["created"]):
                ctx["predicates"]["created"].append({
                    "id": pid,
                    "labels": _normalise_labels(pred.get("labels", {})),
                })

    # ── node.search / node.list ─────────────────────────────────────
    elif path in ("node.search", "node.list"):
        for n in result.get("data", []):
            nid = n.get("node_id", "")
            if nid and not _id_in(nid, ctx["nodes"]["found"]):
                created_ids = {c["id"] for c in ctx["nodes"]["created"]}
                if nid not in created_ids:
                    ctx["nodes"]["found"].append({
                        "id": nid,
                        "labels": _normalise_labels(n.get("labels", {})),
                    })

    # ── predicate.search / predicate.list ───────────────────────────
    elif path in ("predicate.search", "predicate.list"):
        preds = result.get("data", [])
        for p in preds:
            pid = p.get("predicate_id", "")
            if pid and not _id_in(pid, ctx["predicates"]["found"]):
                created_ids = {c["id"] for c in ctx["predicates"]["created"]}
                if pid not in created_ids:
                    ctx["predicates"]["found"].append({
                        "id": pid,
                        "labels": _normalise_labels(p.get("labels", {})),
                    })

    # ── template.list ───────────────────────────────────────────────
    elif path == "template.list":
        for t in result.get("templates", []):
            tname = t.get("name", "")
            if tname and not any(tt["name"] == tname for tt in ctx["templates"]):
                ctx["templates"].append({
                    "name": tname,
                    "description": t.get("description", ""),
                    "params": t.get("param_count", 0),
                })


def _normalise_labels(labels: Any) -> dict:
    """Normalise labels field — could be JSON string or already a dict."""
    if isinstance(labels, str):
        try:
            return json.loads(labels)
        except (json.JSONDecodeError, TypeError):
            return {"en": labels}
    if isinstance(labels, dict):
        return labels
    return {}


# ── context.get handler ────────────────────────────────────────────────────


@command(
    "context.get",
    description="Retrieve relevant nodes, predicates, and templates from previous work",
    params=[{
        "name": "type",
        "type": "string",
        "required": True,
        "description": "What to retrieve: nodes, predicates, templates, or all",
    }],
    permission_level=PermissionLevel.READ,
)
def cmd_context_get(remaining: list[str], flags: dict[str, str]) -> dict:
    """Return structured context data for the current session.

    The LLM should call this in the triple-creation turn to retrieve
    exact node/predicate IDs instead of inventing them.
    """
    sid = _current_context_session.get()
    if not sid:
        return {
            "type": "status",
            "data": {"message": "No context available in the current session."},
        }

    type_filter = flags.get("type", "all")
    filtered = get_filtered_context(sid, type_filter)

    return {
        "type": "context",
        "data": filtered,
        "message": (
            f"Returned {sum(len(v) for v in filtered.values() if isinstance(v, list))} "
            f"item(s). Use these exact IDs in your triple creation calls."
        ),
    }
