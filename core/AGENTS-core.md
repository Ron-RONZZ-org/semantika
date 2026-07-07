# AGENTS-core.md — Core Module Agent Instructions

## Summary
Re-exports from lightercore with local extensions: database connection management, FTS5 configuration, file paths, CRUD base class, backup, permissions, reset.

## Source of Code
This module **does not** vend its own code — it re-exports from lightercore and adds only Semantika-specific additions:
- `db.py` / `exceptions.py` / `paths.py` / `crud.py` / `backup.py` / `fts.py` — thin re-exports from `lightercore.core.*`
- `reset.py` — Semantika-specific reset logic (not in lightercore)

The authoritative source for shared infrastructure is **[lightercore](../lightercore)**.

## Re-exported from lightercore

| File | Source | Purpose |
|------|--------|---------|
| `db.py` | `lightercore.core.db` | `SQLiteDB` connection manager with WAL mode, transaction context manager, retry logic |
| `paths.py` | `lightercore.core.paths` | XDG-compliant data/config directory resolution |
| `exceptions.py` | `lightercore.core.exceptions` | Base exception classes |
| `crud.py` | `lightercore.core.crud` | `CRUDService` base class with standard CRUD + soft-delete pattern |
| `backup.py` | `lightercore.core.backup` | Multi-strategy backup, restore, prune, export/import |
| `fts.py` | `lightercore.core.fts` | `FTSConfig` for FTS5 virtual table setup |

### Additional: `reset.py`
- Resets the knowledge graph to a fresh state (drops and recreates tables)
- Optionally creates a backup before resetting
- Uses `@command` decorator with `permission_level=PermissionLevel.DESTRUCTIVE`

## Constraints and Invariants
- All DB connections use WAL mode
- All files under 500 lines
- No imports from A-ecosystem packages — use lightercore instead
- Transactions via `with self.db.transaction():`

## Input/Output Expectations
- All public functions have type hints
- DB functions raise `sqlite3.Error` subclasses on failure (not bare `Exception`)
- Path functions use `pathlib.Path` throughout

## Documentation Reference
- See lightercore source in `../lightercore/` for upstream reference
- `lightercore.llm` for LLM provider config, profiles, keyring persistence
- `lightercore.prompt_commands` for file-based prompt command loader/expander
- `lightercore.permissions` for `PermissionLevel` enum
- `lightercore.paths` for `data_dir()` and `config_dir()`

## Domain-Specific Rules for Agents
- When adding new DB features, match the existing pattern (context manager, retry, WAL)
- Do NOT add encryption or keyring features here — Semantika is local-only
- Schema migrations follow the `init_db()` pattern with version checks
- Prefer adding features to lightercore if they are shared infrastructure; keep Semantika-specific logic in `reset.py` or the `server/` module
- Path resolution: use `lightercore.paths.data_dir()` for data files, `lightercore.paths.config_dir()` for config files (prompt commands go in `config_dir() / "commands"`)

## Lightercore Modules Used by Semantika

| lightercore Module | Used By | Purpose |
|--------------------|---------|---------|
| `lightercore.core.db` | `semantika.core.db` | DB connection manager |
| `lightercore.core.paths` | `semantika.core.paths` | XDG paths |
| `lightercore.core.exceptions` | `semantika.core.exceptions` | Base exceptions |
| `lightercore.core.crud` | `semantika.core.crud` | CRUD base class |
| `lightercore.core.backup` | `semantika.core.backup` | Backup strategies |
| `lightercore.core.fts` | `semantika.core.fts` | FTS5 setup |
| `lightercore.llm` | `semantika.server.llm.provider` | LLM provider, config, profiles |
| `lightercore.prompt_commands` | `semantika.server.routes.prompt_commands` | File-based prompt commands |
| `lightercore.permissions` | `semantika.server.command.registry` | Permission levels |
