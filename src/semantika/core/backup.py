"""Timestamped, checksum-verified database backups for Semantika.

Semantika uses a single SQLite database (``semantika.db``).  Backup
uses SQLite's native online backup API, which produces a consistent
snapshot even while the database is in use.

Backup location::

    ~/.local/share/semantika/.backups/semantika_{strategy}_{timestamp}.db

Multiple backup strategies are supported — each strategy defines a
retention limit (max copies) and an optional external target directory.
Strategies are stored in ``~/.config/semantika/backup.json``.

Export/Import creates a portable timestamped directory::

    export-{timestamp}/
        semantika.db     # SQLite database copy
        manifest.json    # Metadata + SHA-256 checksums

Ported from lighterbird's backup module, simplified for single-DB use.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from semantika.core.paths import config_dir, data_dir

# ── Constants ──────────────────────────────────────────────────────────────

_BACKUP_SUBDIR = ".backups"
_BACKUP_CONFIG_FILE = "backup.json"
_DEFAULT_MAX_COPIES = 10
_CONFIG_VERSION = 3
_DB_FILENAME = "semantika.db"


# ── Strategy dataclass ─────────────────────────────────────────────────────


@dataclass
class BackupStrategy:
    """A named backup policy.

    Attributes:
        id: Unique kebab-case identifier (e.g. ``"daily"``, ``"hourly"``).
        label: Human-readable name for display.
        interval_minutes: How often to auto-backup in minutes.
            0 means on-demand (only via ``!backup now``).
        max_copies: Maximum number of backups to keep per database stem.
        target: ``"local"`` (default backup dir) or an absolute path to
            an external/synced directory.
        enabled: Whether this strategy is active.
        last_backup_at: ISO-8601 timestamp of the last successful backup,
            or empty string if never backed up.
    """
    id: str
    label: str
    interval_minutes: int = 0
    max_copies: int = _DEFAULT_MAX_COPIES
    target: str = "local"
    enabled: bool = True
    last_backup_at: str = ""


# ── Internal helpers ───────────────────────────────────────────────────────


def _backup_dir() -> Path:
    """Return the root backup directory (``data_dir() / ".backups"``)."""
    return data_dir() / _BACKUP_SUBDIR


def resolve_target_path(strategy: dict[str, Any]) -> str:
    """Resolve a strategy's target to an absolute path.

    ``"local"`` is resolved to the default backup directory.
    """
    target = strategy.get("target", "local")
    if target == "local" or not target:
        return str(_backup_dir())
    return str(Path(target).expanduser().resolve())


def _timestamp() -> str:
    """Return a sortable ISO-like timestamp string (microsecond precision).

    Format: ``YYYYMMDDTHHMMSSuuuuuu`` — no colons, spaces, or
    characters unsafe for filenames.
    """
    t = time.time_ns()
    secs = t // 1_000_000_000
    nsec = t % 1_000_000_000
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime(secs)) + f"{nsec // 1000:06d}"


def _sha256(path: Path) -> str:
    """Compute the SHA-256 hex digest of *path* (8 KiB buffered)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _db_path() -> Path:
    """Return the path to the Semantika database file."""
    return data_dir() / _DB_FILENAME


def _checkpoint_db() -> None:
    """Force-checkpoint the WAL into the main database file.

    Uses SQLite's wal_checkpoint(TRUNCATE) to flush all pending WAL
    data to the main ``.db`` file before backing it up.
    """
    import sqlite3

    p = _db_path()
    if not p.exists():
        return
    try:
        conn = sqlite3.connect(str(p), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except sqlite3.Error:
        pass  # best-effort


def _copy_with_verify(src: Path, dst: Path) -> Path:
    """Copy *src* to *dst* and verify SHA-256 checksum matches.

    Raises:
        OSError: If the checksum verification fails (the copy is
            removed on error).
    """
    src_checksum = _sha256(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    dst_checksum = _sha256(dst)
    if dst_checksum != src_checksum:
        dst.unlink(missing_ok=True)
        raise OSError(
            f"Checksum mismatch for {src.name}: "
            f"source {src_checksum[:12]} != copy {dst_checksum[:12]}"
        )
    return dst


# ── Backup file naming / parsing ───────────────────────────────────────────

_BACKUP_FILE_RE = re.compile(
    r"^(.+?)_([a-z][a-z0-9-]*?)_(\d{8}T\d{12})\.(db|bak|zip)$"
)
_LEGACY_BACKUP_FILE_RE = re.compile(
    r"^(.+?)_(\d{8}T\d{12})\.(db|bak)$"
)


def _parse_backup_filename(name: str) -> dict[str, str] | None:
    """Parse a backup filename into its components.

    Returns ``None`` if the name doesn't match expected patterns.
    """
    m = _BACKUP_FILE_RE.match(name)
    if m:
        return {
            "stem": m.group(1),
            "strategy": m.group(2),
            "timestamp": m.group(3),
            "suffix": m.group(4),
        }
    m = _LEGACY_BACKUP_FILE_RE.match(name)
    if m:
        return {
            "stem": m.group(1),
            "strategy": "legacy",
            "timestamp": m.group(2),
            "suffix": m.group(3),
        }
    return None


def _backup_filename(stem: str, strategy_id: str, ts: str) -> str:
    """Build a strategy-aware backup filename."""
    return f"{stem}_{strategy_id}_{ts}.db"


# ── Strategy CRUD ──────────────────────────────────────────────────────────


def _config_path() -> Path:
    """Return path to the backup config JSON file."""
    return config_dir() / _BACKUP_CONFIG_FILE


def _migrate_old_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate v1/v2 config to current strategy-based format."""
    version = raw.get("version", 1)

    if version < 2:
        # v1: flat → strategy-based
        strategy = BackupStrategy(
            id="default",
            label="Default",
            max_copies=int(raw.get("retention", _DEFAULT_MAX_COPIES)),
            target=raw.get("external_dir", "") or "local",
        )
        return {"version": _CONFIG_VERSION, "strategies": [asdict(strategy)]}

    # v2 → v3: schedule → interval_minutes
    strategies = raw.get("strategies", [])
    for s in strategies:
        sched = s.pop("schedule", "manual")
        if sched == "manual":
            s["interval_minutes"] = 0
        elif sched == "hourly":
            s["interval_minutes"] = 60
        elif sched == "daily":
            s["interval_minutes"] = 1440
        elif sched == "weekly":
            s["interval_minutes"] = 10080
        else:
            s["interval_minutes"] = 0
        s.setdefault("last_backup_at", "")
    return {"version": _CONFIG_VERSION, "strategies": strategies}


def load_config() -> dict[str, Any]:
    """Load backup configuration.

    Returns:
        Dict with keys:

        - **version** (:class:`int`) — Config format version.
        - **strategies** (:class:`list`) — List of strategy dicts.
    """
    defaults: dict[str, Any] = {
        "version": _CONFIG_VERSION,
        "strategies": [asdict(BackupStrategy(id="default", label="Default"))],
    }
    path = _config_path()
    if not path.exists():
        return dict(defaults)
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(defaults)

    version = raw.get("version", 1)
    needs_migrate = (
        version < _CONFIG_VERSION
        or "external_dir" in raw
        or "retention" in raw
        or any("schedule" in s for s in raw.get("strategies", []))
    )
    if needs_migrate:
        raw = _migrate_old_config(raw)
        save_config(raw)
        return raw

    for s in raw.get("strategies", []):
        s.setdefault("interval_minutes", 0)
        s.setdefault("max_copies", _DEFAULT_MAX_COPIES)
        s.setdefault("target", "local")
        s.setdefault("enabled", True)
        s.setdefault("last_backup_at", "")

    return raw


def save_config(cfg: dict[str, Any]) -> None:
    """Save backup configuration to disk.

    Args:
        cfg: Dict with ``version`` and ``strategies`` keys.

    Raises:
        ValueError: If the config is malformed.
    """
    strategies = cfg.get("strategies", [])
    if not isinstance(strategies, list):
        raise ValueError("'strategies' must be a list")

    seen_ids: set[str] = set()
    for s in strategies:
        if not isinstance(s, dict):
            raise ValueError(f"Each strategy must be a dict, got {type(s).__name__}")
        sid = s.get("id", "")
        if not sid or not isinstance(sid, str):
            raise ValueError("Each strategy must have a non-empty string 'id'")
        if not re.match(r"^[a-z][a-z0-9-]*$", sid):
            raise ValueError(
                f"Strategy id '{sid}' must match [a-z][a-z0-9-]*"
            )
        if sid in seen_ids:
            raise ValueError(f"Duplicate strategy id: {sid}")
        seen_ids.add(sid)

        if not isinstance(s.get("label", ""), str):
            raise ValueError(f"Strategy '{sid}': 'label' must be a string")
        try:
            interval = int(s.get("interval_minutes", 0))
        except (TypeError, ValueError):
            raise ValueError(f"Strategy '{sid}': 'interval_minutes' must be an integer")
        if interval < 0:
            raise ValueError(f"Strategy '{sid}': 'interval_minutes' must be >= 0")
        s["interval_minutes"] = interval
        try:
            max_copies = int(s.get("max_copies", _DEFAULT_MAX_COPIES))
        except (TypeError, ValueError):
            raise ValueError(f"Strategy '{sid}': 'max_copies' must be an integer")
        if max_copies < 1:
            raise ValueError(f"Strategy '{sid}': 'max_copies' must be >= 1")
        s["max_copies"] = max_copies
        s.setdefault("target", "local")
        if not isinstance(s["target"], str):
            raise ValueError(f"Strategy '{sid}': 'target' must be a string")
        s["enabled"] = bool(s.get("enabled", True))
        s.setdefault("last_backup_at", "")

    cfg["version"] = _CONFIG_VERSION
    cfg["strategies"] = strategies

    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def list_strategies() -> list[dict[str, Any]]:
    """Return the list of strategy dicts (from config)."""
    cfg = load_config()
    return cfg.get("strategies", [])


def get_strategy(strategy_id: str) -> dict[str, Any] | None:
    """Return a single strategy dict by id, or ``None``."""
    for s in list_strategies():
        if s["id"] == strategy_id:
            return s
    return None


def add_strategy(strategy: BackupStrategy) -> dict[str, Any]:
    """Add a new backup strategy.

    Args:
        strategy: The strategy to add.

    Returns:
        The saved strategy dict.

    Raises:
        ValueError: If the id already exists.
    """
    cfg = load_config()
    for s in cfg["strategies"]:
        if s["id"] == strategy.id:
            raise ValueError(f"Strategy '{strategy.id}' already exists")
    s_dict = asdict(strategy)
    cfg["strategies"].append(s_dict)
    save_config(cfg)
    return s_dict


def update_strategy(strategy_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update fields on an existing strategy.

    Args:
        strategy_id: The strategy id to update.
        updates: Dict of fields to change.

    Returns:
        The updated strategy dict.

    Raises:
        ValueError: If the strategy is not found, or updates are invalid.
    """
    cfg = load_config()
    for s in cfg["strategies"]:
        if s["id"] == strategy_id:
            if "label" in updates:
                raw = updates.get("label", "")
                if not isinstance(raw, str) or not raw.strip():
                    raise ValueError("'label' must be a non-empty string")
                s["label"] = updates["label"].strip()
            if "interval_minutes" in updates:
                try:
                    im = int(updates["interval_minutes"])
                except (TypeError, ValueError):
                    raise ValueError("'interval_minutes' must be an integer")
                if im < 0:
                    raise ValueError("'interval_minutes' must be >= 0")
                s["interval_minutes"] = im
            if "max_copies" in updates:
                try:
                    mc = int(updates["max_copies"])
                except (TypeError, ValueError):
                    raise ValueError("'max_copies' must be an integer")
                if mc < 1:
                    raise ValueError("'max_copies' must be >= 1")
                s["max_copies"] = mc
            if "target" in updates:
                if not isinstance(updates["target"], str):
                    raise ValueError("'target' must be a string")
                s["target"] = updates["target"]
            if "enabled" in updates:
                s["enabled"] = bool(updates["enabled"])
            save_config(cfg)
            return s
    raise ValueError(f"Strategy '{strategy_id}' not found")


def remove_strategy(strategy_id: str) -> None:
    """Remove a backup strategy by id.

    Existing backup files tagged with this strategy are NOT deleted.

    Args:
        strategy_id: The strategy id to remove.

    Raises:
        ValueError: If the strategy is not found.
    """
    cfg = load_config()
    before = len(cfg["strategies"])
    cfg["strategies"] = [s for s in cfg["strategies"] if s["id"] != strategy_id]
    if len(cfg["strategies"]) == before:
        raise ValueError(f"Strategy '{strategy_id}' not found")
    save_config(cfg)


# ── Public API: Backup ─────────────────────────────────────────────────────


def backup_database(strategy: dict[str, Any] | None = None) -> Path | None:
    """Create a SQLite backup of the Semantika database.

    Uses ``SemantikaDB.backup()`` which performs an online backup,
    guaranteeing a consistent snapshot.

    The backup file is stored at::

        {backup_dir}/{stem}_{strategy[id]}_{timestamp}.db

    After a successful copy, old backups for this strategy are
    pruned according to the strategy's ``max_copies``.

    Args:
        strategy: Strategy dict (from config). If ``None``, uses
            the first enabled strategy or a default.

    Returns:
        Path to the created backup file, or ``None`` if the DB does
        not exist.
    """
    dbp = _db_path()
    if not dbp.exists():
        return None

    if strategy is None:
        strategies = list_strategies()
        strategy = next(
            (s for s in strategies if s.get("enabled", True)),
            {"id": "default", "max_copies": _DEFAULT_MAX_COPIES, "target": "local"},
        )

    # Flush WAL → main DB via a temporary connection
    _checkpoint_db()

    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = _timestamp()
    stem = dbp.stem
    strategy_id = strategy["id"]
    backup_path = backup_dir / _backup_filename(stem, strategy_id, ts)

    # Use SQLite's native backup API for a consistent snapshot
    import sqlite3

    dest = sqlite3.connect(str(backup_path))
    try:
        src = sqlite3.connect(str(dbp), timeout=5.0)
        try:
            src.backup(dest)
        finally:
            src.close()
    finally:
        dest.close()

    # Prune old backups for this (stem, strategy)
    _prune_for_stem_and_strategy(stem, strategy_id, retention=strategy["max_copies"])

    # Copy to external target if configured
    target = strategy.get("target", "local")
    if target and target != "local":
        try:
            dst_root = Path(target).expanduser().resolve()
            dst_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup_path), str(dst_root / backup_path.name))
        except OSError:
            pass  # best-effort external copy

    # Update last_backup_at in config
    try:
        cfg = load_config()
        for s in cfg["strategies"]:
            if s["id"] == strategy_id:
                s["last_backup_at"] = datetime.now(timezone.utc).isoformat()
                save_config(cfg)
                break
    except (OSError, ValueError):
        pass

    return backup_path


def backup_all_strategies() -> list[Path]:
    """Backup the database for every enabled strategy.

    Returns:
        List of backup file paths created.
    """
    created: list[Path] = []
    strategies = list_strategies()
    enabled = [s for s in strategies if s.get("enabled", True)]

    for strategy in enabled:
        result = backup_database(strategy)
        if result is not None:
            created.append(result)

    return created


def verify_strategy_target(strategy_id: str) -> dict[str, Any]:
    """Test a backup strategy by verifying the target is writable.

    Args:
        strategy_id: The strategy id to test.

    Returns:
        Dict with keys: **success** (:class:`bool`), **message**
        (:class:`str`), optional **error** (:class:`str`).

    Raises:
        ValueError: If the strategy is not found.
    """
    strategy = get_strategy(strategy_id)
    if strategy is None:
        raise ValueError(f"Strategy '{strategy_id}' not found")

    target = strategy.get("target", "local")
    try:
        if target == "local":
            bdir = _backup_dir()
            bdir.mkdir(parents=True, exist_ok=True)
            probe = bdir / f".probe_{_timestamp()}.tmp"
            probe.write_text("probe")
            probe.unlink()
            location = str(bdir)
        else:
            dst = Path(target).expanduser().resolve()
            dst.mkdir(parents=True, exist_ok=True)
            probe = dst / f".probe_{_timestamp()}.tmp"
            probe.write_text("probe")
            probe.unlink()
            location = str(dst)

        return {"success": True, "message": f"Target is writable: {location}"}
    except OSError as e:
        return {
            "success": False,
            "message": f"Target is NOT writable: {target}",
            "error": str(e),
        }


# ── Public API: List, Restore, Prune ───────────────────────────────────────


def list_backups() -> list[dict[str, Any]]:
    """List available backup files, newest first.

    Returns:
        A list of dicts, each with keys: **path** (:class:`Path`),
        **timestamp** (:class:`str`), **size_bytes** (:class:`int`),
        **stem** (:class:`str`), **strategy** (:class:`str`).
    """
    bdir = _backup_dir()
    if not bdir.is_dir():
        return []

    backups: list[dict[str, Any]] = []
    for p in sorted(bdir.iterdir(), reverse=True):
        if p.suffix not in (".db", ".bak", ".zip"):
            continue
        parsed = _parse_backup_filename(p.name)
        if parsed is None:
            continue
        backups.append({
            "path": p,
            "timestamp": parsed["timestamp"],
            "size_bytes": p.stat().st_size,
            "stem": parsed["stem"],
            "strategy": parsed["strategy"],
        })

    return backups


def restore_latest(target_dir: str | Path) -> Path:
    """Restore the newest backup of the Semantika database.

    Args:
        target_dir: Directory to restore the DB into.

    Returns:
        Path to the restored database file.

    Raises:
        FileNotFoundError: If no backups exist.
        OSError: If restore verification fails.
    """
    dst_dir = Path(target_dir)
    backups = [b for b in list_backups() if b["stem"] == "semantika"]
    if not backups:
        raise FileNotFoundError("No backups found for semantika.db")

    newest = backups[0]
    src_path: Path = newest["path"]
    dst_path = dst_dir / _DB_FILENAME

    _copy_with_verify(src_path, dst_path)
    return dst_path


def restore_by_timestamp(timestamp_prefix: str, target_dir: str | Path) -> Path:
    """Restore a backup matching a timestamp prefix.

    Accepts partial timestamps — e.g. ``"20260704"`` matches
    ``"20260704T120000"``.

    Args:
        timestamp_prefix: ISO timestamp prefix (may be partial).
        target_dir: Directory to restore into.

    Returns:
        Path to the restored database file.

    Raises:
        FileNotFoundError: If no backup matches.
        LookupError: If multiple backups match the same stem.
    """
    dst_dir = Path(target_dir)
    normalized = "".join(c for c in timestamp_prefix if c.isalnum()).lower()

    all_backups = [b for b in list_backups() if b["stem"] == "semantika"]
    matches = [b for b in all_backups if normalized in b["timestamp"].lower()]

    if not matches:
        raise FileNotFoundError(
            f"No backup matches timestamp prefix '{timestamp_prefix}'"
        )

    # If multiple matches for same stem, pick the closest (lexicographically)
    if len(matches) > 1:
        matches.sort(key=lambda b: b["timestamp"], reverse=True)

    src_path: Path = matches[0]["path"]
    dst_path = dst_dir / _DB_FILENAME

    _copy_with_verify(src_path, dst_path)
    return dst_path


def prune_backups(*, retention: int | None = None) -> int:
    """Prune old backups, keeping the newest *retention* per (stem, strategy).

    Args:
        retention: Number of newest backups to keep per group.
            If ``None``, uses each strategy's ``max_copies``.

    Returns:
        Number of backup files deleted.
    """
    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0

    by_group: dict[tuple[str, str], list[Path]] = {}
    for p in sorted(bdir.iterdir(), reverse=True):
        if p.suffix not in (".db", ".bak", ".zip"):
            continue
        parsed = _parse_backup_filename(p.name)
        if parsed is None:
            continue
        key = (parsed["stem"], parsed["strategy"])
        by_group.setdefault(key, []).append(p)

    strategies = {s["id"]: s["max_copies"] for s in list_strategies()}

    deleted = 0
    for (stem, sid), files in by_group.items():
        max_keep = retention
        if max_keep is None:
            max_keep = strategies.get(sid, _DEFAULT_MAX_COPIES)
        if len(files) <= max_keep:
            continue
        for p in files[max_keep:]:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass

    return deleted


def _prune_for_stem_and_strategy(
    stem: str,
    strategy_id: str,
    *,
    retention: int,
) -> int:
    """Prune backups for a specific (stem, strategy) combination."""
    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0

    prefix = f"{stem}_{strategy_id}_"
    files = sorted(
        [p for p in bdir.iterdir() if p.suffix == ".db" and p.stem.startswith(prefix)],
        reverse=True,
    )
    if len(files) <= retention:
        return 0

    deleted = 0
    for p in files[retention:]:
        try:
            p.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted


# ── Public API: Export / Import ────────────────────────────────────────────


def _export_manifest_entry(path: Path, rel: str) -> dict[str, Any]:
    """Create a manifest entry for *path* with size and SHA-256."""
    return {
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def export_data(output_dir: str | Path) -> Path:
    """Export the Semantika database to a portable zip archive.

    Creates a timestamped zip file containing::

        export-{timestamp}.zip
            semantika.db
            manifest.json
            backup.json      # Backup strategy config (if exists)

    Args:
        output_dir: Parent directory for the export zip.

    Returns:
        Path to the created zip file.
    """
    dst_root = Path(output_dir).expanduser().resolve()
    dst_root.mkdir(parents=True, exist_ok=True)

    # Flush WAL → main DB before exporting
    _checkpoint_db()

    ts = _timestamp()
    zip_path = dst_root / f"export-{ts}.zip"

    manifest: dict[str, Any] = {
        "exported_at": ts,
        "files": {},
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add the database file
        dbp = _db_path()
        if dbp.exists():
            zf.write(str(dbp), _DB_FILENAME)
            manifest["files"][_DB_FILENAME] = _export_manifest_entry(dbp, _DB_FILENAME)

        # Add backup config if exists
        bcp = _config_path()
        if bcp.exists():
            rel = "config/backup.json"
            zf.write(str(bcp), rel)
            manifest["files"][rel] = _export_manifest_entry(bcp, rel)

        # Write manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return zip_path


def import_data(
    zip_path: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Import data from a previously exported zip archive.

    Args:
        zip_path: Path to an export zip (must contain ``manifest.json``).
        force: If True, overwrite existing files without prompting.

    Returns:
        Dict with keys:
        - **imported** (:class:`list`) — names of files imported.
        - **skipped** (:class:`list`) — names of files skipped.
        - **errors** (:class:`list`) — names of files that failed.

    Raises:
        FileNotFoundError: If *zip_path* does not exist.
        ValueError: If the manifest is malformed.
    """
    src = Path(zip_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Export zip not found: {zip_path}")

    dst_data = data_dir()

    result: dict[str, Any] = {"imported": [], "skipped": [], "errors": []}

    with zipfile.ZipFile(src, "r") as zf:
        # Read manifest
        try:
            manifest_data = zf.read("manifest.json")
            manifest = json.loads(manifest_data)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid or missing manifest.json: {e}") from e

        # Determine extraction temp dir
        with tempfile.TemporaryDirectory(prefix="semantika-import-") as tmp:
            zf.extractall(tmp)
            tmp_path = Path(tmp)

            # Verify SHA-256 for each file in manifest
            for rel_path_str, file_info in manifest.get("files", {}).items():
                src_file = tmp_path / rel_path_str
                if not src_file.exists():
                    result["errors"].append(f"{rel_path_str} (not found in archive)")
                    continue

                expected_sha = file_info.get("sha256", "")
                if expected_sha:
                    actual_sha = _sha256(src_file)
                    if actual_sha != expected_sha:
                        result["errors"].append(
                            f"{rel_path_str} (SHA-256 mismatch)"
                        )
                        if not force:
                            continue

                # Determine destination
                if rel_path_str.startswith("config/"):
                    rel_suffix = rel_path_str[len("config/"):]
                    dst_file = config_dir() / rel_suffix
                else:
                    dst_file = dst_data / rel_path_str

                # Check if destination exists
                if dst_file.exists() and not force:
                    # Compare content
                    try:
                        if _sha256(dst_file) == _sha256(src_file):
                            result["skipped"].append(rel_path_str)
                            continue
                    except OSError:
                        pass
                    # For the DB file, always import if force is set
                    if not force:
                        result["skipped"].append(
                            f"{rel_path_str} (exists; use --force to overwrite)"
                        )
                        continue

                try:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    _copy_with_verify(src_file, dst_file)
                    result["imported"].append(rel_path_str)
                except OSError as e:
                    result["errors"].append(f"{rel_path_str} ({e})")

    return result


__all__ = [
    "BackupStrategy",
    "add_strategy",
    "backup_all_strategies",
    "backup_database",
    "export_data",
    "get_strategy",
    "import_data",
    "list_backups",
    "list_strategies",
    "load_config",
    "prune_backups",
    "remove_strategy",
    "resolve_target_path",
    "restore_by_timestamp",
    "restore_latest",
    "save_config",
    "update_strategy",
    "verify_strategy_target",
]
