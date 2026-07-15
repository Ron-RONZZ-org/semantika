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
│       ├── graph/               # Triple store services (17 source files + services/)
│       │   ├── __init__.py + constants.py + db.py + file_helpers.py
│       │   ├── node_helpers.py + node_service.py + node_merge_mixin.py + node_fts.py
│       │   ├── predicate_service.py + predicate_group_service.py
│       │   ├── triple_service.py + triple_turtle.py
│       │   ├── review_service.py + proof_service.py
│       │   ├── sparql/__init__.py + sparql/engine.py  # SPARQL engine (Oxigraph cache)
│       │   ├── unit_service.py + unit_builder.py + unit_decomposition.py
│       │   ├── unit_errors.py + unit_parser.py + unit_seed_data.py
│       │   ├── builtin_type_service.py + builtin_seed_data.py
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
│               │   ├── node_specialised.py  # !node add photo|video|file|code
│               │   ├── predicate.py / predicate_group.py / predicate_trash.py
│               │   ├── triple.py / review.py
│               │   ├── backup.py / reset.py
│               │   ├── context.py  # Context store for multi-turn flows (!context.get)
│               │   ├── help.py
│               │   ├── llm.py
│               │   ├── trash.py
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
│               ├── sparql.py    # /api/v1/query/sparql — SPARQL 1.1 Protocol endpoint
│               ├── prompt_commands.py  # /api/v1/prompt-commands/* — list, expand, execute, SSE stream
│               │   Turn prompts use named-only expansion ($ARGUMENTS, $TEMPLATE_DESCRIPTION, $STYLE_EXAMPLE).
│               │   /template supports two-turn HITL: predicate.add in turn1, template.save in turn2.
│               │   /text-to-triples supports three-turn HITL: nodes in T1, templates+predicates in T2,
│               │     triples with post-loop validation in T3.
│               │   $STYLE_EXAMPLE auto-injected from most recently modified user-created template.
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

## Node Handler Module Split

``node.py`` exceeded 500 lines. The specialised subcommands (``!node add photo|video|file|code``) were extracted to ``node_specialised.py``. The core CRUD, concept add, merge, and rename remain in ``node.py``.

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
