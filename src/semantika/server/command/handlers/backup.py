"""Command handlers for backup and restore commands."""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel

from semantika.server.command.errors import CommandValidationError
from semantika.server.command.helpers import backup_dir_abs, fmt_size, fmt_ts
from semantika.server.command.registry import command, group_command


@group_command("backup", description="Database backup and restore")
def cmd_backup_root(remaining: list[str], flags: dict[str, str]) -> dict:
    return {"type": "status", "title": "Backup Commands", "data": {
        "_summary": "Available !backup commands:\n  !backup now — Create backup\n  !backup list — List backups\n  !backup restore — Restore from latest\n  !backup prune — Delete old backups\n  !backup config — View config\n  !backup config list — List strategies\n  !backup config add — Add strategy\n  !backup config modify — Modify strategy\n  !backup config delete — Delete strategy\n  !backup export — Export data\n  !backup import — Import data"}}


@command("backup.now", description="Create timestamped backup")
def cmd_backup_now(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import (
        backup_all_strategies,
        load_config,
        resolve_target_path,
    )
    created = backup_all_strategies()
    if not created:
        return {"type": "status", "title": "Backup", "data": {"message": "No data files found to back up."}}
    cfg = load_config()
    loc_lines = ["  Local backup dir: " + backup_dir_abs()]
    for s in cfg.get("strategies", []):
        loc_lines.append(f"  {s['id']}: {resolve_target_path(s)}")
    return {"type": "status", "title": "Backup Complete", "data": {
        "message": f"Created {len(created)} backup(s).\n\nBackup location:\n" + "\n".join(loc_lines),
        "backups": [str(p) for p in created]}}


@command("backup.list", description="List available backups",
         permission_level=PermissionLevel.READ,
         flags=[{"name": "stem", "type": "string", "help": "Filter by stem"},
                {"name": "strategy", "type": "string", "help": "Filter by strategy"}])
def cmd_backup_list(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import list_backups as _list_backups
    stem = flags.get("stem")
    strategy_filter = flags.get("strategy")
    backups = _list_backups()
    if stem:
        backups = [b for b in backups if b["stem"] == stem]
    if strategy_filter:
        backups = [b for b in backups if b["strategy"] == strategy_filter]
    if not backups:
        return {"type": "status", "title": "Backups", "data": {"message": "No backups found."}}
    entries = [{"file": b["path"].name, "timestamp": fmt_ts(b["timestamp"]), "size": fmt_size(b["size_bytes"]),
                "database": b["stem"], "strategy": b.get("strategy", "legacy")} for b in backups]
    return {"type": "status", "title": f"Backups ({len(entries)})", "data": {"entries": entries}}


@command("backup.restore", description="Restore from backup",
         permission_level=PermissionLevel.DESTRUCTIVE,
         flags=[{"name": "timestamp", "type": "string", "help": "Specific timestamp"}])
def cmd_backup_restore(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import restore_by_timestamp, restore_latest
    from semantika.graph.db import close_db, get_db_path, init_db
    timestamp = flags.get("timestamp")
    close_db()
    target = str(get_db_path().parent)
    try:
        restored = restore_by_timestamp(timestamp, target) if timestamp else restore_latest(target)
    except (FileNotFoundError, LookupError, OSError) as e:
        init_db()
        raise CommandValidationError(str(e))
    init_db()
    return {"type": "status", "title": "Restore Complete", "data": {"message": f"Restored to: {restored}", "file": str(restored)}}


@command("backup.prune", description="Delete old backups",
         permission_level=PermissionLevel.DESTRUCTIVE,
         flags=[{"name": "keep", "type": "number", "help": "Number to keep"}])
def cmd_backup_prune(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import prune_backups
    raw = flags.get("keep", "")
    try:
        retention = int(raw) if raw else None
    except ValueError:
        raise CommandValidationError(f"Invalid --keep value: {raw}")
    deleted = prune_backups(retention=retention)
    return {"type": "status", "title": "Backup Pruned", "data": {"message": f"Deleted {deleted} old backup(s)."}}


@command("backup.config", description="View backup configuration")
def cmd_backup_config(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import load_config, resolve_target_path
    cfg = load_config()
    strategies = cfg.get("strategies", [])
    enabled_count = sum(1 for s in strategies if s.get("enabled", True))
    summary = f"Backup strategies: {len(strategies)} configured ({enabled_count} enabled)\n"
    for s in strategies:
        status = "✓" if s.get("enabled", True) else "✗"
        interval = s.get("interval_minutes", 0)
        sched_str = f"{interval} min" if interval > 0 else "on-demand"
        summary += f"  {status} {s['id']:12s}  {s.get('label', ''):20s}  max {s.get('max_copies', 10):3d}  target={resolve_target_path(s)}  every {sched_str}\n"
    summary += "\nUse !backup config list for interactive management."
    return {"type": "status", "title": "Backup Config", "data": {"_summary": summary}}


@command("backup.config.list", description="List backup strategies",
         permission_level=PermissionLevel.READ)
def cmd_backup_config_list(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import list_strategies, resolve_target_path
    strategies = list_strategies()
    for s in strategies:
        s["_resolved_target"] = resolve_target_path(s)
    return {"type": "status", "title": f"Backup Strategies ({len(strategies)})", "data": {"strategies": strategies}}


@command("backup.config.add", description="Add a backup strategy",
         flags=[{"name": "id", "type": "string", "required": True, "help": "Strategy ID"},
                {"name": "label", "type": "string", "help": "Human-readable label"}, {"name": "interval", "type": "number",
               "help": "Interval in minutes (0 = manual only)"},
                {"name": "max_copies", "type": "number",
               "help": "Max backup copies to keep"}, {"name": "target", "type": "string", "help": "Target path or remote URI"},
                {"name": "enabled", "type": "flag", "help": "Enable or disable this strategy"}])
def cmd_backup_config_add(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import BackupStrategy, add_strategy
    sid = flags.get("id", "")
    if not sid:
        raise CommandValidationError("Missing --id", "Usage: !backup config add --id daily --label 'Daily backups'")
    label = flags.get("label", "") or sid
    try:
        interval_minutes = int(flags.get("interval", "0"))
    except ValueError:
        raise CommandValidationError("Invalid --interval value")
    try:
        max_copies = int(flags.get("max_copies", "10"))
    except ValueError:
        raise CommandValidationError("Invalid --max-copies value")
    if interval_minutes < 0:
        raise CommandValidationError("--interval must be >= 0")
    target = flags.get("target", "local")
    enabled_raw = flags.get("enabled", "true")
    enabled = enabled_raw.lower() in ("true", "1", "yes")
    try:
        add_strategy(BackupStrategy(id=sid, label=label, interval_minutes=interval_minutes,
                                    max_copies=max_copies, target=target, enabled=enabled))
    except ValueError as e:
        raise CommandValidationError(str(e))
    return {"type": "status", "title": "Strategy Added", "data": {"strategy": sid, "message": f"Added backup strategy '{sid}'."}}


@command("backup.config.modify", description="Modify a backup strategy",
         params=[{"name": "id", "type": "string", "required": True}],
         flags=[{"name": "label", "type": "string", "help": "Human-readable label"}, {"name": "interval", "type": "number",
               "help": "Interval in minutes (0 = manual only)"},
                {"name": "max_copies", "type": "number",
               "help": "Max backup copies to keep"}, {"name": "target", "type": "string", "help": "Target path or remote URI"},
                {"name": "enabled", "type": "flag", "help": "Enable or disable this strategy"}])
def cmd_backup_config_modify(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import get_strategy, update_strategy
    if not remaining:
        raise CommandValidationError("Missing strategy id.", "Usage: !backup config modify daily --max-copies 5")
    sid = remaining[0]
    strategy = get_strategy(sid)
    if strategy is None:
        raise CommandValidationError(f"Strategy '{sid}' not found.")
    updates: dict[str, Any] = {}
    if "label" in flags: updates["label"] = flags["label"]
    if "interval" in flags:
        try: updates["interval_minutes"] = int(flags["interval"])
        except ValueError: raise CommandValidationError("Invalid interval value")
    if "max_copies" in flags: updates["max_copies"] = flags["max_copies"]
    if "target" in flags: updates["target"] = flags["target"]
    if "enabled" in flags:
        raw = flags["enabled"]
        updates["enabled"] = raw.lower() in ("true", "1", "yes") if raw else not strategy.get("enabled", True)
    if not updates:
        raise CommandValidationError("No changes specified.", "Use --label, --interval, --max-copies, --target, or --enabled.")
    try: update_strategy(sid, updates)
    except ValueError as e: raise CommandValidationError(str(e))
    return {"type": "status", "title": "Strategy Modified",
            "data": {"strategy": sid, "changed": list(updates.keys()), "message": f"Modified: {', '.join(updates.keys())}."}}


@command("backup.config.delete", description="Delete a backup strategy",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_backup_config_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import remove_strategy
    if not remaining:
        raise CommandValidationError("Missing strategy id.", "Usage: !backup config delete daily")
    sid = remaining[0]
    try: remove_strategy(sid)
    except ValueError as e: raise CommandValidationError(str(e))
    return {"type": "status", "title": "Strategy Deleted", "data": {"strategy": sid, "message": f"Deleted '{sid}'."}}


@command("backup.config.test", description="Test a backup strategy target",
         params=[{"name": "id", "type": "string", "required": True}])
def cmd_backup_config_test(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import verify_strategy_target
    if not remaining:
        raise CommandValidationError("Missing strategy id.", "Usage: !backup config test daily")
    sid = remaining[0]
    try: result = verify_strategy_target(sid)
    except ValueError as e: raise CommandValidationError(str(e))
    if result.get("success"):
        return {"type": "status", "title": "Test Passed", "data": {"message": result["message"]}}
    return {"type": "error", "title": "Test Failed",
            "data": {"message": result.get("message", ""), "error": result.get("error", "")}}


@command("backup.export", description="Export all data",
         flags=[{"name": "output", "type": "string", "help": "Output directory"}])
def cmd_backup_export(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import export_data
    output = flags.get("output", ".")
    try: export_path = export_data(output)
    except OSError as e: raise CommandValidationError(f"Export failed: {e}")
    return {"type": "status", "title": "Export Complete",
            "data": {"path": str(export_path), "message": f"Data exported to: {export_path}"}}


@command("backup.import", description="Import data from export archive",
         permission_level=PermissionLevel.DESTRUCTIVE,
         params=[{"name": "path", "type": "string", "required": True}],
         flags=[{"name": "force", "type": "flag", "help": "Force overwrite"}])
def cmd_backup_import(remaining: list[str], flags: dict[str, str]) -> dict:
    from semantika.core.backup import import_data
    from semantika.graph.db import close_db, init_db
    if not remaining:
        raise CommandValidationError("Missing export path.", "Usage: !backup import <path> [--force]")
    export_path = remaining[0]
    force = "force" in flags
    close_db()
    try: result = import_data(export_path, force=force)
    except (FileNotFoundError, ValueError, OSError) as e:
        init_db()
        raise CommandValidationError(f"Import failed: {e}")
    if result.get("imported"):
        init_db()
    imported = result.get("imported", [])
    skipped = result.get("skipped", [])
    errors = result.get("errors", [])
    msg_parts = [f"Imported {len(imported)} file(s)."]
    if skipped: msg_parts.append(f"{len(skipped)} skipped.")
    if errors: msg_parts.append(f"{len(errors)} error(s).")
    return {"type": "status", "title": "Import Complete",
            "data": {"imported": imported, "skipped": skipped, "errors": errors, "message": " ".join(msg_parts)}}
