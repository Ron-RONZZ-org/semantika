# Semantika

Semantika — knowledge graph CLI+GUI with LLM. A semantic triple store with a Svelte frontend and BYOK (Bring Your Own Key) LLM-native integration. AGPL-3.0.

## Project Family

Semantika is the **third-generation** of a knowledge-graph toolchain. Understanding its ancestry clarifies design decisions:

| Project | Role | Relationship |
|---------|------|-------------|
| **[A-semantika](../A-semantika)** | EO-first CLI ancestor | **Business-logic reference.** Forked and migrated from Esperanto to English. Core triple store services (NodeService, PredicateService, TripleService, ReviewService, ProofService, unit ontology) originate here. Refer to A-semantika when implementing graph operations, Turtle export, or review/proof mechanics. |
| **[lighterbird](../lighterbird)** | Mature sister PIM app | **UX/LLM/DB reference.** The command-bar interaction model, command tree + dispatch architecture, autocomplete engine, tab/result-panel UI, and LLM provider integration (OpenAI/Ollama with text-based command generation) are all ported from lighterbird. Refer to lighterbird when designing frontend components, command routing, LLM tool-calling, or keyring-based config management. |
| **[lightercore](../lightercore)** | Shared core library | **Infrastructure reference.** DB, paths, exceptions, CRUD, and backup come from lightercore — the canonical source shared with lighterbird. |
| **Semantika (this repo)** | Modern English successor | **Combines the best of all.** Graph business logic from A-semantika + UX/LLM patterns from lighterbird + shared infrastructure from lightercore + Svelte 5 SPA frontend. |

## Philosophy: You see only what you need

Traditional knowledge management apps drown you in sidebars, nested menus, and feature flags. Semantika does the opposite:

```
┌──────────────────────────────────────────────┐
│ ❯ !node add --label "Concept"                │  ← Always-visible command bar
├──────────────────────────────────────────────┤
│                                              │
│  Rich result area                            │  ← Shows only what you asked for
│  (node details, triple tables,               │
│   graph visualization, LLM chat, katex,      │
│   code blocks, images)                       │
│                                              │
└──────────────────────────────────────────────┘
```

- `!node add/list/view/modify/delete/merge/rename` — manage knowledge graph nodes; merge duplicates or rename IDs with full FK cascade
- `!predicate add/list/search/update/delete/rename` — manage predicates; rename IDs with cascade to triples and groups
- `!triple add/list/delete` (`PATCH` for metadata) — assert, query, and modify subject-predicate-object arcs
- `!search <query>` — full-text search across nodes, predicates, and triples (by label)
- `!trash list/restore/purge` — manage soft-deleted nodes (restore or permanently purge)
- `!export` / `!import` — export/import the graph in Turtle (.ttl) format
- `!review start [view|quiz]` — interactive triple review with two modes:
  - **view**: show SPO, confirm correct/incorrect
  - **quiz**: multiple-choice with auto-generated distractors via FTS5 similarity
  - Optional `--date-from`/`--date-to` / `--limit` filters
- `!review sessions` — list past review sessions with scores
- `!files attach <node-id> <path|url>` — attach files to nodes (auto-MIME detection)
- Just type naturally → the LLM translates your intent into commands
- As-you-type command suggestions with node/predicate completion — no memorisation needed

## Architecture

```
semantika/
├── core/          Vendored from A-core      — DB, FTS5, paths, interactive helpers
├── graph/         Forked from A-semantika   — triple store services, TTL import/export
├── server/        FastAPI backend           — REST API, command engine, LLM provider
│   └── llm/       Ported from lighterbird   — OpenAI-compatible + Ollama, command generation
└── web/           Svelte 5 SPA              — Command-bar UI (lighterbird pattern), rich results
```

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python 3.11+ / FastAPI | Lightweight, async, auto-docs |
| Frontend | Svelte 5 SPA + Vite | Minimal bundle, excellent custom component DX |
| Database | SQLite (WAL mode) | Embedded, zero-config |
| AI | OpenAI-compatible API + Ollama | BYOK: bring your own model/key; two-phase command generation |
| Credentials | System keyring (via `keyring`) | Never store API keys in DB |

## Quick Start

```bash
# Backend
# The `.[dev]` suffix installs optional dev dependencies (pytest, ruff, etc.)
uv pip install -e ".[dev]"
uv run python -m semantika

# Frontend (separate terminal)
cd web
npm install
npm run dev
```

### Port synchronization

If the backend is on a different port (e.g. 8001 is taken, or you used `--port 0` for an OS-assigned port), set `SEMANTIKA_PORT` before starting the frontend:

```bash
# Terminal 1: start backend on custom port
uv run uvicorn semantika.server.app:create_app --factory --port 8765

# Terminal 2: tell Vite proxy where the backend is
SEMANTIKA_PORT=8765 npm run dev
```

In production (built frontend served by FastAPI), port configuration is automatic — the Svelte SPA is served as static files on the same port as the API. No proxy needed.

## Testing

```bash
# Backend tests
uv run pytest tests/

# With coverage
uv run pytest tests/ --cov=semantika
```

## Development Server

For isolated development, use the `semantika-dev` CLI:

```bash
# Start with seed data
uv run semantika-dev --seed

# Start with clean temp database
uv run semantika-dev
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/graph/nodes` | GET | List nodes |
| `/api/v1/graph/nodes/search?q=` | GET | Search nodes |
| `/api/v1/graph/nodes` | POST | Create a node |
| `/api/v1/graph/nodes/{id}` | GET | Get node with triples |
| `/api/v1/graph/nodes/{id}` | PATCH | Update a node |
| `/api/v1/graph/nodes/{id}` | DELETE | Delete a node |
| `/api/v1/graph/nodes/stats` | GET | Graph statistics |
| `/api/v1/graph/predicates` | GET | List predicates |
| `/api/v1/graph/predicates/search?q=` | GET | Search predicates |
| `/api/v1/graph/predicates` | POST | Create a predicate |
| `/api/v1/graph/predicates/{id}` | PATCH | Update a predicate |
| `/api/v1/graph/predicates/{id}` | DELETE | Delete a predicate |
| `/api/v1/graph/triples` | GET | List triples |
| `/api/v1/graph/triples` | POST | Add a triple |
| `/api/v1/graph/triples` | DELETE | Delete triples |
| `/api/v1/graph/triples/by-subject/{id}` | GET | Get triples for subject |
| `/api/v1/query/search?q=` | GET | Full-text search |
| `/api/v1/query/export` | GET | Turtle export |
| `/api/v1/query/import` | POST | Turtle import |
| `/api/v1/query/stats` | GET | Graph stats |
| `/api/v1/query/sparql?query=` | GET | Raw SQL SELECT query |
| `/api/v1/command/tree` | GET | Command metadata |
| `/api/v1/command/help` | GET | Help text |
| `/api/v1/command/execute` | POST | Execute a command |
| `/api/v1/llm/chat` | POST | Chat with LLM (two-phase: command generation → execution → summarization) |
| `/api/v1/llm/config` | GET | Check LLM provider availability |
| `/api/v1/llm/configure` | POST | Save provider config to keyring |
| `/api/v1/llm/profiles` | GET | List saved LLM profiles |
| `/api/v1/review/sessions` | GET/POST | Review session management |
| `/api/v1/proof/proofs` | GET/POST | Proof management |

## Dependencies

Semantika depends on [lightercore](../lightercore) for shared infrastructure (DB, paths, exceptions, CRUD, backup). Clone both repos side by side:

```bash
git clone https://github.com/Ron-RONZZ-org/semantika.git
git clone https://github.com/Ron-RONZZ-org/lightercore.git
cd semantika
uv pip install -e "../lightercore" -e ".[dev]"
```

## Development

### Running the server

```bash
# Start with clean database
SEMANTIKA_DATA_DIR=/tmp/semantika-dev uv run uvicorn semantika.server.app:create_app --factory --port 8001

### Testing API

```bash
# List nodes
curl http://localhost:8001/api/v1/graph/nodes

# Create a node
curl -X POST http://localhost:8001/api/v1/graph/nodes \
  -H "Content-Type: application/json" \
  -d '{"node_id":"CONCEPT","labels":{"en":"My Concept"}}'

# Add a triple
curl -X POST http://localhost:8001/api/v1/graph/triples \
  -H "Content-Type: application/json" \
  -d '{"subject_id":"CONCEPT","predicate_id":"rdf:type","object_value":"THING","object_type":"uri"}'

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

**Pre-alpha — core complete.** All core triple store operations (nodes, predicates, triples, review, proof, units, TTL import/export) are implemented and tested. The LLM provider (OpenAI-compatible + Ollama) supports configurable profiles with keyring-based key storage and two-phase command generation (natural language → structured command → execution → summarization). 76 pytest tests pass (24 unit + 52 E2E API).
