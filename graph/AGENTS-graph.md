# AGENTS-graph.md — Graph Module Agent Instructions

## Summary
Triple store services: NodeService, PredicateService, PredicateGroupService, TripleService, RecenziService, ProvoService. Ported from A-semantika with Esperanto → English migration.

## Purpose and Expected Behavior
- **Nodes**: entities in the knowledge graph — `node_add`, `node_modify`, `node_delete`, `node_search`
- **Predicates**: semantic properties — `predicate_add`, `predicate_search`, predicate groups
- **Triples**: subject-predicate-object arcs — `triple_add`, `triple_delete`, `triple_search`, Turtle export
- **Recenzi**: spaced-repetition review of triples (flashcard mode)
- **Provo**: RDF reification proofs for triple metadata

## Constraints and Invariants
- All tables use English column names (migrated from A-semantika's Esperanto)
- SQLite with FTS5 for full-text search
- WAL mode for concurrent reads
- Each service file must stay under 500 lines

## Input/Output Expectations
- Service methods return `dict` or `list[dict]` for JSON serialization
- All public methods have type hints
- Errors raise specific exception types (never bare `Exception`)

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
| `difin_text` | `definition_text` |
| `label_text` | (kept) |
| `object_node_uuid` | `object_node_id` |
| `node_id` | (kept) |
| `predicate_id` | (kept) |

- Triple store schema uses compound primary key (subject_id, predicate_id, object_value, object_type) like RDF
- FTS5 on node `label_text` + `definition_text` for full-text search
- The nodes table uses `node_id TEXT PRIMARY KEY` (not UUID) for human-readable IDs
- When porting more files from A-semantika, preserve the business logic — only the naming changes
- The `_trash_table` for NodeService is `nodes_trash` with pk_column=`node_id`
- CRUD operations with FK constraints (triples referencing nodes) require cascade deletion or `PRAGMA defer_foreign_keys`
