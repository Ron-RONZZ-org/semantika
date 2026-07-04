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

## Status

**Pre-alpha.** The code is being forked from the proven [A-semantika](../A-semantika) project. Backend logic exists and is well-tested (400+ tests); the web frontend is being built from scratch.
