"""Command handler for the reset command."""

from __future__ import annotations

from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command


@command("reset", description="Reset to fresh state", interactive=True,
         form_type="reset-no-backup",
         params=[{"name": "path", "type": "string"}],
         flags=[{"name": "no-backup", "type": "flag", "help": "Skip backup"},
                {"name": "confirmed", "type": "flag", "help": "Confirm reset"}])
def cmd_reset(remaining: list[str], flags: dict[str, str]) -> dict:
    has_path = bool(remaining)
    no_backup = "no-backup" in flags
    confirmed = flags.get("confirmed", "").lower() in ("true", "1", "yes")
    if not has_path and not no_backup:
        raise CommandValidationError("Provide either a backup path or --no-backup.",
                                     "Usage: !reset /path/to/backup.db   or   !reset --no-backup")
    if has_path and no_backup:
        raise CommandValidationError("Cannot specify both a backup path and --no-backup.",
                                     "Use either !reset <path> to backup first, or !reset --no-backup to skip backup.")
    if no_backup and not confirmed:
        return {"type": "form-required", "title": "Confirm Reset", "data": {
            "form": "reset-no-backup",
            "message": "This will permanently delete ALL your Semantika data — nodes, predicates, triples, reviews, proofs, and unit ontology. This action CANNOT be undone."}}
    from semantika.core.reset import reset_to_fresh_state
    try:
        backup_path = remaining[0] if remaining else None
        result = reset_to_fresh_state(backup_path=backup_path)
    except (FileNotFoundError, OSError) as e:
        raise CommandValidationError(f"Reset failed: {e}")
    msg_parts = ["Semantika has been reset to a fresh state."]
    if result.get("backup_path"):
        msg_parts.append(f"Backup saved to: {result['backup_path']}")
    msg_parts.append(f"Databases removed: {len(result.get('databases_removed', []))}")
    msg_parts.append(f"Credentials cleared: {result.get('credentials_cleared', 0)}")
    return {"type": "status", "title": "Reset Complete", "data": {"message": " ".join(msg_parts), **result}}
