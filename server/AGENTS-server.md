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
| `/api/v1/triple-templates` | `routes/triple_templates.py` | List, get, expand, execute triple templates |
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
- List commands support pagination via `--limit` (default 100) and `--offset` (default 0) flags; responses include `total`, `limit`, and `offset` metadata keys
- Prompt commands (`/` prefix) are served by `GET/POST /api/v1/prompt-commands/*`:
  - `GET /list` — autocomplete source
  - `POST /expand` — preview expanded prompt
  - `POST /execute` — expand + send to LLM (sync JSON)
  - `POST /execute/stream` — SSE streaming variant
- User config served by `GET/PATCH /api/v1/user/config`

## Documentation Reference
- lighterbird's server module for proven patterns: `../lighterbird/src/lighterbird/server/`

## Security and Operational Notes
- **User hooks flag**: ``create_app(no_hooks=True)`` skips loading ``~/.config/semantika/hooks.py``. The ``semantika-dev --no-hooks`` CLI flag exposes this for debugging.
- **System prompt source of truth**: The canonical Semantika system prompt lives in ``llm/system_prompt.py`` (exported as ``SEMANTIKA_SYSTEM_PROMPT``). All endpoints (``routes/llm.py``, ``routes/prompt_commands.py``) import from there — never duplicate it.
- **Raw SQL query limit**: The ``POST /api/v1/query/raw`` endpoint rejects queries longer than ``MAX_RAW_QUERY_LENGTH`` (10,000 chars) to prevent resource exhaustion.

## Domain-Specific Rules for Agents
- **Command response types**: `status` (simple message), `form-required` (redirect to GUI form), `table` (data table), `graph` (graph visualization data), `error`
- **Interactive commands**: Commands with `interactive: true` in `tree.py` trigger a form popup in the GUI when required params are missing
- **LLM integration**: The chat endpoint can call graph query methods. Keep LLM calls async with timeout. The provider at `server/llm/provider.py` extends `lightercore.llm.BaseLLMProvider` and delegates config/profile persistence to `lightercore.llm` modules.
- **LLM chat flow (multi-round tool-calling)**:
  1. `POST /api/v1/llm/chat` — user sends NL message; backend runs `run_tool_loop` which calls `provider.chat_with_tools` with registered tool definitions
  2. LLM can call multiple tools per round — READ-level tools execute immediately, WRITE/DESTRUCTIVE tools gate behind user confirmation
  3. If write tools are present, the endpoint returns `{"type": "confirm_tool", "session_id": "...", "batch": [...], "message": "..."}` instead of a final reply
  4. Frontend shows a confirmation dialog with the batch of pending operations
  5. Frontend calls `POST /api/v1/llm/chat/resume` with `{session_id, decisions}` (or `confirmed: bool`) to approve or reject
  6. Resume continues the tool loop: approved tools execute, rejected tools are recorded as user rejection; LLM may call more tools or produce a final text answer
- **Same flow for prompt commands**: `/api/v1/prompt-commands/execute` returns `confirm_tool` for write tools; resume via `/api/v1/prompt-commands/execute/resume`
- **Legacy single-command confirm**: `POST /api/v1/llm/confirm` still available for the old flow (`{"type": "confirm", ...}` from the deprecated `generate_command` path). Both the backend and frontend support both formats.
- **User hooks**: ``~/.config/semantika/hooks.py`` is loaded at startup (after system commands register). Any ``@command`` decorator in that file registers (or overrides) a handler. Overridden commands can delegate to the original via ``call_system_command()``. See ``registry.py:freeze_system_commands`` / ``call_system_command`` / ``load_user_hooks``.
- **Permission gate**: The LLM chat route checks command `permission_level` before dispatch. Commands with level >= WRITE return `{"type": "confirm_tool", ...}` (batch) instead of executing immediately. Permission levels come from `@command(permission_level=...)` metadata; unset defaults to `WRITE`.
- **LLM provider architecture**: Uses `lightercore.llm` for ProviderConfig, keyring persistence, ProfileManager, and shared chat/command-generation infrastructure. The `LLMProvider` class is a singleton managed by `get_provider()` / `reset_provider()` — always use these instead of `LLMProvider()` directly.
- **Prompt command files**: Live at `~/.config/semantika/commands/*.md`. First line must start with `# ` (description). Positional args: `$1`, `$2`, …, `$9` and `$ARGUMENTS` catch-all. Parsed by `lightercore.prompt_commands`.
- **User config**: Persisted as JSON at `~/.local/share/semantika/user_config.json`. Atomic writes via temp+rename pattern. Currently supports `locale` only.
- **When adding new routes**, always add corresponding `!command` entries via `@command()` decorator in `handlers/`
