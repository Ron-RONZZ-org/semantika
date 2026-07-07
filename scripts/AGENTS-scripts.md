# AGENTS-scripts.md — Scripts Module Agent Instructions

## Summary
Development tooling: dev CLI, seed data generator, test infrastructure.

## Purpose and Expected Behavior
- `dev_cli.py` — `semantika-dev` entry point:
  - Starts an isolated dev server with optional seed data
  - Creates a temp data directory (avoids polluting production DB)
  - Dynamic port assignment (default 8001)
  - `--seed` flag creates a demo prompt command file in `~/.config/semantika/commands/`
  - Reads `.dev` file for API keys used during seed
- `__main__.py` — `python -m semantika` entry point for direct server launch

## Seed Data (`--seed`)
The `--seed` flag does the following:
1. Creates `~/.config/semantika/commands/` directory if needed
2. Writes a demo `test.md` prompt command file
3. Reads API keys from `.dev` file if present for configuring LLM during development

## Constraints and Invariants
- Dev server uses a temporary data directory to avoid polluting production data
- Seed data must be idempotent (safe to run multiple times)
- Prompt command seed files use content-based naming — if the demo file already exists, it is not overwritten

## Input/Output Expectations
- CLI args via argparse, standard Unix conventions
- Output to stderr for status messages, seed data written to temp DB and config commands dir

## Documentation Reference
- lighterbird's scripts module: `../lighterbird/src/lighterbird/scripts/`

## Domain-Specific Rules for Agents
- When adding seed data, create a realistic knowledge graph (not just test noise)
- Seed data should exercise all query paths: exact match, prefix, FTS5, date range
- The `--seed` flag should remain optional — never seed without explicit user intent
- When adding new prompt commands for demo/seed, follow the existing pattern: check if file exists first, use `config_dir() / "commands"` for path resolution
