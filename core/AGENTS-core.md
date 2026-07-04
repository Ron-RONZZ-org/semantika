# AGENTS-core.md — Core Module Agent Instructions

## Summary
Vendored utilities from A-core: database connection management, FTS5 configuration, file paths, interactive prompts, and shared helpers.

## Purpose and Expected Behavior
- `db.py` — `SQLiteDB` connection manager with WAL mode, transaction context manager, retry logic
- `storage.py` — Schema DDL, `get_db()` singleton, `init_db()`, backup targets
- `paths.py` — XDG-compliant data/config directory resolution
- `crud.py` — `CRUDService` base class with standard CRUD + soft-delete pattern
- `interactive.py` — `confirm_action()`, `select_candidate()`, `select_candidates()` helpers
- `fts.py` — `FTSConfig` for FTS5 virtual table setup

## Constraints and Invariants
- All DB connections use WAL mode
- All files under 500 lines
- No imports from A-ecosystem packages — this is the vendored core
- Transactions via `with self.db.transaction():`

## Input/Output Expectations
- All public functions have type hints
- DB functions raise `sqlite3.Error` subclasses on failure (not bare `Exception`)

## Documentation Reference
- See A-core source in `../A-core/src/A/core/` for upstream reference

## Domain-Specific Rules for Agents
- When adding new DB features, match the existing pattern (context manager, retry, WAL)
- Do NOT add encryption or keyring features here — Semantika is local-only
- Schema migrations follow the `init_db()` pattern with version checks
