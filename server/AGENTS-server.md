# AGENTS-server.md — Server Module Agent Instructions

## Summary
FastAPI web server: application factory, API routes, middleware, command engine, LLM integration, prompt commands, user configuration.

## Purpose and Expected Behavior
- `app.py` — `create_app()` factory that registers all routers and static file serving
- `routes/` — API endpoint handlers organized by domain
- `command/` — `!command` parsing engine, tree metadata, handler registry with `@command`/`@group_command` decorators
- `llm/` — Provider abstraction for OpenAI-compatible APIs and Ollama; singleton managed by `get_provider()`/`reset_provider()`
- `user_config.py` — User preferences persistence as JSON file (locale, etc.) at `~/.local/share/semantika/user_config.json`

## API Routes

| Prefix | File | Description |
|--------|------|-------------|
| `/api/v1/graph` | `routes/graph.py` | CRUD for nodes, predicates, triples |
| `/api/v1/query` | `routes/query.py` | Search, export, stats, raw SQL |
| `/api/v1/command` | `routes/command.py` | Tree, dispatch, execute, help |
| `/api/v1/review` | `routes/review.py` | Review sessions |
| `/api/v1/proof` | `routes/proof.py` | Proof CRUD |
| `/api/v1/llm` | `routes/llm.py` | Chat (two-phase: command gen → exec → summarise), config, profiles, confirm |
| `/api/v1/units` | `routes/unit.py` | Unit ontology |
| `/api/v1/files` | `routes/files.py` | File attachments |
| `/api/v1/prompt-commands` | `routes/prompt_commands.py` | List, expand, execute, SSE stream |
| `/api/v1/user` | `routes/user_config.py` | Locale/preferences |

## Constraints and Invariants
- All routes under `/api/v1/` namespace with version prefix
- Command handlers use decorator-based registration in `command/registry.py` — tree auto-generates from registrations
- Every `!command` must follow the **one concern, one root command** principle:
  - `!graph stats`, `!graph export`, `!graph import`, `!graph search`, `!graph view` — graph-level operations
  - `!node *`, `!predicate *`, `!triple *` — entity CRUD
  - `!predicate group *` — predicate group sub-namespace
  - `!backup *`, `!llm *`, `!user *` — feature groups
- List-type commands return specific types: `"node-list"`, `"predicate-list"`, `"triple-list"` — not `"table"`
- Static files mounted at `/` for Svelte SPA — the SPA handles client-side routing
- CORS defaults to localhost dev ports; configure via `SEMANTIKA_CORS_ORIGINS` env var for production
- Static directory overridable via `SEMANTIKA_STATIC_DIR` env var

## Input/Output Expectations
- All route handlers return Pydantic models or dicts (auto-JSON serialization)
- Errors return structured `{"error": "...", "detail": "..."}` responses
- The `!command` engine returns typed responses: `status`, `form-required`, `node-list`, `predicate-list`, `triple-list`, `graph`, `error`
- Prompt commands (`/*` prefix) are served by `GET/POST /api/v1/prompt-commands/*`:
  - `GET /list` — autocomplete source
  - `POST /expand` — preview expanded prompt
  - `POST /execute` — expand + send to LLM (sync JSON)
  - `POST /execute/stream` — SSE streaming variant
- User config served by `GET/PATCH /api/v1/user/config`

## Documentation Reference
- lighterbird's server module for proven patterns: `../lighterbird/src/lighterbird/server/`

## Domain-Specific Rules for Agents
- **Command response types**: `status` (simple message), `form-required` (redirect to GUI form), `table` (data table), `graph` (graph visualization data), `error`
- **Interactive commands**: Commands with `interactive: true` in `tree.py` trigger a form popup in the GUI when required params are missing
- **LLM integration**: The chat endpoint can call graph query methods. Keep LLM calls async with timeout. The provider at `server/llm/provider.py` extends `lightercore.llm.BaseLLMProvider` and delegates config/profile persistence to `lightercore.llm` modules.
- **LLM chat flow (two-phase)**:
  1. `POST /api/v1/llm/chat` — LLM generates structured command from natural language
  2. Permission check via `PermissionLevel` — destructive/write commands gate behind user confirm
  3. Command dispatched and result summarised by LLM
  4. If no command matched, respond as plain chat
  5. `POST /api/v1/llm/confirm` — execute a destructive command after user approval
- **Permission gate**: The LLM chat route checks command `permission_level` before dispatch. Commands with level >= DESTRUCTIVE return `{"type": "confirm", ...}` instead of executing immediately. Permission levels come from `@command(permission_level=...)` metadata; unset defaults to `WRITE`.
- **LLM provider architecture**: Uses `lightercore.llm` for ProviderConfig, keyring persistence, ProfileManager, and shared chat/command-generation infrastructure. The `LLMProvider` class is a singleton managed by `get_provider()` / `reset_provider()` — always use these instead of `LLMProvider()` directly.
- **Prompt command files**: Live at `~/.config/semantika/commands/*.md`. First line must start with `# ` (description). Positional args: `$1`, `$2`, …, `$9` and `$ARGUMENTS` catch-all. Parsed by `lightercore.prompt_commands`.
- **User config**: Persisted as JSON at `~/.local/share/semantika/user_config.json`. Atomic writes via temp+rename pattern. Currently supports `locale` only.
- **When adding new routes**, always add corresponding `!command` entries via `@command()` decorator in `handlers/`
