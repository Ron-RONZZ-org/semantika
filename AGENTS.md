# AGENTS.md — Root Project Rules for Semantika

This is the canonical, repo-wide instruction file for AI agents working on **Semantika**.

## Hierarchical Context Model

Agents **must** follow this rule:

> When working inside a directory, load the nearest `AGENTS.md` file and merge it with parent `AGENTS.md` files up to root.
> Local rules override global rules.

Context resolution order (highest priority first):
1. `AGENTS-[module].md` in module directories — module-specific context
2. `AGENTS.md` in current working directory (if present)
3. Root `AGENTS.md` — global project rules

---
## Project Overview

**Semantika** is a command-driven knowledge graph tool integrating semantic triple storage, natural-language querying, and LLM-native interaction into a single webapp with BYOK (Bring Your Own Key) LLM support.

The interaction model is a **centralized command box** — three input modes:
- `!command` — built-in graph operations (`!node add`, `!triple list`, `!backup now`, etc.)
- `/prompt-command` — user-defined file-based LLM prompt templates stored in `~/.config/semantika/commands/*.md`
- natural text — free-form chat with the built-in LLM via `!ask` or plain input

The philosophy: *you see only what you need* — no sidebars, no bloat.

### Project Family & Design Inheritance

Semantika is the **third generation** in a toolchain. When implementing new features, consult the ancestor projects for reference:

| Project | Role | What to reference |
|---------|------|-------------------|
| **[A-semantika](../A-semantika)** | EO-first CLI ancestor | **Business logic**: NodeService, PredicateService, TripleService, Turtle export/import, review/proof mechanics, unit ontology. Forked with Esperanto→English migration. |
| **[lighterbird](../lighterbird)** | Mature sister PIM app | **UX/LLM/DB**: Command-bar interaction, command tree + dispatch architecture, autocomplete engine, tab/result-panel UI, LLM provider integration (OpenAI/Ollama), text-based command generation, keyring-based config management, prompt commands (`/` prefix). |
| **[lightercore](../lightercore)** | Shared core library | **DB/paths/exceptions/CRUD/backup/permissions/prompt_commands/user_config**: Canonical implementations consumed by both lighterbird and semantika. Replaces the earlier vendored A-core. |
| **[A-core](../A-core)** | First-gen core library | Historical reference only. Superseded by lightercore. |

**Key rule**: When the task is about graph business logic (nodes, predicates, triples, TTL, review, proof, units), look at **A-semantika** first. When the task is about UX patterns (command routing, LLM, autocomplete, tabs, forms, prompt commands, user config) or DB management, look at **lighterbird** first. For shared infrastructure (DB, paths, exceptions, CRUD, backup, permissions, prompt_commands), look at **lightercore** first — that is the canonical source.

The backend is forked from proven code in [A-semantika](../A-semantika) (triple store services). Shared infrastructure (DB, paths, exceptions, CRUD, backup, permissions, prompt_commands) comes from [lightercore](../lightercore), which supersedes the earlier vendored [A-core](../A-core). The frontend is a Svelte SPA served by a FastAPI Python server, with UX patterns ported from [lighterbird](../lighterbird).

**Shared UI components**: Basic Svelte 5 stores and utility functions are extracted into [lightercore's `web/`](../lightercore/web/) as the `@lightercore/ui` npm package. Local files in `web/src/lib/` are thin re-export wrappers; the canonical implementations live in lightercore. See `web/AGENTS-web.md` for the import convention.

---

## Language and Naming Conventions

- **Source code**: English (variable names, comments, docstrings)
- **User-facing strings**: English first (i18n can be added later)
- **CLI command names**: English, **singular form** (`node`, `predicate`, `triple`, `search`, `export`, `review`, `proof`) — the `!` commands are user-facing
- **URL paths, route names**: lowercase with hyphens (`/api/v1/graph/nodes`)
- **Database columns**: English names throughout (e.g., `node_id`, `labels`, `definitions`, `created_at`). Migrated from A-semantika's Esperanto convention.

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend | Python 3.11+ | Ecosystem, existing codebase |
| Backend framework | FastAPI + uvicorn | Lightweight, async, auto-docs |
| Frontend | Svelte 5 SPA | Minimal bundle, excellent custom component DX |
| Frontend build | Vite + svelte-spa-router | Fast dev, static export possible |
| Database | SQLite (WAL mode) | Embedded, zero-config, sufficient for single-user |
| Credential storage | System keyring (via `keyring` library) | Never store API keys in DB |
| AI providers | OpenAI-compatible API + Ollama | BYOK: bring your own model/key; **multi-round tool-calling** (LLM sees all ``!commands`` as native tools, calls them via ``chat_with_tools``, permission gate returns ``confirm_tool`` for write/destructive commands) |
| TTL parsing | `rdflib` | Standard Turtle (.ttl) import |
| HTTP client | `httpx` | Async HTTP for LLM provider calls |
| Package manager | `uv` (development), `pip` (user install) | Fast, modern, reproducible |
| Build system | Hatchling | PEP 517 compliant, simple |

---

## Dependency Management

This project uses **uv** for development:

| Operation | Command |
|-----------|---------|
| Install project in dev mode | `uv pip install -e .` |
| Install dev deps | `uv pip install -e ".[dev]"` |
| Run tests | `uv run pytest tests/` |
| Run isolated dev server | `uv run semantika-dev --seed` |
| Add dependency | `uv add <pkg>` |
| Add dev dependency | `uv pip install <pkg>` |

---

## Development Server

### Port synchronization (dev only)

The Svelte dev server (Vite, port 6016) proxies `/api/*` requests to the Python backend.
The proxy target defaults to port **6015**. In production the built SPA is served on the
same port as the API — no proxy needed.

If the backend is on a different port (conflict, `--port 0`, or custom setup),
set the `SEMANTIKA_PORT` env var before starting the frontend:

```bash
# Terminal 1: backend on custom port
SEMANTIKA_DATA_DIR=/tmp/semantika-dev uv run uvicorn \
  semantika.server.app:create_app --factory --port 8765

# Terminal 2: Vite proxies to that port
SEMANTIKA_PORT=8765 npm run dev
```

The default fallback is `SEMANTIKA_PORT || 6015` in ``vite.config.js``.

---

## User-Simulation Testing

When running user-simulation tests against the backend, **always use a dynamically-allocated free port**. Never kill a process on the default port (6015) — it may belong to the user's manual dev instance.

```bash
# Find a free TCP port (never kill a foreign process on the default port)
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")

# Start isolated seeded server on that port
setsid uv run semantika-dev --seed --port $PORT > /tmp/semantika-dev.log 2>&1 &

# Wait for server to accept connections
for i in $(seq 1 30); do
  curl -sf -o /dev/null http://127.0.0.1:$PORT/ && break
  sleep 1
done

# Run tests or queries against http://127.0.0.1:$PORT
```

Always use `http://127.0.0.1:<port>` (IPv4) when connecting to a local dev server.

---

## Source Tree Structure

```
semantika/
├── AGENTS.md                    # This file — global project rules
├── README.md
├── LICENSE                      # AGPL-3.0
├── pyproject.toml
├── .gitignore
├── .dev                         # Local dev secrets (gitignored) — API keys for --seed mode
├── src/
│   └── semantika/               # Main Python package
│       ├── __init__.py
│       ├── __main__.py          # python -m semantika entry point
│       ├── core/                # Re-exports from lightercore (DB, paths, exceptions, CRUD, backup, permissions) + reset
│       │   ├── __init__.py      # Re-exports SemantikaDB, paths, exceptions
│       │   ├── db.py / paths.py / exceptions.py / backup.py / crud.py / fts.py
│       │   └── reset.py         # Reset to fresh state
│       ├── graph/               # Triple store services (16 source files + services/)
│       │   ├── __init__.py + constants.py + db.py + file_helpers.py
│       │   ├── node_helpers.py + node_service.py + node_merge_mixin.py + node_fts.py
│       │   ├── predicate_service.py + predicate_group_service.py
│       │   ├── triple_service.py + triple_turtle.py
│       │   ├── review_service.py + proof_service.py
│       │   ├── unit_service.py + unit_builder.py + unit_decomposition.py
│       │   ├── unit_errors.py + unit_parser.py + unit_seed_data.py
│       │   └── services/__init__.py
│       ├── scripts/             # CLI entry points
│       │   ├── __init__.py
│       │   └── dev_cli.py       # semantika-dev CLI: temp DB, --seed prompt commands
│       └── server/              # FastAPI web server
│           ├── __init__.py
│           ├── app.py           # Application factory
│           ├── tasks.py         # Background scheduled tasks (backup scheduler)
│           ├── user_config.py   # User config persistence (locale, preferences) — JSON file on disk
│           ├── command/         # Command engine (models, parser, registry, handlers)
│           │   ├── __init__.py
│           │   ├── registry.py  # @command/@group_command decorators, dispatch, tree generation
│           │   ├── parser.py    # Tokenizer for !command input
│           │   ├── models.py    # CommandRequest/CommandResponse pydantic models
│           │   ├── errors.py    # CommandError, CommandNotFound, CommandValidationError
│           │   ├── helpers.py   # Shared helper utilities
│           │   └── handlers/    # One file per domain (auto-registered via import)
│           │       ├── __init__.py
│           │       ├── graph.py / node.py / node_helpers.py
│           │       ├── predicate.py / predicate_group.py / predicate_trash.py
│           │       ├── triple.py / review.py
│           │       ├── backup.py / reset.py
│           │       ├── llm.py
│           │       ├── trash.py
│           │       ├── unit.py
│           │       └── user_config.py
│           ├── llm/             # LLM provider abstraction
│           │   ├── __init__.py
│           │   └── provider.py  # Provider singleton (get_provider / reset_provider)
│           └── routes/          # FastAPI route handlers
│               ├── graph.py     # /api/v1/graph/* — CRUD for nodes, predicates, triples
│               ├── query.py     # /api/v1/query/* — search, export, stats, raw SQL
│               ├── command.py   # /api/v1/command/* — tree, dispatch, execute, help
│               ├── review.py    # /api/v1/review/* — session management
│               ├── proof.py     # /api/v1/proof/* — proof CRUD
│               ├── unit.py      # /api/v1/units/* — unit ontology
│               ├── files.py     # /api/v1/files/* — file attachments
│               ├── llm.py       # /api/v1/llm/* — chat, config, profiles, confirm
│               ├── prompt_commands.py  # /api/v1/prompt-commands/* — list, expand, execute, SSE stream
│               └── user_config.py      # /api/v1/user/config — locale, preferences
├── tests/                       # pytest tests (849 tests)
│   ├── conftest.py
│   ├── test_core/               # Backup, entry points, reset tests
│   ├── test_graph/              # Service integration tests (nodes, predicates, triples, units, proofs)
│   └── test_server/             # API E2E + handler dispatch tests
│       ├── conftest.py
│       ├── test_api_*.py        # API endpoint tests per domain
│       ├── test_handler_*.py    # Command handler dispatch tests
│       ├── test_command_*.py    # Command parser + dispatch
│       ├── test_llm_*.py        # LLM provider + API tests
│       └── test_files_api.py    # File attachment API tests
├── core/                        # AGENTS-core.md (doc only — code is under src/semantika/core/)
├── graph/                       # AGENTS-graph.md (doc only — code is under src/semantika/graph/)
├── server/                      # AGENTS-server.md (doc only — code is under src/semantika/server/)
├── scripts/                     # AGENTS-scripts.md (doc only — code is at src/semantika/scripts/)
└── web/                         # Svelte 5 SPA frontend
    ├── package.json / vite.config.js / svelte.config.js / index.html
    └── src/
        ├── main.js + App.svelte
        └── lib/                  # UI components
            ├── ChatInput.svelte / DynamicForm.svelte / FormField.svelte
            ├── FormTab.svelte / PopupOverlay.svelte / StatusPopup.svelte
            ├── ErrorPopup.svelte / LoadingPopup.svelte / BannerContainer.svelte
            ├── HelpPopup.svelte / ConfirmDialog.svelte / KeyboardShortcutOverlay.svelte
            ├── LlmSetupModal.svelte / GraphView.svelte / QuizPanel.svelte
            ├── HomeTab.svelte / HomeHeader.svelte
            ├── TabView.svelte / MessageList.svelte
            ├── NodeListTab.svelte / PredicateListTab.svelte / TripleListTab.svelte
            ├── listTabFormat.js / listTabSelection.svelte.js / listTabShared.svelte.js
            ├── commandRouter.js / commandEngine.js / commandExecutor.js
            ├── commandTree.js / commandHistory.svelte.js / parser.js
            ├── popupStore.svelte.js / tabStore.svelte.js / bannerStore.svelte.js
            ├── dirtyFormStore.svelte.js / keyboardShortcuts.svelte.js
            └── userConfig.svelte.js / markdown.js
```

---

## GUI + CLI Parity Requirement

**All functionalities MUST be accessible via BOTH GUI and CLI.** No feature may be CLI-only or GUI-only. This means:

- Every `!command` must have a corresponding GUI panel (form, tab, or overlay) accessible through the command bar.
- Every GUI form/panel must have a corresponding `!command` accessible via the centralized command box.
- When adding a new feature, implement both the CLI handler (backend) and the GUI component (Svelte) simultaneously.
- The authoritative command metadata is generated by `src/semantika/server/command/registry.py` (backend). The frontend fetches it on startup via `GET /api/v1/command/tree`.

---

## Prompt Commands (`/` prefix)

Prompt commands are user-defined LLM prompt templates stored as Markdown files in the config directory. They provide a way to extend Semantika with custom reusable prompts.

### How they work

- Files live at `~/.config/semantika/commands/*.md` (XDG config dir)
- The first line starting with `# ` is the description (shown in autocomplete)
- Everything after is the template body, with `$1`, `$2`, … positional placeholders
- `$ARGUMENTS` is a catch-all for all remaining args joined with spaces
- Files without a `# ` first line are silently skipped

### Example

Create `~/.config/semantika/commands/weekly.md`:

```markdown
# Weekly review of what I learned
Review the nodes added in the past $1 days and identify key themes.

Then look at $2 area specifically.
```

Usage: `/weekly 7 productivity`

### Adding new prompt commands

To add a new `/` command, simply create a new `.md` file in the commands directory:

```bash
# Pick a descriptive filename (no spaces) — the stem becomes the command name
echo '# Summarize the last N emails
Summarise the last $1 emails focusing on key items.' \
  > ~/.config/semantika/commands/summarize.md
```

The command is immediately available — no restart needed. The frontend fetches the list on startup and the dev server supports hot-reload.

### API

Prompt commands are served by `GET/POST /api/v1/prompt-commands/*`:
- `GET /list` — autocomplete source
- `POST /expand` — preview expanded template
- `POST /execute` — expand + send to LLM (sync JSON)
- `POST /execute/stream` — SSE streaming variant

The `--seed` flag on `semantika-dev` creates a demo prompt command for testing.

## Service Caching

`get_services()` in ``graph/db.py`` caches service instances (``NodeService``, ``PredicateService``, ``TripleService``, ``ProofService``, ``ReviewService``, ``PredicateGroupService``) after the first call.  This avoids re-instantiating the entire service layer on every command dispatch.

- Call :func:`reset_services` to clear the cache after a database reset or restore.
- When writing tests that share a global ``get_services()``, call ``reset_services()`` between test runs to avoid state leakage.
- The ``FTS5Manager`` in ``core/fts.py`` provides shared FTS5 index operations to both ``NodeService`` and ``PredicateService``, replacing the duplicated ``_ensure_fts`` / ``_index_fts`` / ``_remove_from_fts`` / ``_rebuild_fts`` pattern.

## User Configuration

Semantika supports persistent user preferences stored as JSON at `~/.local/share/semantika/user_config.json`:

- **Locale** — set via `!user config --locale CODE` or the GUI locale badge
- API: `GET/PATCH /api/v1/user/config`
- The frontend fetches locale on startup and falls back to browser language

## Coding Guidelines

1. **No file > 500 lines.** Split by functional unit.
2. **Type hints on all public functions.** Use `from __future__ import annotations`.
3. **Docstrings on all public functions.** Google-style or reStructuredText.
4. **Tests required for all modules.** `pytest` with `tmp_path` isolation for DB tests.
5. **SQLite in WAL mode.** Use `pragma journal_mode=wal` on connection.
6. **API keys in system keyring only.** Never in SQLite, config files, or environment (beyond dev).
7. **Async where it matters.** FastAPI routes are async; business logic can be sync.
8. **Error messages include actionable suggestions.**
9. **Missing CLI args → form popup (default behaviour).** When a `!command` is invoked with missing required options and the command has an interactive form registered, the system redirects the user to a form with pre-filled options. All interactive commands must be registered in `registry.py` (backend) with `interactive: true`.
10. **Prompt command files go in `~/.config/semantika/commands/*.md`.** The first line must start with `# ` (description). Positional args use `$1`, `$2`, …, `$9` and `$ARGUMENTS` catch-all.

---

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` — new user-facing feature
- `fix:` — bug fix
- `docs:` — documentation only
- `chore:` — tooling, config, CI
- `test:` — test additions/fixes
- `refactor:` — code restructuring with no behavior change
- `web:` — frontend-only changes (Svelte)
- `server:` — backend API changes

---

## Testing Requirements

| Aspect | Convention |
|--------|-----------|
| Framework | pytest |
| Run all tests | `uv run pytest tests/` |
| Run single test file | `uv run pytest tests/test_graph/test_nodes.py -v` |
| Test directory | `tests/` |

### Testing Principles

1. **Test via the public API wherever possible.** Prefer integration tests over isolated unit tests.
2. **Console errors in browser tests indicate real bugs** — fix them even if tests pass.
3. **Every bug fix must include a test that would have caught the regression.**

---

## Local Development Secrets (`.dev`)

A `.dev` file in the project root stores local development secrets (API keys, test credentials).
It is **gitignored** (see `.gitignore`) and never committed.

This follows the same pattern as [lighterbird](../lighterbird), which uses `.dev` for test email
accounts, calendar credentials, and LLM API keys used by `--seed` mode.

```bash
# .dev — local development secrets (gitignored)
DEEPSEEK_API_KEY="sk-..."
```

The `--seed` flag (dev server) reads `.dev` to populate test data. Production deployments
should use environment variables or system keyring exclusively.

## Security: User Hooks

Semantika supports user-defined hooks via ``~/.config/semantika/hooks.py``, which is loaded
and executed using ``importlib`` at startup. **This is effectively arbitrary code execution
from disk.** The following considerations apply:

- The hooks file lives in the XDG config directory, which should be treated as a **trusted
  location** by the user.
- A malicious ``.dev`` file or a compromised config directory could inject arbitrary code.
- There is no ``--no-hooks`` flag to skip loading user hooks during debugging.
- **Recommendation**: If you share your config directory across machines, audit the hooks
  file for unexpected content before running Semantika.

---

## What to Avoid

- **Do not import from A-ecosystem packages at runtime.** Use lightercore instead of vendoring A-core directly.
- **Do not duplicate shared UI logic.** Before adding a new store, utility function, or UI primitive, check if it exists in `@lightercore/ui`. If a component has a lighterbird equivalent, extract it to lightercore rather than copying.
- **Do not duplicate logic across modules.** Shared infrastructure comes from lightercore; domain-specific utilities go in their own module.
- **Do not use `print()` for user output.** Use FastAPI structured responses or logging.
- **Do not store API keys in SQLite.** Keyring only.
- **Do not add heavy frameworks** (Django, SQLAlchemy, Celery) — this is a lightweight single-user app.
- **Do not hardcode paths.** Use `core.paths` module for XDG-compliant resolution.

---

## Module-Level AGENTS Files

| Module | AGENTS File | Description |
|--------|-------------|-------------|
| Core | `core/AGENTS-core.md` | DB, FTS5, paths, interactive helpers |
| Graph | `graph/AGENTS-graph.md` | Triple store services (node, predicate, triple, review, proof) |
| Server | `server/AGENTS-server.md` | FastAPI routes, command engine, LLM, prompt commands, user config |
| Scripts | `scripts/AGENTS-scripts.md` | Dev CLI, seed data generator, --seed prompt commands |
| Web | `web/AGENTS-web.md` | Svelte SPA, command-bar UI, prompt command autocomplete, locale

---

## Dependency and Inheritance Map

```
Root AGENTS.md (global rules)
    │
    ├── core/AGENTS-core.md       DB, FTS5, paths, interactive helpers
    ├── graph/AGENTS-graph.md     Triple store: nodes, predicates, triples, review, proof
    ├── server/AGENTS-server.md   FastAPI backend, API routes, LLM
    ├── scripts/AGENTS-scripts.md Dev CLI, seed data, test infra
    └── web/AGENTS-web.md         Svelte SPA frontend
```

Local rules override global rules. Module-level files focus on domain-specific behavior, constraints, and invariants.
