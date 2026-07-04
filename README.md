# Semantika

Semantika — knowledge graph CLI+GUI with LLM. A semantic triple store with a Svelte frontend and BYOK (Bring Your Own Key) LLM-native integration. AGPL-3.0.

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

- `!node add/list/view/modify/delete` — manage knowledge graph nodes
- `!predicate add/list/view` — manage predicates (semantic properties)
- `!triple add/delete/search` — assert and query subject-predicate-object arcs
- `!search <query>` — full-text search across labels and definitions
- `!export` — export the graph in Turtle (.ttl) format
- `!review` — spaced-repetition flashcard review of triples
- `!ask "What do I know about X?"` — query naturally via built-in LLM
- Just type naturally → ask the LLM to add triples, find connections, or visualize relationships
- As-you-type command suggestions with node/predicate completion — no memorisation needed

## Architecture

```
semantika/
├── core/          Vendored from A-core  — DB, FTS5, paths, interactive helpers
├── graph/         Forked from A-semantika — triple store services
├── server/        FastAPI backend       — REST API, command engine, LLM integration
└── web/           Svelte 5 SPA          — Command-bar UI, rich result rendering
```

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python 3.11+ / FastAPI | Lightweight, async, auto-docs |
| Frontend | Svelte 5 SPA + Vite | Minimal bundle, excellent custom component DX |
| Database | SQLite (WAL mode) | Embedded, zero-config |
| AI | OpenAI-compatible API + Ollama | BYOK: bring your own model/key |
| Credentials | System keyring | Never store API keys in DB |

## Quick Start

```bash
# Backend
uv pip install -e ".[dev]"
uv run python -m semantika

# Frontend (separate terminal)
cd web
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies API calls to the Python backend on port 8000.

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
| `/api/v1/graph/triples` | GET | List triples |
| `/api/v1/graph/triples` | POST | Add a triple |
| `/api/v1/graph/triples` | DELETE | Delete triples |
| `/api/v1/graph/triples/by-subject/{id}` | GET | Get triples for subject |
| `/api/v1/query/search?q=` | GET | Full-text search |
| `/api/v1/query/export` | GET | Turtle export |
| `/api/v1/query/stats` | GET | Graph stats |
| `/api/v1/query/sparql?query=` | GET | Raw SQL SELECT query |
| `/api/v1/command/tree` | GET | Command metadata |
| `/api/v1/command/help` | GET | Help text |
| `/api/v1/command/execute` | POST | Execute a command |
| `/api/v1/llm/chat` | POST | Chat with LLM |
| `/api/v1/review/sessions` | GET/POST | Review session management |
| `/api/v1/proof/proofs` | GET/POST | Proof management |

## Development

### Running the server

```bash
# Start with clean database
SEMANTIKA_DATA_DIR=/tmp/semantika-dev uv run uvicorn semantika.server.app:create_app --factory --port 8000
```

### Testing API

```bash
# List nodes
curl http://localhost:8000/api/v1/graph/nodes

# Create a node
curl -X POST http://localhost:8000/api/v1/graph/nodes \
  -H "Content-Type: application/json" \
  -d '{"node_id":"CONCEPT","labels":{"en":"My Concept"}}'

# Add a triple
curl -X POST http://localhost:8000/api/v1/graph/triples \
  -H "Content-Type: application/json" \
  -d '{"subject_id":"CONCEPT","predicate_id":"rdf:type","object_value":"THING","object_type":"uri"}'

# Execute a command
curl -X POST http://localhost:8000/api/v1/command/execute \
  -H "Content-Type: application/json" \
  -d '{"command":"stats"}'
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

**Pre-alpha — draft implementation complete.** The core triple store services (NodeService, PredicateService, TripleService, ReviewService, ProofService) have been ported from [A-semantika](../A-semantika) with Esperanto-to-English migration. The FastAPI server exposes all operations via REST API. The Svelte frontend provides a command-bar UI with vis-network graph visualization. 19 pytest tests pass.

Next steps:
- Port remaining CLI-specific features (batch operations, advanced filtering)
- Implement full LLM provider integration (currently keyword-based stub)
- Add more Svelte form components for interactive node/triple creation
- Port the unit/dimension system from A-semantika
