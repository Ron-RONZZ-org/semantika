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

#### Disk Locations (absolute paths on this machine)

All sibling repos live under `/home/rongzhou/kodo/autish/`:

| Project | Absolute path |
|---------|--------------|
| **semantika** | `/home/rongzhou/kodo/autish/semantika/` — this repo |
| **lighterbird** | `/home/rongzhou/kodo/autish/lighterbird/` |
| **lightercore** | `/home/rongzhou/kodo/autish/lightercore/` |
| **A-semantika** | `/home/rongzhou/kodo/autish/A-semantika/` |
| **A-core** | `/home/rongzhou/kodo/autish/A-core/` |

Relative references in this file (e.g., `../lightercore`) resolve correctly from within the semantika repo because all five projects share the same parent directory.

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
| SPARQL engine | `pyoxigraph` | Rust-based SPARQL 1.1 engine with RocksDB persistence |
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
| Run dev server with persistent data | `uv run semantika-dev --data-dir ~/semantika-data --seed` |
| Run dev server with real credentials | `uv run semantika-dev --data-dir ~/semantika-data --prod` |
| Add dependency | `uv add <pkg>` |
| Add dev dependency | `uv pip install <pkg>` |

---

## Development Server

### Dev server CLI (`semantika-dev`)

The `semantika-dev` CLI starts an isolated server with optional seed data.
It uses `lightercore.dev_helpers` for shared dev-server infrastructure.

```bash
# Ephemeral server with seed data from .dev (LLM config + prompt commands)
uv run semantika-dev --seed

# Persistent server (data survives restarts)
uv run semantika-dev --data-dir ~/semantika-data --seed

# Persistent server with .prod credentials
uv run semantika-dev --data-dir ~/semantika-data --prod

# No seed, skip user hooks
uv run semantika-dev --no-hooks
```

Flags beyond the standard set (`--seed`, `--prod`, `--seed-from`, `--data-dir`,
`--port`, `--keep-data`, `--quiet`):

| Flag | Description |
|------|-------------|
| `--no-hooks` | Skip loading user-defined hooks from `~/.config/semantika/hooks/` |

When ``--data-dir`` is used, the data directory persists across restarts and
seeding only runs when the directory is empty (safe to restart without losing
data).

### Port synchronization (dev only)

The Svelte dev server (Vite, port 6016) proxies `/api/*` requests to the Python backend.
The proxy target defaults to port **6015**. In production the built SPA is served on the
same port as the API — no proxy needed.

If the backend is on a different port (conflict, `--port 0`, or custom setup),
set the `SEMANTIKA_PORT` env var before starting the frontend:

```bash
# Terminal 1: backend on custom port
uv run semantika-dev --port 8765

# Terminal 2: Vite proxies to that port
SEMANTIKA_PORT=8765 npm run dev
```

The default fallback is `SEMANTIKA_PORT || 6015` in ``vite.config.js``.

### Node modules in git worktrees

Git worktrees do NOT share `node_modules/` with the parent repo — it appears as an
empty directory. There are three ways to run Node.js tools (Vitest, Vite, Playwright)
from a worktree:

1. **NODE_PATH** (one-shot, no setup):
   ```bash
   NODE_PATH=/path/to/parent/web/node_modules npx vitest run web/src/lib/__tests__/...
   ```

2. **Symlink** (persistent local setup):
   ```bash
   ln -sfn /path/to/parent/web/node_modules web/node_modules
   ```
   Once created, all Node.js tools resolve dependencies from the parent's
   `node_modules` as if they were installed locally. The symlink is gitignored.

3. **Full install** (isolated, slow):
   ```bash
   cd web && npm install
   ```
   Use this only if you need to modify `package.json` or work offline for extended
   periods.

Method 2 is the recommended balance between convenience and setup effort for this
project.

---

## User-Simulation Testing

See ``tests/AGENTS-tests.md`` for the full lifecycle: dev server with dynamically-allocated port, startup/teardown, cleanup, and data isolation.

Always use ``http://127.0.0.1:<port>`` (IPv4) when connecting to a local dev server.

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
├── .prod                        # Your real credentials (gitignored) — API keys for --prod mode
├── src/
│   └── semantika/               # Main Python package
│       ├── __init__.py
│       ├── __main__.py          # python -m semantika entry point
│       ├── core/                # Re-exports from lightercore (DB, paths, exceptions, CRUD, backup, permissions) + reset
│       │   ├── __init__.py      # Re-exports SemantikaDB, paths, exceptions
│       │   ├── db.py / paths.py / exceptions.py / backup.py / crud.py / fts.py
│       │   └── reset.py         # Reset to fresh state
│       ├── graph/               # Triple store services (20+ source files + services/)
│       │   ├── __init__.py + constants.py + db.py + helpers.py
│       │   ├── file_helpers.py + node_helpers.py + node_service.py
│       │   ├── node_merge_mixin.py + node_fts.py
│       │   ├── predicate_service.py + predicate_group_service.py
│       │   ├── triple_service.py + triple_turtle.py
│       │   ├── review_service.py + proof_service.py
│       │   ├── sparql/__init__.py + sparql/engine.py  # SPARQL engine (Oxigraph cache)
│       │   ├── unit_service.py + unit_builder.py + unit_decomposition.py
│       │   ├── unit_errors.py + unit_parser.py + units.yaml
│       │   ├── builtin_type_service.py + builtin_loader.py
│       │   ├── builtins.yaml + _required_predicates.py
│       │   └── services/__init__.py
│       ├── scripts/             # CLI entry points
│       │   ├── __init__.py
│       │   └── dev_cli.py       # semantika-dev CLI: --data-dir, --seed, --prod, --no-hooks
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
│               │   ├── graph.py / node.py / node_helpers.py
│               │   ├── node_attachment.py  # !node add attachment photo|video|file|code
│               │   ├── node_media.py       # !node add media book|film|song|game|podcast
│               │   ├── node_scholarly.py   # !node add scholarly paper|patent|conference
│               │   ├── predicate.py / predicate_group.py / predicate_trash.py
│               │   ├── triple.py / review.py
│               │   ├── template.py          # !template list/view/save/use
│               │   ├── backup.py / reset.py
│               │   ├── builtins.py          # !builtins reload
│               │   ├── system.py            # !system reindex
│               │   ├── sparql.py            # !sparql query/status
│               │   ├── context.py           # Context store for multi-turn flows (!context.get)
│               │   ├── help.py
│               │   ├── llm.py
│               │   ├── trash.py
│           │       ├── unit.py
│           │       └── user_config.py
│           ├── llm/             # LLM provider abstraction + tool registry
│           │   ├── __init__.py
│           │   ├── provider.py  # Provider singleton (get_provider / reset_provider)
│           │   ├── tool_loop.py # Re-exports from lightercore.llm.tool_loop
│           │   ├── system_prompt.py  # Two-file system prompt (base + AGENTS.md)
│           │   ├── prompt_defaults.py  # Shipped defaults for prompt files
│           │   └── tools/       # Dedicated LLM tool registry (AI-optimised, no CLI deps)
│           │       ├── __init__.py  # @llm_tool decorator, registry, dispatch
│           │       ├── graph.py     # graph.stats
│           │       ├── node.py      # node.search/view/create/update/delete
│           │       ├── predicate.py # predicate.search/view/create
│           │       ├── triple.py    # triple.search/add/delete
│           │       ├── template.py  # template.list/view/apply
│           │       ├── search.py    # search.fts
│           │       ├── sparql.py    # sparql.query/status
│           │       ├── system.py    # system.now
│           │       ├── review.py    # review.status
│           │       └── unit.py      # unit.search/info
│           ├── templates/       # Triple template management
│           │   ├── __init__.py + loader.py  # YAML file discovery and parsing
│           │   ├── models.py   # TemplateParam, TriplePattern, TripleTemplate
│           │   └── executor.py # execute_template, expand_template
│           └── routes/          # FastAPI route handlers
│               ├── graph.py     # /api/v1/graph/* — CRUD for nodes, predicates, triples
│               ├── query.py     # /api/v1/query/* — search, export, stats, raw SQL
│               ├── command.py   # /api/v1/command/* — tree, dispatch, execute, help
│               ├── review.py    # /api/v1/review/* — session management
│               ├── proof.py     # /api/v1/proof/* — proof CRUD
│               ├── unit.py      # /api/v1/units/* — unit ontology
│               ├── files.py     # /api/v1/files/* — file attachments
│               ├── llm.py       # /api/v1/llm/* — chat, config, profiles, confirm, resume
│               ├── sparql.py    # /api/v1/query/sparql — SPARQL 1.1 Protocol endpoint
│               ├── prompt_commands.py  # /api/v1/prompt-commands/* — list, expand, execute, SSE stream
│               │   Turn prompts use named-only expansion ($ARGUMENTS, $TEMPLATE_DESCRIPTION, $STYLE_EXAMPLE).
│               │   /template supports two-turn HITL: predicate.add in turn1, template.save in turn2.
│               │   /text-to-triples supports three-turn HITL: nodes in T1, templates+predicates in T2,
│               │     triples with post-loop validation in T3.
│               │   $STYLE_EXAMPLE auto-injected from most recently modified user-created template.
│               ├── prompt_commands_text_to_triple.py  # /text-to-triples three-turn flow logic
│               ├── prompt_commands_helpers.py  # Shared helpers: context dispatch, style injection
│               ├── triple_templates.py  # /api/v1/triple-templates/* — list, expand, execute, save
│               ├── prompts.py          # /api/v1/llm/prompts/* — prompt file management
│               └── user_config.py      # /api/v1/user/config — locale, preferences
├── tests/                       # pytest tests (1300+ tests)
│   ├── conftest.py
│   ├── test_core/               # Backup, entry points, reset, config tests
│   ├── test_graph/              # Service integration tests (nodes, predicates, triples, units, proofs)
│   ├── test_server/             # API E2E + handler dispatch tests
│   │   ├── conftest.py
│   │   ├── test_api_*.py        # API endpoint tests per domain
│   │   ├── test_handler_*.py    # Command handler dispatch tests
│   │   ├── test_command_*.py    # Command parser + dispatch
│   │   ├── test_llm_*.py        # LLM provider + API tests
│   │   ├── test_files_api.py    # File attachment API tests
│   │   ├── test_templates.py    # Triple template tests
│   │   ├── test_template_turns.py     # /template two-turn flow tests
│   │   ├── test_text_to_triple_flow.py # /text-to-triples flow tests
│   │   ├── test_prompt_commands.py     # Prompt command expansion/execution
│   │   ├── test_system_prompt.py       # System prompt loading tests
│   │   ├── test_sparql.py             # SPARQL endpoint tests
│   │   ├── test_user_hooks.py         # User hooks loading tests
│   │   └── test_zz_api_import.py      # Turtle import E2E
│   ├── test_scripts/            # Dev CLI tests
│   ├── semantika_full_e2e.mjs   # Playwright E2E test
│   ├── sparql_e2e.mjs           # SPARQL Playwright E2E test
│   ├── gui_fixes_e2e.mjs        # GUI fix regression E2E tests
│   ├── test_markdown.mjs        # Markdown renderer unit tests
│   └── test_e2e.py             # E2E wrapper (pytest-managed server)
├── core/                        # AGENTS-core.md (doc only — code is under src/semantika/core/)
├── graph/                       # AGENTS-graph.md (doc only — code is under src/semantika/graph/)
├── server/                      # AGENTS-server.md (doc only — code is under src/semantika/server/)
├── scripts/                     # AGENTS-scripts.md (doc only — code is at src/semantika/scripts/)
└── web/                         # Svelte 5 SPA frontend
    ├── package.json / vite.config.js / svelte.config.js / index.html
    └── src/
        ├── main.js + App.svelte
        ├── lib/                  # UI components
        │   ├── ChatInput.svelte / DynamicForm.svelte / FormField.svelte
        │   ├── FormTab.svelte / PopupOverlay.svelte / StatusPopup.svelte
        │   ├── ErrorPopup.svelte / LoadingPopup.svelte / BannerContainer.svelte
        │   ├── HelpPopup.svelte / ConfirmDialog.svelte / KeyboardShortcutOverlay.svelte
        │   ├── LlmSetupModal.svelte / GraphView.svelte / QuizPanel.svelte
        │   ├── HomeTab.svelte / HomeHeader.svelte
        │   ├── TabView.svelte / MessageList.svelte
        │   ├── NodeListTab.svelte / NodeViewTab.svelte
        │   ├── PredicateListTab.svelte / TripleListTab.svelte / TripleDetailTab.svelte
        │   ├── TripleAddTab.svelte / tripleAddTypeUtils.js
        │   ├── TripleTemplateForm.svelte / TemplateYamlPopup.svelte
        │   ├── PromptListTab.svelte / SettingsTab.svelte
        │   ├── listTabFormat.js / listTabSelection.svelte.js / listTabShared.svelte.js
        │   ├── listSort.svelte.js / formatCommand.js
        │   ├── commandRouter.js / commandEngine.js / commandExecutor.js
        │   ├── commandTree.js / commandHistory.svelte.js / parser.js
        │   ├── popupStore.svelte.js / tabStore.svelte.js / bannerStore.svelte.js
        │   ├── dirtyFormStore.svelte.js / keyboardShortcuts.svelte.js / historyStore.svelte.js
        │   ├── userConfig.svelte.js / markdown.js
        │   └── sparql/                  # SPARQL query editor (CodeMirror 6)
        │       ├── SparqlQueryEditor.svelte / SparqlResultTable.svelte
        │       ├── sparqlStore.svelte.js / sparqlLanguage.js
        └── lib/__tests__/              # Vitest component tests
            ├── commandRouter.test.js / commandEngine.test.js
            ├── commandHistory.test.js / parser.test.js
            ├── ConfirmDialog.test.js / DynamicForm.test.js
            ├── FormField.test.js / FormTab.test.js
            ├── formatCommand.test.js / optimisticStore.test.js
            ├── popupStore.test.js / SettingsTab.test.js
            ├── tabStore.test.js
            └── tripleAddTypeUtils.test.js
```

---

## GUI + CLI Parity Requirement

**All functionalities MUST be accessible via BOTH GUI and CLI.** No feature may be CLI-only or GUI-only. This means:

- Every `!command` must have a corresponding GUI panel (form, tab, or overlay) accessible through the command bar.
- Every GUI form/panel must have a corresponding `!command` accessible via the centralized command box.
- When adding a new feature, implement both the CLI handler (backend) and the GUI component (Svelte) simultaneously.
- The authoritative command metadata is generated by `src/semantika/server/command/registry.py` (backend). The frontend fetches it on startup via `GET /api/v1/command/tree`.

**Exception**: LLM co-writing ("cowrite") is GUI-only. It requires per-field diff visualization and Accept/Reject controls, which are impractical in CLI. Cowrite enhances existing parity-compliant commands and does not introduce new functionality that would need CLI parity.

---

## Cowrite (LLM-Assisted Editing)

Semantika provides an **Ask LLM** button on dynamic forms (``!node add``, ``!predicate add``, ``!triple add``, etc.) that opens a slide-in panel for AI-assisted editing.

### How it works

1. Fill in form fields (or leave empty).
2. Click **✨ Ask LLM** in the form toolbar.
3. Type an instruction (e.g. "make this more formal", "add more detail", "translate to French").
4. The LLM returns per-field diffs with inline visualization (red strikethrough for deleted text, green highlight for inserted text).
5. Accept/Reject per field, or Accept All / Reject All.
6. Iterate with refinement instructions.

### Architecture

| Layer | Location | Purpose |
|-------|----------|---------|
| Backend engine | ``lightercore.cowrite.engine`` | Protocol prompt, LLM response parsing, diff computation |
| Style cascade | ``lightercore.cowrite.style`` | Generic cascade style loader (general + per-domain) |
| API route | ``src/semantika/server/routes/cowrite.py`` | ``POST /api/v1/cowrite`` — validates, loads style, calls engine |
| Style defaults | ``src/semantika/core/cowrite_defaults.py`` | Shipped defaults for ``cowrite_style*.md`` files |
| Frontend engine | ``@lightercore/ui/cowrite/CowriteEngine.svelte.js`` | Session state machine, API calls, accept/reject logic |
| Frontend button | ``@lightercore/ui/cowrite/CowriteButton.svelte`` | "✨ Ask LLM" toolbar button |
| Frontend panel | ``@lightercore/ui/cowrite/CowritePanel.svelte`` | Slide-in overlay with diff visualization + controls |
| Form integration (DynamicForm) | ``web/src/lib/DynamicForm.svelte`` | Generic ``getValues()``/``setField()`` wiring — all DynamicForm-based commands get cowrite for free |
| Form integration (triple batch) | ``web/src/lib/TripleAddTab.svelte`` | Multi-row batch cowrite — serializes rows as ``row_0_subject_id`` etc., maps edits back to individual cells |
| Context/RAG | ``src/semantika/server/cowrite/context.py`` | Writing samples DB table, ``gather_context()`` returns recent samples for style injection |

### Style Files

Style files live at ``~/.config/semantika/cowrite_style*.md`` and are auto-seeded on first access:

| File | Domain |
|------|--------|
| ``cowrite_style.md`` | General (cross-cutting rules) |
| ``cowrite_style_node.md`` | Node labels, definitions, code formatting |
| ``cowrite_style_predicate.md`` | Predicate IDs, labels |
| ``cowrite_style_triple.md`` | Triple pattern style |
| ``cowrite_style_unit.md`` | Unit type descriptions |
| ``cowrite_style_review.md`` | Review comments |
| ``cowrite_style_proof.md`` | Proof evidence descriptions |

### Writing Samples

Context gathering (writing samples RAG) uses a ``cowrite_samples`` table in the graph DB. ``gather_context()`` in ``src/semantika/server/cowrite/context.py`` retrieves up to 5 most recent samples for style matching. **Collection is not yet implemented** — no code triggers saving a writing sample after approved edits. When collection is added, samples will be inserted into ``cowrite_samples`` and automatically picked up by ``gather_context()`` on subsequent cowrite requests.

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
- `POST /execute` — expand + send to LLM with multi-round tool-calling (sync JSON)
- `POST /execute/stream` — SSE streaming variant
- `POST /execute/resume` — resume after HITL confirmation

The frontend **always calls `/expand` first** to show the expanded template in a preview dialog before sending to the LLM.

### LLM Action Approval (HITL)

When the LLM issues write-level tool calls, the tool loop gates them behind user confirmation:

1. The backend returns `{"type": "confirm_tool", "session_id", "batch": [...]}`
2. The frontend shows a per-item approval dialog (`ConfirmDialog.svelte`) with:
   - Full command display (no truncation, includes flags)
   - Per-item **[Approve]** / **[Tell LLM what to do instead…]** buttons
   - Global **[Approve All]** / **[Tell LLM what to do instead (global)…]** buttons
3. On submit, `POST .../resume` receives `{session_id, decisions, feedback}`
4. The backend injects user feedback as a conversation message and includes it in rejected tool results

### Resume endpoints with feedback support

- **Chat**: `POST /api/v1/llm/chat/resume` — accepts `feedback` (dict per-index or global string)
- **Prompt commands**: `POST /api/v1/prompt-commands/execute/resume` — same `feedback` support
- **lightercore**: `resume_execution()` accepts `feedback: dict[int, str] | str | None`
- Feedback is injected as a user message summarising rejected tools + reason
- Individual rejected tool results include: `"User rejected {cmd}, with the feedback: {fb}"`

The `--seed` flag on `semantika-dev` creates demo prompt commands for testing.
Prompt files are only seeded **if they don't already exist** — your edits survive
across restarts.  Use ``!llm prompt list`` and ``!llm prompt reset`` to inspect
or restore shipped defaults.

## Built-in Multi-Turn Commands (/ prefix)

Semantika ships with built-in prompt commands that use multi-turn LLM flows.
These are registered as special cases in ``prompt_commands.py``.

### ``/template`` — two-turn flow

| Turn | Purpose | Tools | HITL |
|------|---------|-------|------|
| T1 | Predicate discovery | ``predicate.search``, ``predicate.add`` | Yes (predicate.add) |
| T2 | YAML template generation | ``context.get``, ``template.save``, ``template.list``, ``template.view``, ``predicate.search`` | Yes (template.save) |

Turn prompts live at ``~/.config/semantika/commands/_template_turns/turn1.md``
and ``turn2.md`` (user-editable).  Shipped defaults are in
:data:`~semantika.server.llm.prompt_defaults.DEFAULT_TURN1` and
:data:`~semantika.server.llm.prompt_defaults.DEFAULT_TURN2`.

### ``/text-to-triples`` — three-turn flow (also accessible as ``/ttt``)

Translates natural-language text into semantic triples by discovering
entities, relationships, and templates in separate focused turns.

| Turn | Purpose | Tools | HITL |
|------|---------|-------|------|
| T1 | Node discovery | ``node.search``, ``node.add`` | Yes (node.add) |
| T2 | Template + predicate discovery | ``template.list``, ``template.view``, ``predicate.search``, ``predicate.add`` | Yes (predicate.add) |
| T3 | Triple creation | ``context.get``, ``triple.add``, ``template.list``, ``template.view``, ``template.save``, ``node.search`` | Yes (triple.add) |

Turn 3 includes **post-loop validation**: after the tool loop completes,
all ``!triple.add`` calls are checked against the context store.  If any
reference non-existent nodes or predicates, an automatic corrective prompt
is injected and the loop re-enters (max 3 correction rounds).

Turn prompts live at ``~/.config/semantika/commands/_text_to_triple_turns/``
(turn1.md, turn2.md, turn3.md).  Shipped defaults are in
:data:`~semantika.server.llm.prompt_defaults.DEFAULT_TTT_TURN1`,
:data:`~semantika.server.llm.prompt_defaults.DEFAULT_TTT_TURN2`, and
:data:`~semantika.server.llm.prompt_defaults.DEFAULT_TTT_TURN3`.

## Context System (``!context.get``)

Multi-turn flows use a **context store** (in-memory, per-session) to pass
structured data between turns.  After each turn, the backend automatically
collects created/found entities from tool call results into the context:

```python
{
  "nodes":       [{"id": "BOOK_001", "labels": {"en": "..."}}, ...],
  "predicates":  [{"id": "rs:hasAuthor", "labels": {"en": "..."}}, ...],
  "templates":   [{"name": "book-author", "description": "...", "params": 2}]
}
```

The LLM retrieves this data via ``!context.get --type all`` (READ-level,
no HITL) to get exact IDs instead of guessing or relying on free-text
summaries.  This replaces the old ``$AVAILABLE_PREDICATES`` injection
pattern in ``/template`` T2.

## Dedicated LLM Tools (``@llm_tool``)

Semantika uses a **separate LLM tool registry** independent from the CLI ``!command``
registry.  The ``POST /api/v1/llm/chat`` endpoint uses dedicated AI-optimised tools
that call graph services directly — no CLI flag parsing, no frontend-shaped response
wrapping.

### Architecture

``src/semantika/server/llm/tools/``

| File | Purpose |
|------|---------|
| ``__init__.py`` | ``@llm_tool()`` decorator, registry, ``get_llm_tools()``, ``dispatch_llm_tool()`` |
| ``graph.py`` | ``graph.stats`` |
| ``node.py`` | ``node.search``, ``.view``, ``.create``, ``.update``, ``.delete`` |
| ``predicate.py`` | ``predicate.search``, ``.view``, ``.create`` |
| ``triple.py`` | ``triple.search``, ``.add``, ``.delete`` |
| ``template.py`` | ``template.list``, ``.view``, ``.apply`` |
| ``search.py`` | ``search.fts`` |
| ``sparql.py`` | ``sparql.query``, ``.status`` |
| ``system.py`` | ``system.now`` |
| ``review.py`` | ``review.status`` |
| ``unit.py`` | ``unit.search``, ``.info`` |

### Tool registration

Tools are registered with the ``@llm_tool()`` decorator::

    @llm_tool(
        name="node.search",
        description="Search nodes by ID, label, or FTS text query",
        params=[{"name": "q", "type": "string", "description": "Search query", "required": True}],
        permission_level=PermissionLevel.READ,
    )
    def llm_node_search(q: str = "", **kwargs) -> dict:
        ...

### Return format

Every tool returns a uniform dict::

    # Success
    {"success": True, "data": {...}}

    # Error
    {"success": False, "error": "descriptive message"}

### Permission model

- **READ** tools execute immediately without confirmation
- **WRITE** tools gate behind HITL approval (same ``confirm_tool`` mechanism as CLI commands)
- Permission is resolved via ``get_llm_tool_level()``, passed as ``get_tool_level_fn`` to ``run_tool_loop``
- Falls back to CLI command registry level if the tool path isn't in the LLM registry

### Why separate tools?

| CLI commands | LLM tools |
|--------------|-----------|
| ~40+ subcommands, one per operation | ~22 higher-level tools |
| Frontend-shaped responses (``type``, ``title``, ``data``) | Structured data (``success``, ``data``/``error``) |
| CLI flag parsing + positional args | Clean keyword arguments |
| Designed for human consumption | Designed for AI consumption |
| ``!node add concept|media book|scholarly paper|...`` | ``node.create`` with ``type`` param |

### Chat endpoint migration

The ``POST /api/v1/llm/chat`` endpoint now uses ``get_llm_tools()`` (not ``defs_to_tools(get_command_definitions())``).
The dispatch was changed from ``dispatch()`` (CLI pipeline) to ``dispatch_llm_tool()`` (direct service calls).
``get_tool_level_fn=get_llm_tool_level`` is passed for permission resolution.

The prompt commands endpoint (``POST /api/v1/prompt-commands/execute``) continues to use CLI definitions
for backward compatibility with multi-turn flows.

### Future: lightercore extraction

The ``@llm_tool`` decorator, registry, dispatch, and permission helpers are currently
vendored in ``semantika.server.llm.tools``.  A future extraction to
``lightercore.llm.tools`` will make them shared with lighterbird.

## Templates (``!template``)

Templates are reusable triple patterns stored as YAML files in
``~/.config/semantika/templates/``.

| Command | Permission | Purpose |
|---------|-----------|---------|
| ``!template list`` | READ | List available templates |
| ``!template view`` | READ | View a template's structure |
| ``!template save`` | WRITE | Save a new template definition |
| ``!template use`` | WRITE | Apply a template: creates nodes from labels, then adds triples |

``!template use`` accepts labels (not just existing node IDs) for
``type: node`` parameters.  Labels can be plain text, ``LANG::TEXT``
pairs, or JSON dicts for multi-language support::

    !template use book --subject "The Great Gatsby" --author "F. Scott Fitzgerald"
    !template use book --subject '{"en":"Gatsby","fr":"Gatsby le Magnifique"}'
    !template use book --subject "en::Gatsby, fr::Gatsby le Magnifique"

**Key files**:
- ``src/semantika/server/command/handlers/context.py`` — store, population,
  and ``!context.get`` handler
- ``src/semantika/server/routes/prompt_commands_helpers.py`` — dispatch
  wrapper that calls ``collect_into_context()`` after each tool execution

## Optimistic UI Updates

Write operations that go through the GUI (list tabs, command bar) should update the UI **immediately** using the optimistic pattern in `web/src/lib/optimisticStore.svelte.js`. See `web/AGENTS-web.md` → Optimistic UI Pattern for the full guide.

**Safe for optimistic updates**: deletes, renames, toggles, trash operations.
**NOT safe**: LLM interactions, multi-step creates, confirmation-gated commands, file I/O, backup restore.

## Prompt File Management (``!llm prompt``)

Semantika ships with several editable prompt files that control LLM behavior.
You can inspect, edit, and reset them via ``!llm prompt`` commands or the GUI
tab at ``!llm prompt list``.

| File | Logical Name | Purpose |
|------|-------------|---------|
| ``system_prompt.md`` | ``system-prompt`` | Base system prompt (tool usage, operational rules) |
| ``AGENTS.md`` | ``agents`` | User style instructions (appended to base prompt) |
| ``commands/_template_turns/turn1.md`` | ``template/turn1`` | Predicate discovery prompt for ``/template`` |
| ``commands/_template_turns/turn2.md`` | ``template/turn2`` | YAML generation prompt for ``/template`` |

### Commands

- ``!llm prompt list`` — List all prompt files with modification status
  (opens the prompt management tab in the GUI).
- ``!llm prompt view <name>`` — Show current and default content.
- ``!llm prompt reset <name>`` — Reset a single prompt to its shipped default
  (WRITE-level, HITL confirmation).
- ``!llm prompt reset --all`` — Reset ALL prompt files to defaults
  (WRITE-level, HITL confirmation).

### GUI

- **Prompt management tab**: ``!llm prompt list`` opens a tab showing all
  files with ``!modified`` badges, View/Edit/Reset buttons, and an inline
  text editor.
- **Banner**: When any prompt file differs from its default, a persistent
  yellow banner appears on the home page: *"Custom LLM prompts active"*.
  Click the ✕ to dismiss.
- **Reset all**: Available in the prompt management tab header.

### How defaults work

Shipped defaults are defined centrally in
``src/semantika/server/llm/prompt_defaults.py`` using
:class:`lightercore.prompt_files.PromptFile` descriptors. The
:class:`lightercore.prompt_files.PromptFilesManager` compares file content
on disk against these defaults (whitespace-normalised) to detect
modifications.  ``!llm prompt reset`` writes the default back to disk.

## System Prompt Customization

Semantika uses a **two-file model** for LLM system prompt customisation:

| File | Purpose | Default Source |
|------|---------|---------------|
| ``~/.config/semantika/system_prompt.md`` | **Base prompt** — the app's operational instructions (tool usage, batch operations, error recovery). For power users who want deep customisation. | :data:`~semantika.server.llm.system_prompt.DEFAULT_SEMANTIKA_PROMPT` |
| ``~/.config/semantika/AGENTS.md`` | **User style instructions** — your personal naming conventions, language preferences, workflow rules. Always **appended** to the base prompt. This is the primary customisation point for regular users. | :data:`~semantika.server.llm.system_prompt.DEFAULT_AGENTS_STYLE` |

### How it works

- Both files are **auto-seeded on first access** (lazy seeding) — no files are
  created at startup, only when ``load_system_prompt()`` is first called
  (typically on the first chat or prompt command).
- The combined system prompt = content of ``system_prompt.md`` + ``"\n\n"`` +
  content of ``AGENTS.md``.
- **After editing**, call ``POST /api/v1/llm/reload-prompt`` to apply
  changes without restarting the server.
- **View the current prompt**: ``GET /api/v1/llm/prompt`` returns
  ``{"prompt": "...", "path": "..."}``.

### Which file to edit?

- **Most users**: Edit ``AGENTS.md`` to add your graph naming conventions,
  language rules, or workflow preferences.  The base prompt stays as shipped.
- **Power users**: Edit ``system_prompt.md`` to change the LLM's fundamental
  behaviour (tone, tool-use patterns, response format).  You can also move
  your ``AGENTS.md`` content into ``system_prompt.md`` if you prefer a single
  file — both approaches work.
- **Note**: Editing ``system_prompt.md`` means you may miss new operational
  instructions shipped in future app upgrades.  Your ``AGENTS.md``
  customisations are never affected by upgrades.

### Example

Edit ``~/.config/semantika/AGENTS.md``:

```markdown
# AGENTS.md — Additional context for Semantika AI

## Graph Naming Conventions
- Always provide labels in eo, fr, en
- Predicate IDs follow Esperanto grammar: -o for subject-is, -on for object-is
```

The next LLM interaction will append these rules after the base prompt.

### Migration note

Previous versions of Semantika either:
- Used a single merged ``system_prompt.md`` (with AGENTS.md content migrated in)
- Or used ``AGENTS.md`` as the only customisation point

Both are handled automatically: if your ``system_prompt.md`` contains the
migration marker, it is returned as-is (no double-append).  If you want to
switch to the two-file model, simply delete ``system_prompt.md`` and the
next access will re-seed it fresh, re-appending your AGENTS.md content.

## Service Caching

`get_services()` in ``graph/db.py`` caches service instances (``NodeService``, ``PredicateService``, ``TripleService``, ``ProofService``, ``ReviewService``, ``PredicateGroupService``) after the first call.  This avoids re-instantiating the entire service layer on every command dispatch.

- Call :func:`reset_services` to clear the cache after a database reset or restore.
- When writing tests that share a global ``get_services()``, call ``reset_services()`` between test runs to avoid state leakage.
- The ``FTS5Manager`` in ``core/fts.py`` provides shared FTS5 index operations to both ``NodeService`` and ``PredicateService``, replacing the duplicated ``_ensure_fts`` / ``_index_fts`` / ``_remove_from_fts`` / ``_rebuild_fts`` pattern.

## Global Configuration (``semantika.jsonc``)

Semantika reads a global config file from ``~/.config/semantika/semantika.jsonc`` (JSONC — JSON with ``//`` comments).  Falls back to ``semantika.json`` if the ``.jsonc`` variant doesn't exist.  The file is optional; built-in defaults are used when absent.

| Key | Default | Description |
|-----|---------|-------------|
| ``node_iri`` | ``https://semantika.local/node/$id`` | IRI template for nodes (``$id`` → internal ID) |
| ``predicate_iri`` | ``https://semantika.local/resource/$id`` | IRI template for unknown-prefix predicates |

Known-prefix predicates (``rdf:type``, ``rdfs:label``, etc.) always use their fixed standard namespaces regardless of the configured template.

### Commands

- ``!system reindex`` — Clear the SPARQL RocksDB cache and re-sync all triples from SQLite using the current IRI templates.  Run after changing ``node_iri`` / ``predicate_iri`` in ``semantika.jsonc``.  Requires ``--confirmed``.
- ``!node add --canonical <iri>`` / ``!node modify --canonical <iri>`` — Set a custom canonical IRI for a node (stored in the ``iri`` column; overrides the configured template).
- ``!predicate add --canonical <iri>`` — Same for predicates.

### Implementation notes

- The ``iri`` column in the ``nodes`` and ``predicates`` SQLite tables is **empty** for entities using the default template.  It is populated only when ``--canonical`` is specified.
- SPARQL enrichment uses a **dual-path** lookup:
  1. IRIs matching the template prefix → string-op → query by internal ID.
  2. Other IRIs (custom ``--canonical``, known-prefix predicates) → query by ``iri`` column.
- RocksDB sync hooks resolve IRIs via a cache-aware method (``_resolve_iri``) that checks the ``iri`` column first, falling back to template computation.

## Built-in Ontology Seeding (YAML + Python Fallback)

Semantika seeds its built-in predicates, type nodes, and unit ontology from
YAML files with a Python fallback for required predicates.

### Source files

| File | Contents | Editable by non-coders? |
|------|----------|------------------------|
| ``graph/builtins.yaml`` | Predicate catalog (W3C / Tier 1–2 / File ``sm:``) + type nodes (PHOTO, BOOK, PAPER, etc.) | Yes |
| ``graph/units.yaml`` | Unit type hierarchy, SI base/derived units, SI prefixes | Yes |
| ``graph/_required_predicates.py`` | Python fallback dict — every predicate referenced by built-in commands | No (developers only) |
| ``graph/builtin_loader.py`` | YAML loading logic with caching and fallback | No (developers only) |

### Resolution order

1. **User-editable YAML** at ``~/.config/semantika/builtins.yaml`` (or ``units.yaml``)
2. **Shipped default YAML** bundled in the package
3. **Python fallback** (``_required_predicates.py``) — only for predicates that
   built-in commands need by name

If a required predicate is missing from the YAML, a warning is logged and the
Python fallback is used.  This ensures the app never breaks even if someone
accidentally deletes a predicate from the YAML file.

### Usage

- Edit ``~/.config/semantika/builtins.yaml`` to modify the predicate catalog
- Run ``!builtins reload`` to apply changes without restarting the server
- Or restart the server for a fresh seed

### Commands

- ``!builtins reload`` — Re-read YAML files and re-seed (uses ``INSERT OR IGNORE``)

## Semantika Predicate Namespace (``sm:``)

Semantika ships with a **standard predicate catalog** in the ``sm:`` (Semantika) namespace. The namespace is registered in all IRI-resolution code paths (``graph/constants.py`` — single source of truth), giving ``sm:`` predicates a stable IRI at ``https://sm.ronzz.org/predicates/``
(``sm:depicts`` → ``https://sm.ronzz.org/predicates/depicts``).

### Design rules

- ``sm:`` predicates **complement, never replace, W3C standards.** The existing ``rdf:``, ``rdfs:``, and ``owl:`` predicates are left completely untouched.
- ``sm:`` fills gaps that W3C doesn't cover. See ``graph/builtins.yaml`` for the canonical catalog.
- Core ``sm:`` predicates (Tier 1) are **soft-protected** from accidental deletion — ``!predicate delete`` warns unless ``--force`` is used.
- All predicates are seeded via ``BuiltinTypeService.ensure_builtins()`` at app startup (idempotent).

### Catalog summary

| Tier | Contents | Protected | Seeded |
|------|----------|-----------|--------|
| W3C | ``rdf:type``, ``rdfs:subClassOf``, ``rdfs:label``, ``owl:sameAs``, ``owl:disjointWith``, ``owl:inverseOf``, ``rdfs:seeAlso`` | No | Always |
| Tier 1 (core) | ``sm:depicts``, ``sm:programmingLanguage``, ``sm:theme``, ``sm:dimension``, ``sm:canonicalLink``, ``sm:hasSource``, ``sm:attributedTo``, ``sm:partOf`` | Yes (``--force`` to delete) | Always |
| Tier 2 (extended) | ``sm:isAbout``, ``sm:relatesTo``, ``sm:contradicts``, ``sm:requires``, ``sm:hasExample``, ``sm:definedIn``, ``sm:succeededBy``, ``sm:precededBy``, ``sm:similarTo``, ``sm:hasPart`` | No | Always |
| File (internal) | ``:hasFilePath``, ``:hasFileMime``, ``:hasFileSize``, ``:hasFileSource`` | No | Always |

### Reasoning: no W3C duplication

Equivalence mapping (e.g. ``sm:instanceOf`` → ``rdf:type``) is deceptive — RDF/RDFS/OWL inference happens inside the SPARQL engine at query time, and a nonstandard alternative bypasses built-in subclass transitivity, type propagation, and domain/range inference. Maintaining two parallel type systems in the same database recreates the fragmentation problem we set out to solve.

### Known prefix map

All code that resolves IRIs (``compute_iri``, ``_to_uri``, ``_format_turtle_uri``) imports from a single source of truth in ``graph/constants.py``:

```python
KNOWN_PREFIXES = {
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd":  "http://www.w3.org/2001/XMLSchema#",
    "owl":  "http://www.w3.org/2002/07/owl#",
    "sm":   "https://sm.ronzz.org/predicates/",
}
```

See GitHub issue [#134](https://github.com/Ron-RONZZ-org/semantika/issues/134) for full discussion.

## User Configuration

Semantika supports persistent user preferences stored as JSON at `~/.local/share/semantika/user_config.json`:

| Setting | Type | CLI flag | Effect |
|---------|------|----------|--------|
| **Locale** | string | `--locale CODE` | Interface language |
| **Normalise node IDs** | bool | `--normalise-node-ids on|off` | Strip diacritics (â→a) from node IDs on creation |
| **Strip predicate diacritics** | bool | `--strip-predicate-diacritics on|off` | Strip diacritics from predicate IDs on creation |

- CLI: `!user config` with optional flags above (opens the settings tab when run without flags)
- GUI settings tab: Type ``!user config`` to open the settings tab with toggles
- API: `GET/PATCH /api/v1/user/config`
- The frontend fetches config on startup and falls back to browser language
- Normalisation applies only to new IDs (no retroactive cleanup)

## Inline Code Storage

Source code nodes (``!node add code``) support two modes:
- **Inline paste** (default): Use ``--code`` to pass source text directly. Content is stored in the ``code_content`` and ``code_language`` columns of the ``nodes`` table, making it FTS5-searchable.
- **File upload**: Use ``--path`` to reference a source file (existing behavior, still supported).

The ``--code`` flag takes precedence over ``--path`` when both are provided. The ``--no-copy`` flag is removed for ``!node add code`` since text-only code has no file to copy.

## Form Metadata Enhancements (Backend → Frontend)

The ``@command`` decorator's param/flag dicts support these metadata keys for enhanced GUI rendering:

| Key | Type | Effect |
|-----|------|--------|
| ``placeholder`` | string | Example input shown in the form field |
| ``group`` | string | Mutual exclusion group — flags sharing a group render as a toggle |
| ``suggestions`` | list of strings | Autocomplete suggestions rendered as ``<datalist>`` |
| ``type: "code"`` | string | Renders a multi-line ``<textarea>`` with Preview (Ctrl+Shift+P) |

All ``!xxx add`` commands (node, predicate, triple, unit, proof, predicate.group) now include ``placeholder`` text.

## Post-Submit Redirect & Highlight

When a form submits and creates a new entity (node or predicate), the default behavior is now to **close the form tab** and **redirect to the list tab** with a brief green pulse animation on the newly created row.

### Mechanism

1. The form tab's ``data`` includes top-level metadata keys: ``returnType`` (e.g. ``"node-list"``), ``returnTokens`` (e.g. ``["node", "list"]``), ``returnTitle``, and optionally ``returnIdKey``.
2. ``FormTab.handleFormSubmit()`` checks: if ``resp.ok`` AND ``result.data.node.node_id`` (or ``result.data.predicate.predicate_id``) exists AND ``returnType``/``returnTokens`` are set → redirect. Otherwise → original status-tab behavior.
3. On redirect: close form tab, re-fetch fresh list data via ``POST /api/v1/command`` with ``returnTokens``, open/update the list tab with ``_highlight`` set to the new entity ID.
4. The list component (``NodeListTab``, ``PredicateListTab``) uses ``createHighlightManager`` from ``@lightercore/ui/highlight.svelte.js``, which watches for ``data._highlight`` in a ``$effect``, scrolls the matching row into view, and applies a CSS pulse animation.

### Coverage

The redirect fires for **every** ``!node add <type>`` and ``!predicate add`` — all backend handlers return either ``node.node_id`` or ``predicate.predicate_id`` in their response ``data``. Forms without ``returnType`` (``!triple add``, ``!unit add``, ``!proof add``) keep the original behavior.

### Testing

8 component tests in ``FormTab.test.js`` cover: original-behavior preservation (no returnType → status tab), error responses don't close form, full redirect with ``returnTokens``, ``returnIdKey`` persistent-tab update, list-fetch failure fallback, predicate_id redirect, and correct tab close.

The ``applyHighlight()`` DOM function is tested with 8 unit tests in lightercore's ``highlight.test.js``.

## Node Handler Module Split

``node.py`` exceeded 500 lines. The specialised subcommands were extracted into sibling modules:

| Module | Commands | Pattern |
|--------|----------|---------|
| ``node_attachment.py`` | ``!node add attachment photo\|video\|file\|code`` | File-attachment nodes with auto triples |
| ``node_media.py`` | ``!node add media book\|film\|song\|game\|podcast`` | Creative works, pure metadata |
| ``node_scholarly.py`` | ``!node add scholarly paper\|patent\|conference`` | Academic/IP works, pure metadata |

The general ``!node add concept``, CRUD, merge, and rename remain in ``node.py``. The ``--inverse`` flag was removed from concept (it is a predicate property, not a node property).

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
11. **No backward compatibility guarantee (pre-release).** Pre-1.0 versions may remove or rename flags, options, and commands without a deprecation period. A clear error message pointing to the replacement is sufficient — no migration shims, no phase gates.

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
| Test directory | `tests/` |

### Testing Principles

1. **Test via the public API wherever possible.** Prefer integration tests over isolated unit tests.
2. **Console errors in browser tests indicate real bugs** — fix them even if tests pass.
3. **Every bug fix must include a test that would have caught the regression.**

For execution commands, dev server lifecycle, and user-simulation testing, see ``tests/AGENTS-tests.md``.

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

Semantika supports user-defined command hooks via ``~/.config/semantika/hooks/*.py`` —
every ``.py`` file in this directory is loaded at startup via ``exec()`` with a
pre-populated namespace (``command``, ``call_system_command``, etc. — no imports needed).
**This is effectively arbitrary code execution from disk.** The following considerations apply:

- The hooks directory lives in the XDG config directory, which should be treated as a **trusted
  location** by the user.
- A malicious ``.dev`` file or a compromised config directory could inject arbitrary code.
- The ``--no-hooks`` flag (on ``semantika-dev`` or ``create_app(no_hooks=True)``) skips
  loading user hooks entirely — use it during debugging or when the hooks directory is suspect.
- Files are loaded in alphabetical order; ``__init__.py``, hidden files (``.`` prefix),
  and editor backups (``~`` suffix) are skipped.
- One bad file does **not** block others — errors are logged and the file is skipped.
- **Recommendation**: If you share your config directory across machines, audit the hooks
  directory for unexpected content before running Semantika.

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
| Tests | `tests/AGENTS-tests.md` | Dev server lifecycle, E2E execution, data isolation, user-simulation testing |
| Web | `web/AGENTS-web.md` | Svelte SPA, command-bar UI, prompt command autocomplete, locale

---

## Dependency and Inheritance Map

```
Root AGENTS.md (global rules)
    │
    ├── core/AGENTS-core.md        DB, FTS5, paths, interactive helpers
    ├── graph/AGENTS-graph.md      Triple store: nodes, predicates, triples, review, proof
    ├── server/AGENTS-server.md    FastAPI backend, API routes, LLM
    ├── scripts/AGENTS-scripts.md  Dev CLI, seed data, test infra
    ├── tests/AGENTS-tests.md      Dev server lifecycle, E2E, data isolation
    └── web/AGENTS-web.md          Svelte SPA frontend
```

Local rules override global rules. Module-level files focus on domain-specific behavior, constraints, and invariants.
