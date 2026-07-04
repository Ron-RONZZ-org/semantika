# AGENTS-scripts.md — Scripts Module Agent Instructions

## Summary
Development tooling: dev CLI, seed data generator, test infrastructure.

## Purpose and Expected Behavior
- `dev_cli.py` — `semantika-dev` entry point: starts an isolated dev server with optional seed data, temp data directory, dynamic port
- `seed.py` — Generates test data: sample nodes, predicates, triples for development and E2E testing

## Constraints and Invariants
- Dev server uses a temporary data directory to avoid polluting production data
- Seed data must be idempotent (safe to run multiple times)

## Input/Output Expectations
- CLI args via argparse, standard Unix conventions
- Output to stderr for status messages, seed data written to temp DB

## Documentation Reference
- lighterbird's scripts module: `../lighterbird/src/lighterbird/scripts/`

## Domain-Specific Rules for Agents
- When adding seed data, create a realistic knowledge graph (not just test noise)
- Seed data should exercise all query paths: exact match, prefix, FTS5, date range
