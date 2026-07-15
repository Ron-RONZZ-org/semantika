"""Command handlers for review and proof commands."""

from __future__ import annotations

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command

# ── Review commands ───────────────────────────────────────────────────────


@command("review.start", description="Start a review session",
         params=[{"name": "mode", "type": "string", "default": "view"}],
         flags=[{"name": "date_from", "type": "string", "help": "Start date"},
                {"name": "date_to", "type": "string", "help": "End date"},
                {"name": "limit", "type": "number", "help": "Max questions"}])
def cmd_review_start(remaining: list[str], flags: dict[str, str]) -> dict:
    """Start a new review session."""
    svc = get_services()
    mode = flags.get("mode") or (remaining[0] if remaining else "") or "view"
    if mode not in ("view", "quiz"):
        raise CommandValidationError("Mode must be 'view' or 'quiz'")
    date_from = flags.get("date_from")
    date_to = flags.get("date_to")
    raw_limit = flags.get("limit", "10")
    try:
        limit = int(raw_limit)
    except ValueError:
        raise CommandValidationError(f"Invalid limit value: {raw_limit}")
    session = svc["review"].create_session(mode=mode, date_from=date_from, date_to=date_to, limit=limit)
    if mode == "quiz":
        return {"type": "quiz", "title": "Quiz", "data": session}
    return {"type": "status", "data": session}


@command("review.sessions", description="List review sessions",
         permission_level=PermissionLevel.READ)
def cmd_review_sessions(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all review sessions."""
    svc = get_services()
    sessions = svc["review"].list_sessions()
    return {"type": "table", "data": sessions, "label": "Review Sessions"}


@command("review.view", description="View a review session",
         permission_level=PermissionLevel.READ,
         params=[{"name": "uuid", "type": "string", "required": True}])
def cmd_review_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View a review session by ID."""
    svc = get_services()
    session_uuid = flags.get("uuid") or (remaining[0] if remaining else "") or ""
    if not session_uuid:
        raise CommandValidationError("Specify a session UUID")
    session = svc["review"].get_session(session_uuid, enrich=True)
    if not session:
        raise CommandValidationError(f"Session not found: {session_uuid}")
    return {"type": "status", "data": session}


@command("review.delete", description="Delete a review session",
         params=[{"name": "uuid", "type": "string", "required": True}])
def cmd_review_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    """Delete a review session."""
    svc = get_services()
    session_uuid = flags.get("uuid") or (remaining[0] if remaining else "") or ""
    if not session_uuid:
        raise CommandValidationError("Specify a session UUID")
    svc["review"].delete_session(session_uuid)
    return {"type": "status", "data": {"message": f"Deleted session {session_uuid}"}}


# ── Proof commands ────────────────────────────────────────────────────────


@command("proof.add", description="Add a proof to a triple", interactive=True,
         params=[{"name": "subject_id", "type": "string", "required": True,
                  "placeholder": "ALICE or ALI (node ID prefix)"},
                 {"name": "predicate_id", "type": "string", "required": True,
                  "placeholder": "ex:knows or know (predicate ID)"},
                 {"name": "object_value", "type": "string", "required": True,
                  "placeholder": "BOB (node ID) or \"a literal\""}],
         flags=[{"name": "proof_type", "type": "string",
                 "help": "Type of proof (e.g. observation, citation, experiment)",
                 "placeholder": "observation"},
                {"name": "source", "type": "string",
                 "help": "Source citation (URL or reference)",
                 "placeholder": "https://doi.org/10.1234/example"},
                {"name": "notes", "type": "string",
                 "help": "Additional notes about this proof",
                 "placeholder": "This was verified by experiment X"}])
def cmd_proof_add(remaining: list[str], flags: dict[str, str]) -> dict:
    """Add a proof (justification) for a triple."""
    svc = get_services()
    subject_id = flags.get("subject_id") or (remaining[0] if remaining else "") or ""
    predicate_id = flags.get("predicate_id") or (remaining[1] if len(remaining) > 1 else "") or ""
    object_value = flags.get("object_value") or (remaining[2] if len(remaining) > 2 else "") or ""
    if not subject_id or not predicate_id or not object_value:
        raise CommandValidationError("Specify subject_id, predicate_id, and object_value")
    subj_node = svc["node"].resolve_node_id_prefix(subject_id)
    if subj_node:
        subject_id = subj_node["node_id"]
    obj_node = svc["node"].resolve_node_id_prefix(object_value)
    if obj_node:
        object_value = obj_node["node_id"]
    proof_data = {"subject_id": subject_id, "predicate_id": predicate_id, "object_value": object_value,
                  "proof_type": flags.get("proof_type", "observation"), "source": flags.get("source", ""),
                  "notes": flags.get("notes", "")}
    proof = svc["proof"].create(proof_data)
    return {"type": "status", "data": {"message": f"Created proof {proof['uuid']}", "proof": proof}}


@command("proof.view", description="View proofs for a triple",
         permission_level=PermissionLevel.READ,
         params=[{"name": "subject_id", "type": "string", "required": True},
                 {"name": "predicate_id", "type": "string", "required": True},
                 {"name": "object_value", "type": "string", "required": True}])
def cmd_proof_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View proofs for a triple."""
    svc = get_services()
    subject_id = flags.get("subject_id") or (remaining[0] if remaining else "") or ""
    predicate_id = flags.get("predicate_id") or (remaining[1] if len(remaining) > 1 else "") or ""
    object_value = flags.get("object_value") or (remaining[2] if len(remaining) > 2 else "") or ""
    if not subject_id or not predicate_id or not object_value:
        raise CommandValidationError("Specify subject_id, predicate_id, and object_value")
    subj_node = svc["node"].resolve_node_id_prefix(subject_id)
    if subj_node:
        subject_id = subj_node["node_id"]
    obj_node = svc["node"].resolve_node_id_prefix(object_value)
    if obj_node:
        object_value = obj_node["node_id"]
    proofs = svc["proof"].get_by_triple(subject_id, predicate_id, object_value)
    return {"type": "table", "data": proofs, "label": "Proofs"}


@command("proof.delete", description="Delete a proof",
         params=[{"name": "uuid", "type": "string", "required": True}])
def cmd_proof_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    """Delete a proof."""
    svc = get_services()
    proof_uuid = flags.get("uuid") or (remaining[0] if remaining else "") or ""
    if not proof_uuid:
        raise CommandValidationError("Specify a proof UUID")
    svc["proof"].delete(proof_uuid)
    return {"type": "status", "data": {"message": f"Deleted proof {proof_uuid}"}}
