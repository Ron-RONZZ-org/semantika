# Semantika

Semantika — knowledge graph CLI+GUI with LLM. A semantic triple store with a Svelte frontend, BYOK (Bring Your Own Key) LLM-native integration, and a **standard SPARQL 1.1 endpoint**. AGPL-3.0.

## Project Family

Semantika is the **third-generation** of a knowledge-graph toolchain. Understanding its ancestry clarifies design decisions:

| Project | Role | Relationship |
|---------|------|-------------|
| **[A-semantika](../A-semantika)** | EO-first CLI ancestor | **Business-logic reference.** Forked and migrated from Esperanto to English. Core triple store services (NodeService, PredicateService, TripleService, ReviewService, ProofService, unit ontology) originate here. Refer to A-semantika when implementing graph operations, Turtle export, or review/proof mechanics. |
| **[lighterbird](../lighterbird)** | Mature sister PIM app | **UX/LLM/DB reference.** The command-bar interaction model, command tree + dispatch architecture, autocomplete engine, tab/result-panel UI, LLM provider integration (OpenAI/Ollama with text-based command generation), and prompt commands (`/` prefix) are all ported from lighterbird. Refer to lighterbird when designing frontend components, command routing, LLM tool-calling, or keyring-based config management. |
| **[lightercore](../lightercore)** | Shared core library | **Infrastructure reference.** DB, paths, exceptions, CRUD, backup, permissions, prompt_commands, LLM config, profile management come from lightercore — the canonical source shared with lighterbird. |
| **Semantika (this repo)** | Modern English successor | **Combines the best of all.** Graph business logic from A-semantika + UX/LLM patterns from lighterbird + shared infrastructure from lightercore + Svelte 5 SPA frontend. |

## Interaction Model

Semantika uses a **centralized command box** with three input modes and a **tab-based result system**:

```
┌──────────────────────────────────────────────────────────┐
│ ❯ !node add --label "Concept"             ← ! built-in  │
│ ❯ /weekly 7 productivity                 ← / prompt     │
│ ❯ What do I know about X?                ← natural text │
│                                                          │
│  ┌────────── Home tab (pinned) ──────────┐              │
│  │  Brand header + graph stats           │              │
│  │  Conversation area (LLM chat,         │              │
│  │  prompt command replies)              │              │
│  │  Command input                        │              │
│  └───────────────────────────────────────┘              │
│                                                          │
│  ┌─── Tab bar ───────────────────────────┐              │
│  │ ⌂ Home │ 📋 node list │ 📋 result … │  ✕│              │
│  └───────────────────────────────────────┘              │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Active tab content:                                     │
│  (node details, triple tables, graph viz, LLM chat,     │
│   katex, code blocks, images, forms, quizzes)           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

- `!command` — built-in graph operations; results open in a new tab
- **Multi-command input**: chain multiple `!` commands in one message — `!node list !predicate list`. Commands execute sequentially; `!` inside quoted strings ignored.
- `/name [args...]` — user-defined prompt commands; results appear in the Home tab conversation
- `/text-to-triples` or `/ttt` — built-in three-turn flow: translate natural language into semantic triples (nodes → predicates/templates → triples with validation)
- `!template use` — apply a reusable template to create nodes from labels and add triples
- Natural text — free-form LLM chat; results appear in the Home tab conversation
- The **Home tab** is always pinned at index 0 — it shows a compact header once a conversation starts, the conversation history, and the command input box
- Most `!command` results (lists, details, forms, graph views, quizzes) open as separate tabs with a tab bar at the bottom for switching; close with `Esc` or `q`

## Features

### Core Graph Operations
- `!node add/list/view/update/delete/merge/rename` — manage nodes; batch delete with `--prefix`, merge duplicates, rename IDs with full FK cascade
- `!predicate add/list/search/view/update/delete/rename` — manage predicates with descriptions, Wikidata auto-fetch; batch delete with `--prefix`
- `!predicate-group list/view/add/rename/delete/search` — manage predicate groups with member add/remove
- `!triple add` with full literal type support (`--str`, `--int`, `--float`, `--bool`, `--lang`, `--unit`, `--katex`, `--str-dosiero`, `--kodlingvo`)
- `!triple delete` — delete triples with cascade proof removal (interactive picker for partial args)
- `!triple modify` — change subject/predicate/object/type of existing triple
- `!triple list/view` — list all triples or view triples for a node
- `!search <q> [--date-from] [--date-to]` — full-text search with optional date filtering
- `!view <id>` — alias for triples-by-subject view
- `!export [--output FILE] [--base-uri URI]` — export graph in Turtle format to file or stdout
- `!import <data>` or `!import --file <path>` — import Turtle (.ttl) data (inline or from file)
- `!stats` — graph statistics

### Review & Proof
- `!proof add/view/delete` — attach evidence (proofs) to triples
- `!review start [view|quiz]` — interactive triple review with two modes:
  - **view**: show SPO, confirm correct/incorrect
  - **quiz**: multiple-choice with auto-generated distractors via FTS5 similarity
  - Optional `--date-from`/`--date-to` / `--limit` filters
- `!review sessions/view/delete` — manage review sessions

### Trash Management
- `!trash list/restore/delete/purge` — manage soft-deleted nodes
- `!predicate-trash list/restore/delete/purge` — manage soft-deleted predicates

### Triple Templates
- `!template list/view/save/use` — reusable YAML triple patterns stored in `~/.config/semantika/templates/*.yaml`
- `!template use` creates nodes from labels, then adds triples — supports plain text, `LANG::TEXT`, and JSON dict formats
- Templates are LLM-friendly: the LLM can discover, inspect, create, and apply templates via tool-calling

### Unit Ontology
- `!unit list/view/resolve/decompose/add` — unit ontology management

### LLM & AI
- `!llm show/new/set/clear` — LLM provider configuration
- `!llm profile list/show/load/delete` — profile management
- `!ask <question>` — ask the LLM about the graph
- Just type naturally → the LLM translates your intent into commands
- **Multi-round tool-calling**: LLM sees all `!commands` as native tools, calls them via `chat_with_tools`, permission gate returns `confirm_tool` for write/destructive commands
- **Resume with feedback**: `POST /api/v1/llm/chat/resume` supports per-item feedback when rejecting tool calls
- As-you-type command suggestions with node/predicate/predicate-group completion — no memorisation needed

### Prompt Commands (`/` prefix)
Prompt commands are user-defined LLM prompt templates stored as Markdown files:

```bash
# Files: ~/.config/semantika/commands/*.md
# Format: first line starting with "# " = description
#         rest = prompt template with $1, $2, $ARGUMENTS placeholders

# Example: ~/.config/semantika/commands/weekly.md
echo '# Weekly review of what I learned
Review the nodes added in the past $1 days and identify key themes.
Then look at $2 area specifically.' > ~/.config/semantika/commands/weekly.md

# Usage:
/weekly 7 productivity
```

### LLM System Prompt Customization

Semantika uses a **two-file model** for LLM system prompt customisation:

- **`~/.config/semantika/system_prompt.md`** — the base prompt (app's operational
  instructions). Auto-seeded on first access. Edit for deep customisation.
- **`~/.config/semantika/AGENTS.md`** — your personal style instructions (naming
  conventions, language preferences, workflow rules). Auto-seeded and always
  **appended** to the base prompt. This is the primary customisation point.
- **Reload at runtime**: ``POST /api/v1/llm/reload-prompt`` (no server restart)
- **View current prompt**: ``GET /api/v1/llm/prompt``

### Built-in Ontology (YAML Seeding)

Semantika seeds its built-in predicates, type nodes, and unit ontology from **declarative YAML files** with a Python fallback for required predicates.

| File | Contents | Editable by non-coders? |
|------|----------|------------------------|
| `src/semantika/graph/builtins.yaml` | Predicate catalog (W3C / Tier 1–2 / File `sm:`) + type nodes (PHOTO, BOOK, PAPER, etc.) | Yes |
| `src/semantika/graph/units.yaml` | Unit type hierarchy, SI base/derived units, SI prefixes | Yes |
| `src/semantika/graph/_required_predicates.py` | Python fallback dict — every predicate referenced by built-in commands | No (developers only) |

**Resolution order:**
1. User-editable YAML at `~/.config/semantika/builtins.yaml` (or `units.yaml`)
2. Shipped default YAML bundled in the package
3. Python fallback (`_required_predicates.py`) — only for predicates that built-in commands need by name

**Usage:** Edit `~/.config/semantika/builtins.yaml` to modify the predicate catalog, then run `!builtins reload` to apply changes without restarting the server.

### Reactive UI (Optimistic Updates)

Write operations (deletes, trash actions, toggles) update the UI **instantly** — items disappear from list tabs the moment you click Delete, while the API call runs in the background. On the rare occasion a delete fails, the items are restored and an error banner is shown. This pattern is implemented via `web/src/lib/optimisticStore.svelte.js`.

### Backup & Recovery
- `!backup now/list/restore/prune/config` — database backup with multi-strategy support
- `!backup config list/add/modify/delete/test` — backup strategy management
- `!backup export/import` — portable data export/import
- `!reset [--no-backup]` — reset to fresh state

### Built-in Ontology Management
- `!builtins reload` — re-read YAML files (`builtins.yaml`, `units.yaml`) and re-seed (uses `INSERT OR IGNORE`)
- The predicate catalog is editable by non-coders — edit `~/.config/semantika/builtins.yaml` and reload
- A Python fallback (`_required_predicates.py`) ensures required predicates never go missing

### Prompt File Management
- `!llm prompt list` — opens a tab showing all customisable prompt files with modification status badges
- `!llm prompt view <name>` — view current and default content
- `!llm prompt reset <name>` / `!llm prompt reset --all` — restore shipped defaults (HITL confirmed)
- A yellow banner on the home page alerts when prompts deviate from defaults
- Both `system_prompt.md` (base operational instructions) and `AGENTS.md` (user style) are auto-seeded on first access

### User Configuration
- `!user config` — opens a settings tab with locale selector and ID normalisation toggles
- `--locale CODE` — set interface language (e.g. `en`, `fr`, `de`, `eo`)
- `--normalise-node-ids on|off` — strip diacritics (â→a) from node IDs
- `--strip-predicate-diacritics on|off` — strip diacritics from predicate IDs
- Persistent locale badge in the GUI header

### System
- `!system reindex --confirmed` — Clear the SPARQL RocksDB cache and re-sync all triples from SQLite using current IRI templates. Run after changing IRI templates in `semantika.jsonc`.

### SPARQL Endpoint
Semantika includes a **standard SPARQL 1.1 Protocol endpoint** backed by an Oxigraph RocksDB cache with incremental sync from SQLite.

**The SPARQL engine starts automatically** on first query — no special flags or configuration needed. Just install the dependencies and the engine is ready.

**Usage:**

```
# Direct API call (GET)
curl 'http://localhost:6015/api/v1/query/sparql?query=SELECT+*+WHERE+{+?s+?p+?o+}+LIMIT+10'

# Direct API call (POST)
curl -X POST http://localhost:6015/api/v1/query/sparql \
  -H "Content-Type: application/sparql-query" \
  -d 'SELECT * WHERE { ?s ?p ?o } LIMIT 10'

# Via command bar — opens the SPARQL query editor tab
!sparql

# Execute inline
!sparql query 'SELECT * WHERE { ?s ?p ?o } LIMIT 10'
```

**Features:**
- Full SPARQL 1.1: SELECT, ASK, CONSTRUCT, DESCRIBE
- Results enriched with human-readable labels from SQLite
- Context-aware autocomplete (suggests nodes vs predicates based on cursor position)
- Keyboard shortcut: `Ctrl+Enter` to run queries
- Standard content negotiation (`application/sparql-results+json`, `text/turtle`)
- Incremental sync — triples added/removed via `!` commands are immediately available via SPARQL

### Semantika Predicate Namespace (`sm:`)

Semantika ships with **standard predicates** in the `sm:` namespace, giving users a shared vocabulary from day one. Key design:

- `sm:` predicates **complement, never replace, W3C standards.** `rdf:type`, `rdfs:subClassOf`, `rdfs:label`, and `owl:*` are left completely untouched.
- `sm:` fills gaps that W3C doesn't cover (media metadata, knowledge provenance, mereology, etc.)
- Core `sm:` predicates are **soft-protected** from accidental deletion (`--force` to bypass)
- All predicates are seeded at app startup via `BuiltinTypeService.ensure_builtins()` (idempotent)
- The `sm:` namespace is registered in all IRI-resolution paths at `https://sm.ronzz.org/predicates/` (`sm:depicts` → `https://sm.ronzz.org/predicates/depicts`)

The full catalog (W3C + 30+ `sm:` predicates + file metadata + type nodes) is defined in `src/semantika/graph/builtins.yaml` — a declarative YAML file editable by non-coders. A Python fallback (`src/semantika/graph/_required_predicates.py`) ensures required predicates never go missing. See [issue #134](https://github.com/Ron-RONZZ-org/semantika/issues/134) for the design discussion.

**Architecture:**
- SQLite remains the source of truth for all data (nodes, predicates, labels, FTS5, proofs)
- Oxigraph RocksDB stores only bare ID-triples for fast SPARQL evaluation
- Failed sync operations are queued in a backlog with exponential backoff (never silent)

## Architecture

```
semantika/
├── core/        Re-exports from lightercore  — DB, paths, exceptions, CRUD, backup, FTS
├── graph/       Forked from A-semantika      — triple store services, TTL import/export
├── server/      FastAPI backend              — REST API, command engine, LLM provider,
│   └── llm/     Ported from lighterbird      — user config, prompt commands
└── web/         Svelte 5 SPA                 — Command-bar UI (lighterbird pattern),
                                               rich results, / prompt commands
```

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python 3.11+ / FastAPI | Lightweight, async, auto-docs |
| Frontend | Svelte 5 SPA + Vite | Minimal bundle, excellent custom component DX |
| Database | SQLite (WAL mode) | Embedded, zero-config |
| AI | OpenAI-compatible API + Ollama | BYOK: bring your own model/key; multi-round tool-calling (LLM calls ``!commands`` as tools) with permission gate (HITL for write/destructive commands) |
| Credentials | System keyring (via `keyring`) | Never store API keys in DB |
| TTL parsing | `rdflib` | Standard Turtle (.ttl) import |
| HTTP client | `httpx` | Async HTTP for LLM provider calls |

## Quick Start

```bash
# Backend
uv pip install -e ".[dev]"
uv run semantika-dev --seed   # isolated dev server with demo prompt command

# Frontend (separate terminal)
cd web
npm install
npm run dev
```

### Without the frontend (API-only)

```bash
uv run uvicorn semantika.server.app:create_app --factory --port 6015 --reload
```

### Port synchronization

If the backend is on a different port (e.g. 6015 is taken, or you used `--port 0` for an OS-assigned port), set `SEMANTIKA_PORT` before starting the frontend:

```bash
# Terminal 1: start backend on custom port
SEMANTIKA_DATA_DIR=/tmp/semantika-dev uv run uvicorn \
  semantika.server.app:create_app --factory --port 8765 --reload

# Terminal 2: tell Vite proxy where the backend is
SEMANTIKA_PORT=8765 npm run dev
```

In production (built frontend served by FastAPI), port configuration is automatic — the Svelte SPA is served as static files on the same port as the API. No proxy needed.

### Disable file watching

To run the Vite dev server without file watching or HMR (useful when you want manual refresh on restart):

```bash
DISABLE_WATCH=true npm run dev
```

This sets `server.watch: null` and `server.hmr: false` — no chokidar watcher runs and no WebSocket connection is established. Restart the process to see changes.

## Migrating from A-semantika

If you have an existing A-semantika database (Esperanto-column schema), you can
migrate it to the semantika (English-column) schema with the bundled script:

```bash
# Source: your A-semantika user DB
# Target: your semantika data directory
uv run python src/semantika/scripts/migrate_from_a_semantika.py \
    ~/.local/share/A/A-semantika/semantika.db \
    ~/.local/share/semantika/semantika.db
```

The script handles full column renaming (Esperanto → English), table renames,
trash-table migration, and rebuilds FTS indexes. It creates a fresh DB with the
semantika schema and copies all data — no in-place migration needed.

### Column mapping reference

| A-semantika         | semantika           |
|---------------------|---------------------|
| `etikedoj`          | `labels`            |
| `difinoj`           | `definitions`       |
| `difin_text`        | `definition_text`   |
| `priskriboj`        | `descriptions`      |
| `kreita_je`         | `created_at`        |
| `modifita_je`       | `updated_at`        |
| `forigita_je`       | `deleted_at`        |
| `subject_uuid`      | `subject_id`        |
| `object_node_uuid`  | `object_node_id`    |
| `recenzo_sesio`     | `review_sessions`   |
| `recenzo_rezulto`   | `review_results`    |
| `recenzo_rezulto` → `korekta` | `review_results` → `is_correct` |
| `recenzo_rezulto` → `pozicio` | `review_results` → `position` |
| `nodes_rubujo`      | `nodes_trash`       |
| `predicates_rubujo` | `predicates_trash`  |
| `predicate_groups_rubujo` | `predicate_groups_trash` |

## Testing

```bash
# Backend tests (1307 tests)
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=semantika
```

### E2E browser test
```bash
# Start dev server with seed data
uv run semantika-dev --seed &

# Run Playwright E2E test
npx playwright test tests/semantika_full_e2e.mjs
```

## Development Server

For isolated development, use the `semantika-dev` CLI:

```bash
# Start with seed data (creates demo prompt command)
uv run semantika-dev --seed

# Start with clean temp database
uv run semantika-dev
```

The `--seed` flag creates a demo prompt command in `~/.config/semantika/commands/` and reads API keys from the `.dev` file (gitignored).

## API Endpoints

### Graph & Query
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/graph/nodes` | List nodes |
| GET | `/api/v1/graph/nodes/search?q=` | Search nodes |
| POST | `/api/v1/graph/nodes` | Create a node |
| GET | `/api/v1/graph/nodes/{id}` | Get node with triples |
| PATCH | `/api/v1/graph/nodes/{id}` | Update a node |
| DELETE | `/api/v1/graph/nodes/{id}` | Delete a node |
| GET | `/api/v1/graph/nodes/stats` | Graph statistics |
| GET | `/api/v1/graph/predicates` | List predicates |
| GET | `/api/v1/graph/predicates/search?q=` | Search predicates |
| POST | `/api/v1/graph/predicates` | Create a predicate |
| PATCH | `/api/v1/graph/predicates/{id}` | Update a predicate |
| DELETE | `/api/v1/graph/predicates/{id}` | Delete a predicate |
| GET | `/api/v1/graph/triples` | List triples |
| POST | `/api/v1/graph/triples` | Add a triple |
| DELETE | `/api/v1/graph/triples` | Delete triples |
| GET | `/api/v1/graph/triples/by-subject/{id}` | Get triples for subject |
| GET | `/api/v1/graph/triples/search?subject=&predicate=&object=` | Search triples |

### Query
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/query/search?q=` | Full-text search |
| GET | `/api/v1/query/export` | Turtle export |
| POST | `/api/v1/query/import` | Turtle import |
| GET | `/api/v1/query/stats` | Graph stats |
| POST | `/api/v1/query/raw` | Raw SQL SELECT query (read-only) |

### Command Dispatch
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/command/tree` | Command metadata for autocomplete |
| GET | `/api/v1/command/help` | Help text |
| POST | `/api/v1/command` | Execute a command |

### LLM
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/llm/chat` | Chat with LLM (multi-round tool-calling, permission gate) |
| POST | `/api/v1/llm/chat/resume` | Resume chat after HITL confirmation (with feedback support) |
| POST | `/api/v1/llm/confirm` | Execute a single destructive command after user confirmation (legacy) |
| GET | `/api/v1/llm/config` | Check LLM provider availability |
| POST | `/api/v1/llm/configure` | Save provider config to keyring |
| GET | `/api/v1/llm/profiles` | List saved LLM profiles |
| POST | `/api/v1/llm/profiles` | Create a named profile |
| POST | `/api/v1/llm/profiles/{name}/load` | Load a saved profile |
| GET | `/api/v1/llm/prompt` | View current system prompt |
| POST | `/api/v1/llm/reload-prompt` | Reload system prompt from disk (no restart needed) |

### Prompt Commands
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/prompt-commands/list` | List available prompt commands |
| POST | `/api/v1/prompt-commands/expand` | Preview expanded template |
| POST | `/api/v1/prompt-commands/execute` | Expand + send to LLM (sync JSON) |
| POST | `/api/v1/prompt-commands/execute/stream` | SSE streaming variant |
| POST | `/api/v1/prompt-commands/execute/resume` | Resume after HITL confirmation |

### Prompt Files
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/llm/prompts/list` | List all prompt files with modification status |
| GET | `/api/v1/llm/prompts/view?name=` | View a specific prompt file (current + default) |
| POST | `/api/v1/llm/prompts/reset` | Reset a prompt to default content |
| POST | `/api/v1/llm/prompts/save` | Save edited prompt content |
| GET | `/api/v1/llm/prompts/modified-count` | Count of modified prompts (for banner) |

### Triple Templates
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/triple-templates/list` | List available triple templates |
| GET | `/api/v1/triple-templates/{name}` | Get full template definition |
| POST | `/api/v1/triple-templates/expand` | Preview expanded triples |
| POST | `/api/v1/triple-templates/execute` | Expand and add all triples |
| POST | `/api/v1/triple-templates/save` | Save a generated YAML template to disk |

### SPARQL
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/query/sparql?query=` | SPARQL 1.1 query (GET) |
| POST | `/api/v1/query/sparql` | SPARQL 1.1 query (POST with `application/sparql-query`) |

### Other
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/v1/review/sessions` | Review session management |
| GET | `/api/v1/proof/proofs` | List proofs |
| POST | `/api/v1/files/upload` | Upload file attachment |
| GET/PATCH | `/api/v1/user/config` | User locale/preferences |

## Dependencies

Semantika depends on [lightercore](../lightercore) for shared infrastructure (DB, paths, exceptions, CRUD, backup, LLM, prompt_commands, permissions). Clone both repos side by side:

```bash
git clone https://github.com/Ron-RONZZ-org/semantika.git
git clone https://github.com/Ron-RONZZ-org/lightercore.git
cd semantika
uv pip install -e "../lightercore" -e ".[dev]"
```

## Development

### Running the server

The database lives at `~/.local/share/semantika/semantika.db` by default.
The first run creates tables and seeds default predicates automatically.

```bash
# Start with persistent data
uv run uvicorn semantika.server.app:create_app --factory --port 6015 --reload

# Start with an isolated temporary database
SEMANTIKA_DATA_DIR=/tmp/semantika-dev uv run uvicorn semantika.server.app:create_app --factory --port 6015 --reload
```

### CORS Configuration (Production)

By default, Semantika allows `http://localhost:6016` and `http://127.0.0.1:6016` (Vite dev ports). In production, you **must** restrict CORS to your actual frontend domain:

```bash
# Single frontend origin
SEMANTIKA_CORS_ORIGINS=https://semantika.example.com uv run uvicorn ...

# Multiple origins (comma-separated)
SEMANTIKA_CORS_ORIGINS="https://app.example.com,https://admin.example.com" uv run uvicorn ...
```

The `SEMANTIKA_CORS_ORIGINS` env var accepts a comma-separated list of origins. If unset, localhost dev ports are used.

### Custom Static Directory

Override the SPA static file directory:

```bash
SEMANTIKA_STATIC_DIR=/path/to/custom/dist uv run uvicorn ...
```

### Testing the API

```bash
# List nodes
curl http://127.0.0.1:6015/api/v1/graph/nodes

# Create a node
curl -X POST http://127.0.0.1:6015/api/v1/graph/nodes \
  -H "Content-Type: application/json" \
  -d '{"node_id":"CONCEPT","labels":{"en":"My Concept"}}'

# Execute a command
curl -X POST http://127.0.0.1:6015/api/v1/command \
  -H "Content-Type: application/json" \
  -d '{"tokens":["stats"],"flags":{}}'
```

## DB Schema

```sql
-- Nodes: entities in the knowledge graph
CREATE TABLE nodes (
    node_id         TEXT PRIMARY KEY,
    labels          TEXT NOT NULL DEFAULT '{}',    -- JSON: {"en": "Label"}
    label_text      TEXT NOT NULL DEFAULT '',
    definitions     TEXT NOT NULL DEFAULT '{}',    -- JSON: {"en": "Definition"}
    definition_text TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Predicates: semantic properties
CREATE TABLE predicates (
    predicate_id  TEXT PRIMARY KEY,
    source        TEXT NOT NULL DEFAULT 'manual',
    labels        TEXT NOT NULL DEFAULT '{}',
    descriptions  TEXT NOT NULL DEFAULT '{}',
    aliases       TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Triples: subject-predicate-object arcs (RDF-style)
CREATE TABLE triples (
    subject_id      TEXT NOT NULL REFERENCES nodes(node_id),
    predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
    object_type     TEXT NOT NULL DEFAULT 'uri',
    object_value    TEXT NOT NULL,
    object_lang     TEXT DEFAULT NULL,
    object_datatype TEXT DEFAULT NULL,
    object_node_id  TEXT GENERATED ALWAYS AS (...),
    created_at      TEXT NOT NULL,
    PRIMARY KEY (subject_id, predicate_id, object_value, object_type)
) WITHOUT ROWID;
```

## Status

**Pre-alpha — growing rapidly.** All core triple store operations (nodes, predicates, triples, review, proof, units, TTL import/export, trash, predicate trash) are implemented and tested (1300+ tests). The LLM provider (OpenAI-compatible + Ollama) supports configurable profiles with keyring-based key storage and multi-round tool-calling with permission gate. File-based prompt commands (`/` prefix), built-in multi-turn flows (``/template``, ``/text-to-triples``), context store system, user configuration (locale, ID normalisation), triple templates, SPARQL 1.1 endpoint, built-in predicate catalog (``builtins.yaml``), system prompt customisation, and **LLM co-writing (cowrite)** for form editing are operational.
