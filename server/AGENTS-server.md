# AGENTS-server.md — Server Module Agent Instructions

## Summary
FastAPI web server: application factory, API routes, middleware, command engine, LLM integration.

## Purpose and Expected Behavior
- `app.py` — `create_app()` factory that registers all routers and static file serving
- `routes/` — API endpoint handlers organized by domain
- `command/` — `!command` parsing engine, tree metadata, handler registry
- `llm/` — Provider abstraction for OpenAI-compatible APIs and Ollama

## Constraints and Invariants
- All routes under `/api/v1/` namespace with version prefix
- `command/tree.py` is the single source of truth for command metadata
- Every `!command` must be registered in `tree.py` with proper response type
- Static files mounted at `/` for Svelte SPA — the SPA handles client-side routing

## Input/Output Expectations
- All route handlers return Pydantic models or dicts (auto-JSON serialization)
- Errors return structured `{"error": "...", "detail": "..."}` responses
- The `!command` engine returns typed responses: `status`, `form-required`, `table`, `graph`

## Documentation Reference
- lighterbird's server module for proven patterns: `../lighterbird/src/lighterbird/server/`

## Domain-Specific Rules for Agents
- **Command response types**: `status` (simple message), `form-required` (redirect to GUI form), `table` (data table), `graph` (graph visualization data), `error`
- **Interactive commands**: Commands with `interactive: true` in `tree.py` trigger a form popup in the GUI when required params are missing
- **LLM integration**: The chat endpoint can call graph query methods. Keep LLM calls async with timeout.
- **Permission gate**: The LLM chat route checks command `permission_level` before dispatch. Commands with level >= DESTRUCTIVE return `{"type": "confirm", ...}` instead of executing immediately. Use `POST /api/v1/llm/confirm` for user-approved dispatch. Permission levels come from `@command(permission_level=...)` metadata; unset defaults to `WRITE`.
- **When adding new routes**, always add corresponding `!command` entries in `tree.py`
