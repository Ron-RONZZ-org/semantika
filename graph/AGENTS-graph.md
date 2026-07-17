# AGENTS-graph.md — Graph Module Agent Instructions

## Summary
Triple store services: NodeService, PredicateService, PredicateGroupService, TripleService, ReviewService, ProofService, UnitService. Ported from A-semantika with Esperanto → English migration.

## Purpose and Expected Behavior
- **Nodes**: entities in the knowledge graph — `node_add`, `node_modify`, `node_delete`, `node_search`, `node_merge`, `node_rename`
- **Predicates**: semantic properties — `predicate_add`, `predicate_search`, predicate groups with member add/remove
- **Triples**: subject-predicate-object arcs — `triple_add` (with full literal type support), `triple_delete`, `triple_modify`, `triple_search`, Turtle export/import
- **Review**: spaced-repetition review of triples (view/quiz modes)
- **Proof**: RDF reification proofs for triple metadata
- **Units**: unit ontology — resolve, decompose, add, list

## Constraints and Invariants
- All tables use English column names (migrated from A-semantika's Esperanto)
- SQLite with FTS5 for full-text search
- WAL mode for concurrent reads
- Each service file must stay under 500 lines
- Nodes table uses `node_id TEXT PRIMARY KEY` (not UUID) for human-readable IDs
- Nodes table has optional `code_content TEXT` and `code_language TEXT` columns for inline source code storage (FTS5-indexed alongside label_text/definition_text)
- Triple store schema uses compound primary key (subject_id, predicate_id, object_value, object_type) like RDF

## Input/Output Expectations
- Service methods return `dict` or `list[dict]` for JSON serialization
- All public methods have type hints
- Errors raise specific exception types (never bare `Exception`)

## Source Files

| File | Purpose |
|------|---------|
| `node_service.py` | Node CRUD, search, list |
| `node_helpers.py` | Node label/definition parsing, language extraction |
| `node_merge_mixin.py` | Node merge with FK cascade, property merging |
| `node_fts.py` | Full-text search index for nodes |
| `predicate_service.py` | Predicate CRUD, search (incl. Wikidata autofetch) |
| `predicate_group_service.py` | Predicate group CRUD + member management |
| `triple_service.py` | Triple CRUD with typed literal support |
| `triple_turtle.py` | Turtle (.ttl) export and import via rdflib |
| `review_service.py` | Review session management, quiz generation |
| `proof_service.py` | Proof CRUD (RDF reification) |
| `unit_service.py` / `unit_builder.py` / `unit_decomposition.py` | Unit ontology management |
| `builtins.yaml` / `units.yaml` | Declarative seed data (predicates, type nodes, unit ontology) — editable by non-coders |
| `builtin_loader.py` / `_required_predicates.py` | YAML loader with caching + Python fallback for required predicates |
| `builtin_type_service.py` | Built-in type nodes and predicates — lazy seeding from YAML |
| `unit_parser.py` / `unit_errors.py` | Unit parser, errors |
| `db.py` | Graph DB init, schema DDL, `get_services()` factory |
| `constants.py` | **Single source of truth** for ``KNOWN_PREFIXES`` (imported by ``db.py``, ``sparql/engine.py``, ``triple_turtle.py``), ``CORE_SM_PREDICATES`` (lazy proxy from YAML), FTS5 keywords, and heuristic helpers |
| `file_helpers.py` | File attachment helpers |
| `helpers.py` | General utility helpers |
| `services/__init__.py` | Service registry |

## Documentation Reference
- Upstream source: `../A-semantika/src/A_semantika/`

## Domain-Specific Rules for Agents
- **Esperanto → English mapping** (applied in this port):

| EO (A-semantika) | EN (Semantika) |
|---|---|
| `nodo` | `node` |
| `predikato` | `predicate` |
| `rubujo` | `trash` |
| `etikedoj` | `labels` |
| `difinoj` | `definitions` |
| `kreita_je` | `created_at` |
| `modifita_je` | `updated_at` |
| `forigita_je` | `deleted_at` |
| `aldoni` | `add` |
| `forigi` | `delete` |
| `modifi` | `modify` |
| `vidi` | `view` |
| `serci` | `search` |
| `kunfandi` | `merge` |
| `recenzi` | `review` |
| `provo` | `proof` |
| `subject_uuid` | `subject_id` |
| `object_node_uuid` | `object_node_id` |

- **SPARQL engine** (`graph/sparql/engine.py`): Oxigraph RocksDB cache for standard SPARQL 1.1 queries.
  - Only bare ID-triples stored in the cache (no labels/descriptions) — enrichment happens via SQLite lookups on query.
  - Incremental sync: ``TripleService.add()`` / ``.remove()`` / ``.update_metadata()`` fire sync hooks to keep the cache in sync.
  - Cascade deletes from ``NodeService.delete()`` and ``PredicateService.delete()`` also fire sync hooks.
  - Failed sync operations are queued in a ``SyncBacklog`` with exponential backoff and logged as ERROR after 5 retries.
- FTS5 on node `label_text` + `definition_text` for full-text search
- The `_trash_table` for NodeService is `nodes_trash` with pk_column=`node_id`
- The `_trash_table` for PredicateService is `predicates_trash` with pk_column=`predicate_id`
- CRUD operations with FK constraints (triples referencing nodes) require cascade deletion or `PRAGMA defer_foreign_keys`
- When porting more files from A-semantika, preserve the business logic — only the naming changes
