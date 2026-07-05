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

The interaction model is a **centralized command box** — type `!node add` to create entities, `!ask "What do I know about X?"` to query naturally, or just type naturally to chat with the built-in LLM. The philosophy: *you see only what you need* — no sidebars, no bloat.

### Project Family & Design Inheritance

Semantika is the **third generation** in a toolchain. When implementing new features, consult the ancestor projects for reference:

| Project | Role | What to reference |
|---------|------|-------------------|
| **[A-semantika](../A-semantika)** | EO-first CLI ancestor | **Business logic**: NodeService, PredicateService, TripleService, Turtle export/import, review/proof mechanics, unit ontology. Forked with Esperanto→English migration. |
| **[lighterbird](../lighterbird)** | Mature sister PIM app | **UX/LLM/DB**: Command-bar interaction, command tree + dispatch architecture, autocomplete engine, tab/result-panel UI, LLM provider integration (OpenAI/Ollama), text-based command generation, keyring-based config management. |
| **[lightercore](../lightercore)** | Shared core library | **DB/paths/exceptions/CRUD/backup/permissions**: Canonical implementations consumed by both lighterbird and semantika. Replaces the earlier vendored A-core. |
| **[A-core](../A-core)** | First-gen core library | Historical reference only. Superseded by lightercore. |

**Key rule**: When the task is about graph business logic (nodes, predicates, triples, TTL, review, proof, units), look at **A-semantika** first. When the task is about UX patterns (command routing, LLM, autocomplete, tabs, forms) or DB management, look at **lighterbird** first. For shared infrastructure (DB, paths, exceptions, CRUD, backup, permissions), look at **lightercore** first — that is the canonical source.

The backend is forked from proven code in [A-semantika](../A-semantika) (triple store services). Shared infrastructure (DB, paths, exceptions, CRUD, backup, permissions) comes from [lightercore](../lightercore), which supersedes the earlier vendored [A-core](../A-core). The frontend is a Svelte SPA served by a FastAPI Python server, with UX patterns ported from [lighterbird](../lighterbird).

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
| AI providers | OpenAI-compatible API + Ollama | BYOK: bring your own model/key; **three-phase command generation** (LLM parses NL → structured JSON command → permission check → dispatch → summarize) with permission gate guarding destructive commands behind user confirmation |
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

The Svelte dev server (Vite, port 5173) proxies `/api/*` requests to the Python backend.
The proxy target defaults to port **8001**. In production the built SPA is served on the
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

The default fallback is `SEMANTIKA_PORT || 8001` in ``vite.config.js``.

---

## Source Tree Structure

```
semantika/
├── AGENTS.md                    # This file — global project rules
├── README.md
├── LICENSE                      # AGPL-3.0
├── pyproject.toml
├── .gitignore
├── src/
│   └── semantika/               # Main Python package
│       ├── __init__.py
│       ├── __main__.py          # python -m semantika entry point
│       ├── core/                # Re-exports from lightercore (DB, paths, exceptions, CRUD, backup, permissions) + reset
│       │   ├── __init__.py      # Re-exports SemantikaDB, paths, exceptions
│       │   ├── db.py / paths.py / exceptions.py / backup.py / crud.py / fts.py
│       │   └── reset.py         # Reset to fresh state
│       ├── graph/               # Triple store services (18 Python files)
│       │   ├── __init__.py + constants.py + db.py + file_helpers.py
│       │   ├── node_helpers.py + node_service.py
│       │   ├── predicate_service.py + predicate_group_service.py
│       │   ├── triple_service.py + triple_turtle.py
│       │   ├── review_service.py + proof_service.py
│       │   ├── unit_service.py + unit_builder.py + unit_decomposition.py
│       │   ├── unit_errors.py + unit_parser.py + unit_seed_data.py
│       │   └── services/__init__.py
│       └── server/              # FastAPI web server
│           ├── __init__.py
│           ├── app.py           # Application factory
│           ├── tasks.py         # Background scheduled tasks
│           ├── command/         # Command engine (models, parser, errors)
│           ├── llm/             # LLM provider abstraction
│           └── routes/
│               ├── graph.py     # /api/v1/graph/* — CRUD for nodes, predicates, triples
│               ├── query.py     # /api/v1/query/* — search, export, stats, sparql
│               ├── command.py   # /api/v1/command/* — tree, dispatch, execute
│               ├── review.py    # /api/v1/review/* — session management
│               ├── proof.py     # /api/v1/proof/* — proof CRUD
│               ├── unit.py      # /api/v1/units/* — unit ontology
│               ├── files.py     # /api/v1/files/* — file attachments
│               └── llm.py       # /api/v1/llm/* — chat routing
├── tests/                       # pytest tests
│   ├── test_core/               # Backup, infrastructure tests
│   ├── test_graph/              # Service integration tests
│   └── test_server/             # API E2E tests (includes conftest.py)
├── core/                        # AGENTS-core.md (doc only — code is under src/semantika/core/)
├── graph/                       # AGENTS-graph.md (doc only — code is under src/semantika/graph/)
├── server/                      # AGENTS-server.md (doc only — code is under src/semantika/server/)
├── scripts/                     # AGENTS-scripts.md (doc only — scripts live at src/semantika/__main__.py + pyproject.toml)
└── web/                         # Svelte frontend
    ├── package.json / vite.config.js / svelte.config.js / index.html
    └── src/
        ├── main.js + App.svelte
        └── lib/                  # UI components
            ├── CommandBar.svelte / CommandBar.svelte
            ├── DynamicForm.svelte / FormField.svelte / FormTab.svelte
            ├── PopupOverlay.svelte / StatusPopup.svelte / ErrorPopup.svelte
            ├── TabView.svelte / HomeTab.svelte / SearchTab.svelte
            ├── LoadingPopup.svelte / BannerContainer.svelte
            ├── HelpPopup.svelte / ConfirmDialog.svelte
            ├── LlmSetupModal.svelte / GraphView.svelte
            └── command*.js / popupStore.svelte.js / tabStore.svelte.js / api.js / markdown.js
```

---

## GUI + CLI Parity Requirement

**All functionalities MUST be accessible via BOTH GUI and CLI.** No feature may be CLI-only or GUI-only. This means:

- Every `!command` must have a corresponding GUI panel (form, tab, or overlay) accessible through the command bar.
- Every GUI form/panel must have a corresponding `!command` accessible via the centralized command box.
- When adding a new feature, implement both the CLI handler (backend) and the GUI component (Svelte) simultaneously.
- The authoritative command metadata lives in `src/semantika/server/command/tree.py` (backend). The frontend fetches it on startup via `GET /api/v1/command/tree`.

---

## Coding Guidelines

1. **No file > 500 lines.** Split by functional unit.
2. **Type hints on all public functions.** Use `from __future__ import annotations`.
3. **Docstrings on all public functions.** Google-style or reStructuredText.
4. **Tests required for all modules.** `pytest` with `tmp_path` isolation for DB tests.
5. **SQLite in WAL mode.** Use `pragma journal_mode=wal` on connection.
6. **API keys in system keyring only.** Never in SQLite, config files, or environment (beyond dev).
7. **Async where it matters.** FastAPI routes are async; business logic can be sync.
8. **Error messages include actionable suggestions.**
9. **Missing CLI args → form popup (default behaviour).** When a `!command` is invoked with missing required options and the command has an interactive form registered, the system redirects the user to a form with pre-filled options. All interactive commands must be registered in `tree.py` (backend) with `interactive: true`.

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

## What to Avoid

- **Do not import from A-ecosystem packages at runtime.** Use lightercore instead of vendoring A-core directly.
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
| Graph | `graph/AGENTS-graph.md` | Triple store services (node, predicate, triple, recenzi, provo) |
| Server | `server/AGENTS-server.md` | FastAPI routes, command engine, LLM |
| Scripts | `scripts/AGENTS-scripts.md` | Dev CLI, seed data generator |
| Web | `web/AGENTS-web.md` | Svelte SPA, command-bar UI |

(Update this table as new modules are added)

---

## Dependency and Inheritance Map

```
Root AGENTS.md (global rules)
    │
    ├── core/AGENTS-core.md       DB, FTS5, paths, interactive helpers
    ├── graph/AGENTS-graph.md     Triple store: nodes, predicates, triples, recenzi, provo
    ├── server/AGENTS-server.md   FastAPI backend, API routes, LLM
    ├── scripts/AGENTS-scripts.md Dev CLI, seed data, test infra
    └── web/AGENTS-web.md         Svelte SPA frontend
```

Local rules override global rules. Module-level files focus on domain-specific behavior, constraints, and invariants.
