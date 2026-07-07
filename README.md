# Semantika

Semantika — knowledge graph CLI+GUI with LLM. A semantic triple store with a Svelte frontend and BYOK (Bring Your Own Key) LLM-native integration. AGPL-3.0.

## Project Family

Semantika is the **third-generation** of a knowledge-graph toolchain. Understanding its ancestry clarifies design decisions:

| Project | Role | Relationship |
|---------|------|-------------|
| **[A-semantika](../A-semantika)** | EO-first CLI ancestor | **Business-logic reference.** Forked and migrated from Esperanto to English. Core triple store services (NodeService, PredicateService, TripleService, ReviewService, ProofService, unit ontology) originate here. Refer to A-semantika when implementing graph operations, Turtle export, or review/proof mechanics. |
| **[lighterbird](../lighterbird)** | Mature sister PIM app | **UX/LLM/DB reference.** The command-bar interaction model, command tree + dispatch architecture, autocomplete engine, tab/result-panel UI, LLM provider integration (OpenAI/Ollama with text-based command generation), and prompt commands (`/*` prefix) are all ported from lighterbird. Refer to lighterbird when designing frontend components, command routing, LLM tool-calling, or keyring-based config management. |
| **[lightercore](../lightercore)** | Shared core library | **Infrastructure reference.** DB, paths, exceptions, CRUD, backup, permissions, prompt_commands, LLM config, profile management come from lightercore — the canonical source shared with lighterbird. |
| **Semantika (this repo)** | Modern English successor | **Combines the best of all.** Graph business logic from A-semantika + UX/LLM patterns from lighterbird + shared infrastructure from lightercore + Svelte 5 SPA frontend. |

## Interaction Model

Semantika uses a **centralized command box** with three input modes:

```
┌──────────────────────────────────────────────────────────┐
│ ❯ !node add --label "Concept"            ← ! built-in   │
│ ❯ /*weekly 7 productivity               ← /* prompt     │
│ ❯ What do I know about X?                ← natural text  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Rich result area                                        │
│  (node details, triple tables, graph viz, LLM chat,     │
│   katex, code blocks, images, forms)                    │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

- `!command` — built-in graph operations
- `/*name [args...]` — user-defined prompt commands (see below)
- Natural text — free-form LLM chat

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

### Unit Ontology
- `!unit list/view/resolve/decompose/add` — unit ontology management

### LLM & AI
- `!llm show/new/set/clear` — LLM provider configuration
- `!llm profile list/show/load/delete` — profile management
- `!ask <question>` — ask the LLM about the graph
- Just type naturally → the LLM translates your intent into commands
- **Permission gate**: Write/destructive commands from LLM require user confirmation
- As-you-type command suggestions with node/predicate/predicate-group completion — no memorisation needed

### Prompt Commands (`/*` prefix)
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
/*weekly 7 productivity
```

### Backup & Recovery
- `!backup now/list/restore/prune/config` — database backup with multi-strategy support
- `!backup config list/add/modify/delete/test` — backup strategy management
- `!backup export/import` — portable data export/import
- `!reset [--no-backup]` — reset to fresh state

### User Configuration
- `!user config` — show current config
- `!user config --locale CODE` — set locale (e.g. `en`, `fr`, `de`, `eo`)
- Persistent locale badge in the GUI header

## Architecture

```
semantika/
├── core/        Re-exports from lightercore  — DB, paths, exceptions, CRUD, backup, FTS
├── graph/       Forked from A-semantika      — triple store services, TTL import/export
├── server/      FastAPI backend              — REST API, command engine, LLM provider,
│   └── llm/     Ported from lighterbird      — user config, prompt commands
└── web/         Svelte 5 SPA                 — Command-bar UI (lighterbird pattern),
                                               rich results, /* prompt commands
```

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python 3.11+ / FastAPI | Lightweight, async, auto-docs |
| Frontend | Svelte 5 SPA + Vite | Minimal bundle, excellent custom component DX |
| Database | SQLite (WAL mode) | Embedded, zero-config |
| AI | OpenAI-compatible API + Ollama | BYOK: bring your own model/key; three-phase command generation (parse → execute → summarise) with permission gate |
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
uv run uvicorn semantika.server.app:create_app --factory --port 8001 --reload
```

### Port synchronization

If the backend is on a different port (e.g. 8001 is taken, or you used `--port 0` for an OS-assigned port), set `SEMANTIKA_PORT` before starting the frontend:

```bash
# Terminal 1: start backend on custom port
SEMANTIKA_DATA_DIR=/tmp/semantika-dev uv run uvicorn \
  semantika.server.app:create_app --factory --port 8765 --reload

# Terminal 2: tell Vite proxy where the backend is
SEMANTIKA_PORT=8765 npm run dev
```

In production (built frontend served by FastAPI), port configuration is automatic — the Svelte SPA is served as static files on the same port as the API. No proxy needed.

## Testing

```bash
# Backend tests (817 tests)
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
| POST | `/api/v1/llm/chat` | Chat with LLM (two-phase: command generation → execution → summarisation) |
| POST | `/api/v1/llm/confirm` | Execute a destructive command after user confirmation |
| GET | `/api/v1/llm/config` | Check LLM provider availability |
| POST | `/api/v1/llm/configure` | Save provider config to keyring |
| GET | `/api/v1/llm/profiles` | List saved LLM profiles |
| POST | `/api/v1/llm/profiles` | Create a named profile |
| POST | `/api/v1/llm/profiles/{name}/load` | Load a saved profile |

### Prompt Commands
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/prompt-commands/list` | List available prompt commands |
| POST | `/api/v1/prompt-commands/expand` | Preview expanded template |
| POST | `/api/v1/prompt-commands/execute` | Expand + send to LLM (sync JSON) |
| POST | `/api/v1/prompt-commands/execute/stream` | SSE streaming variant |

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
uv run uvicorn semantika.server.app:create_app --factory --port 8001 --reload

# Start with an isolated temporary database
SEMANTIKA_DATA_DIR=/tmp/semantika-dev uv run uvicorn semantika.server.app:create_app --factory --port 8001 --reload
```

### CORS Configuration (Production)

By default, Semantika allows `http://localhost:5173` and `http://127.0.0.1:5173` (Vite dev ports). In production, you **must** restrict CORS to your actual frontend domain:

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
curl http://localhost:8001/api/v1/graph/nodes

# Create a node
curl -X POST http://localhost:8001/api/v1/graph/nodes \
  -H "Content-Type: application/json" \
  -d '{"node_id":"CONCEPT","labels":{"en":"My Concept"}}'

# Execute a command
curl -X POST http://localhost:8001/api/v1/command \
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

**Pre-alpha — core complete.** All core triple store operations (nodes, predicates, triples, review, proof, units, TTL import/export, trash, predicate trash) are implemented and tested. The LLM provider (OpenAI-compatible + Ollama) supports configurable profiles with keyring-based key storage and two-phase command generation with permission gate. File-based prompt commands (`/*` prefix) and user configuration (locale) are operational. **817 pytest tests pass.**
