"""Graph database schema and initialization.

Ported from A-semantika's ``data/storage.py`` with Esperanto-to-English migration.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from semantika.core import SemantikaDB
from semantika.core import data_dir, ensure_dirs
from semantika.server.cowrite import COWRITE_SAMPLES_SCHEMA
from semantika.core.crud import now

logger = logging.getLogger(__name__)

_DB_FILENAME = "semantika.db"

_db_instance: SemantikaDB | None = None
_db_path: Path | None = None

# SPARQL engine singleton (injected at app startup)
_sparql_engine: Any = None  # SparqlEngine | None — type is Any to avoid import at module level


def get_db_path() -> Path:
    """Return the path to the SQLite database file."""
    global _db_path
    if _db_path is None:
        _db_path = data_dir() / _DB_FILENAME
    return _db_path


def get_db() -> SemantikaDB:
    """Return the singleton database instance, creating it if necessary."""
    global _db_instance
    if _db_instance is None:
        ensure_dirs()
        _db_instance = SemantikaDB(get_db_path())
        # WAL and foreign_keys pragmas are set by SemantikaDB._get_conn()
    return _db_instance


def close_db() -> None:
    """Close and reset the singleton database instance.

    Used before restore operations so the file can be overwritten.
    """
    global _db_instance, _db_path
    if _db_instance is not None:
        try:
            _db_instance.close()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Error closing DB: %s", exc
            )
        _db_instance = None
        _db_path = None


def get_sparql_engine() -> Any:
    """Return the SPARQL engine singleton, or ``None`` if not initialized.

    The engine is set by :func:`init_sparql_engine` during app startup.
    """
    return _sparql_engine


def init_sparql_engine(cache_dir: Path | None = None) -> Any:
    """Initialize the SPARQL engine singleton.

    Creates an :class:`~semantika.graph.sparql.engine.SparqlEngine` backed by
    an Oxigraph RocksDB store at the given path (or a default under the
    Semantika data directory).

    Args:
        cache_dir: Directory for the RocksDB store. Defaults to
            ``{data_dir}/sparql-cache/``.

    Returns:
        The engine instance, or ``None`` if the SPARQL module is unavailable.

    Call :func:`close_sparql_engine` to shut it down.
    """
    global _sparql_engine
    try:
        from semantika.graph.sparql.engine import SparqlEngine
    except ImportError:
        logger.warning("SPARQL engine not available (pyoxigraph not installed)")
        return None

    if cache_dir is None:
        cache_dir = data_dir() / "sparql-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    _sparql_engine = SparqlEngine(get_db(), cache_dir=cache_dir)

    # Bulk-sync existing triples (handles lazy init where data already exists)
    _sparql_engine.sync_all()

    # Inject the engine into any already-cached services (lazy init path)
    global _services_cache
    if _services_cache is not None:
        for svc_name in ("node", "predicate", "triple"):
            svc = _services_cache.get(svc_name)
            if svc is not None:
                svc._sparql_engine = _sparql_engine

    logger.info("SPARQL engine initialized (cache: %s)", cache_dir)
    return _sparql_engine


def close_sparql_engine() -> None:
    """Shut down the SPARQL engine singleton."""
    global _sparql_engine
    if _sparql_engine is not None:
        try:
            _sparql_engine.close()
        except Exception as exc:
            logger.warning("Error closing SPARQL engine: %s", exc)
        _sparql_engine = None
        logger.info("SPARQL engine shut down")


_services_cache: dict[str, Any] | None = None


def get_services() -> dict[str, Any]:
    """Return a dict of all service singletons (cached).

    Lazily initializes the DB and all services once.  Subsequent calls
    return the cached instances, avoiding repeated constructor overhead
    on every command dispatch.

    Call :func:`reset_services` to clear the cache (e.g. after a database
    reset or restore).
    """
    global _services_cache
    if _services_cache is not None:
        return _services_cache

    init_db()
    from semantika.graph.node_service import NodeService
    from semantika.graph.predicate_group_service import PredicateGroupService
    from semantika.graph.predicate_service import PredicateService
    from semantika.graph.proof_service import ProofService
    from semantika.graph.review_service import ReviewService
    from semantika.graph.triple_service import TripleService
    from semantika.graph.builtin_type_service import BuiltinTypeService

    db = get_db()
    engine = _sparql_engine
    triple_svc = TripleService(db)
    triple_svc._sparql_engine = engine
    node_svc = NodeService(db)
    node_svc._sparql_engine = engine
    pred_svc = PredicateService(db)
    pred_svc._sparql_engine = engine

    _services_cache = {
        "node": node_svc,
        "predicate": pred_svc,
        "predicate_group": PredicateGroupService(db),
        "triple": triple_svc,
        "review": ReviewService(db),
        "proof": ProofService(db),
        "builtin_type": BuiltinTypeService(
            db,
            NodeService(db),
            TripleService(db),
            PredicateService(db),
        ),
    }
    return _services_cache


def reset_services() -> None:
    """Clear the services cache.

    Call after a database reset or restore so that the next call to
    :func:`get_services` creates fresh service instances tied to the
    new database.
    """
    global _services_cache
    _services_cache = None


# ── Canonical IRI computation ──────────────────────────────────────────
# KNOWN_PREFIXES imported from graph.constants (single source of truth).

from semantika.graph.constants import KNOWN_PREFIXES  # noqa: E402


def compute_iri(internal_id: str, template: str | None = None) -> str:
    """Return the canonical IRI string for an internal Semantika ID.

    Resolution rules (mirrors :func:`_to_uri` in ``engine.py``):

    1. Full ``http://`` / ``https://`` URI → pass through as-is.
    2. ``prefix:local`` with known prefix (e.g. ``rdf:type``) →
       ``<known_prefix_uri>local`` (template is **ignored** for known prefixes).
    3. ``prefix:local`` with *unknown* prefix →
       ``template`` with ``$id`` replaced by the full ``prefix:local``.
    4. Bare label (no colon) → ``template`` with ``$id`` replaced by the label.

    If *template* is ``None``, the configured template for the entity kind is
    used (see :func:`get_iri_template`).  When no template is configured and
    none is supplied, a default is used.
    """
    if internal_id.startswith("http://") or internal_id.startswith("https://"):
        return internal_id
    if ":" in internal_id:
        prefix, local = internal_id.split(":", 1)
        ns = KNOWN_PREFIXES.get(prefix)
        if ns:
            return ns + local
        kind = "predicate"
    else:
        if not internal_id:
            raise ValueError("Cannot compute IRI for empty internal ID")
        kind = "node"

    tpl = template if template is not None else _get_template_for_kind(kind)
    return tpl.replace("$id", internal_id)


def _get_template_for_kind(kind: str) -> str:
    """Return the IRI template from config, falling back to built-in default.

    Imported lazily to avoid circular imports at module level.
    """
    from semantika.core.config import get_iri_template

    return get_iri_template(kind)


# ── Schema DDL ─────────────────────────────────────────────────────────

SCHEMA = {
    "nodes": """
        CREATE TABLE IF NOT EXISTS nodes (
            node_id         TEXT PRIMARY KEY,
            iri             TEXT NOT NULL DEFAULT '',
            labels          TEXT NOT NULL DEFAULT '{}',   -- JSON: {"en": "Label"}
            label_text      TEXT NOT NULL DEFAULT '',
            definitions     TEXT NOT NULL DEFAULT '{}',   -- JSON: {"en": "Definition"}
            definition_text TEXT NOT NULL DEFAULT '',
            code_content    TEXT NOT NULL DEFAULT '',      -- Inline code snippet (text only)
            code_language   TEXT NOT NULL DEFAULT '',      -- Programming language tag
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """,
    "nodes_trash": """
        CREATE TABLE IF NOT EXISTS nodes_trash (
            node_id         TEXT PRIMARY KEY,
            iri             TEXT NOT NULL DEFAULT '',
            labels          TEXT NOT NULL DEFAULT '{}',
            label_text      TEXT NOT NULL DEFAULT '',
            definitions     TEXT NOT NULL DEFAULT '{}',
            definition_text TEXT NOT NULL DEFAULT '',
            code_content    TEXT NOT NULL DEFAULT '',
            code_language   TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            deleted_at      TEXT NOT NULL
        )
    """,
    "predicates": """
        CREATE TABLE IF NOT EXISTS predicates (
            predicate_id  TEXT PRIMARY KEY,
            iri           TEXT NOT NULL DEFAULT '',
            source        TEXT NOT NULL DEFAULT 'manual',
            labels        TEXT NOT NULL DEFAULT '{}',   -- JSON: {"en": "type"}
            descriptions  TEXT NOT NULL DEFAULT '{}',   -- JSON: {"en": "Description"}
            aliases       TEXT NOT NULL DEFAULT '[]',   -- JSON array
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
    """,
    "predicates_trash": """
        CREATE TABLE IF NOT EXISTS predicates_trash (
            predicate_id  TEXT PRIMARY KEY,
            iri           TEXT NOT NULL DEFAULT '',
            source        TEXT NOT NULL DEFAULT 'manual',
            labels        TEXT NOT NULL DEFAULT '{}',
            descriptions  TEXT NOT NULL DEFAULT '{}',
            aliases       TEXT NOT NULL DEFAULT '[]',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            deleted_at    TEXT NOT NULL
        )
    """,
    "predicate_groups": """
        CREATE TABLE IF NOT EXISTS predicate_groups (
            uuid         TEXT PRIMARY KEY,
            group_name   TEXT NOT NULL UNIQUE,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        )
    """,
    "predicate_group_members": """
        CREATE TABLE IF NOT EXISTS predicate_group_members (
            uuid           TEXT PRIMARY KEY,
            group_uuid     TEXT NOT NULL REFERENCES predicate_groups(uuid),
            predicate_id   TEXT NOT NULL REFERENCES predicates(predicate_id),
            created_at     TEXT NOT NULL,
            UNIQUE(group_uuid, predicate_id)
        )
    """,
    "triples": """
        CREATE TABLE IF NOT EXISTS triples (
            subject_id      TEXT NOT NULL REFERENCES nodes(node_id),
            predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
            object_type     TEXT NOT NULL DEFAULT 'node',   -- 'node' or 'literal'
            object_value    TEXT NOT NULL,
            object_lang     TEXT DEFAULT NULL,
            object_datatype TEXT DEFAULT NULL,
            object_unit     TEXT DEFAULT NULL,
            created_at      TEXT NOT NULL,
            object_node_id  TEXT GENERATED ALWAYS AS (
                CASE WHEN object_type='node' THEN object_value ELSE NULL END
            ) STORED REFERENCES nodes(node_id),
            PRIMARY KEY (subject_id, predicate_id, object_value, object_type)
        )
    """,
}

# Indexes on the triples table
TRIPLES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_triples_pos ON triples(predicate_id, object_value, subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_triples_osp ON triples(object_value, object_type, predicate_id, subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_triples_pred_subj ON triples(predicate_id, subject_id)",
]

# Case-insensitive lookup index for node_id (used by COLLATE NOCASE queries)
NODES_NOCASE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_nodes_node_id_nocase ON nodes(node_id COLLATE NOCASE)"
)

# Review (recenzi) schema
REVIEW_SCHEMA = {
    "review_sessions": """
        CREATE TABLE IF NOT EXISTS review_sessions (
            uuid        TEXT PRIMARY KEY,
            mode        TEXT NOT NULL DEFAULT 'view',
            date_from   TEXT,
            date_to     TEXT,
            created_at  TEXT NOT NULL,
            total       INTEGER NOT NULL DEFAULT 0,
            correct     INTEGER NOT NULL DEFAULT 0,
            finished    INTEGER NOT NULL DEFAULT 0
        )
    """,
    "review_results": """
        CREATE TABLE IF NOT EXISTS review_results (
            uuid         TEXT PRIMARY KEY,
            session_uuid TEXT NOT NULL REFERENCES review_sessions(uuid),
            subject_id   TEXT NOT NULL,
            predicate_id TEXT NOT NULL,
            object_value TEXT NOT NULL,
            object_type  TEXT NOT NULL DEFAULT 'node',
            is_correct   INTEGER NOT NULL DEFAULT 0,
            response     TEXT,
            position     INTEGER NOT NULL DEFAULT 0,
            answered_at  TEXT NOT NULL DEFAULT ''
        )
    """,
}

# Proof (provo) schema
PROOF_SCHEMA = {
    "proofs": """
        CREATE TABLE IF NOT EXISTS proofs (
            uuid        TEXT PRIMARY KEY,
            subject_id  TEXT NOT NULL REFERENCES nodes(node_id),
            predicate_id TEXT NOT NULL REFERENCES predicates(predicate_id),
            object_value TEXT NOT NULL,
            object_type TEXT NOT NULL DEFAULT 'node',
            proof_type  TEXT NOT NULL DEFAULT 'observation',
            source      TEXT NOT NULL DEFAULT '',
            notes       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """,
}


def init_db() -> None:
    """Initialize the database: create tables, indexes, seed defaults."""
    db = get_db()

    # Create all tables (IF NOT EXISTS handles idempotency)
    for sql in SCHEMA.values():
        db.execute(sql)

    # Create indexes
    for idx_sql in TRIPLES_INDEXES:
        db.execute(idx_sql)
    db.execute(NODES_NOCASE_INDEX)

    # Create review/proof tables
    for sql in {**REVIEW_SCHEMA, **PROOF_SCHEMA}.values():
        db.execute(sql)

    # Create cowrite writing samples table
    for sql in COWRITE_SAMPLES_SCHEMA.values():
        db.execute(sql)

    # Create FTS tables + populate
    _ensure_nodes_fts(db)
    _ensure_predicates_fts(db)

    # Migrate existing tables
    _migrate_review_schema(db)
    _migrate_triples_schema(db)
    _migrate_iri_column(db)
    _migrate_code_columns(db)

    # Migrate legacy object_type values ('uri' -> 'node')
    _migrate_object_type_values(db)

    # Seed default predicates if empty
    _seed_default_predicates(db)


def _migrate_review_schema(db: SemantikaDB) -> None:
    """Add missing columns to existing review tables (migration)."""
    migs = {
        "review_sessions": [
            ("mode", "TEXT NOT NULL DEFAULT 'view'"),
            ("date_from", "TEXT"),
            ("date_to", "TEXT"),
            ("finished", "INTEGER NOT NULL DEFAULT 0"),
        ],
        "review_results": [
            ("response", "TEXT"),
            ("position", "INTEGER NOT NULL DEFAULT 0"),
        ],
    }
    for table, cols in migs.items():
        for col_name, col_def in cols:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass  # Column already exists


def _migrate_triples_schema(db: SemantikaDB) -> None:
    """Add missing columns to existing triples table (migration)."""

    # Migration: drop WITHOUT ROWID so that the implicit rowid is available
    # (needed by the file-attachment grouping query in files.py).
    try:
        row = db.execute_one(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='triples'"
        )
        if row and "WITHOUT ROWID" in row["sql"].upper():
            _recreate_triples_without_rowid(db)
    except Exception:
        pass  # Best effort — fresh DB will use the updated DDL

    migs = {
        "triples": [
            ("object_unit", "TEXT DEFAULT NULL"),
        ],
    }
    for table, cols in migs.items():
        for col_name, col_def in cols:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass  # Column already exists


def _recreate_triples_without_rowid(db: SemantikaDB) -> None:
    """Recreate the triples table without WITHOUT ROWID.

    SQLite does not support ``ALTER TABLE ... DROP WITHOUT ROWID``, so we
    must recreate the table to make the implicit ``rowid`` available.
    """
    db.execute("""
        CREATE TABLE IF NOT EXISTS triples_new (
            subject_id      TEXT NOT NULL REFERENCES nodes(node_id),
            predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
            object_type     TEXT NOT NULL DEFAULT 'node',
            object_value    TEXT NOT NULL,
            object_lang     TEXT DEFAULT NULL,
            object_datatype TEXT DEFAULT NULL,
            object_unit     TEXT DEFAULT NULL,
            created_at      TEXT NOT NULL,
            object_node_id  TEXT GENERATED ALWAYS AS (
                CASE WHEN object_type='node' THEN object_value ELSE NULL END
            ) STORED REFERENCES nodes(node_id),
            PRIMARY KEY (subject_id, predicate_id, object_value, object_type)
        )
    """)
    db.execute(
        "INSERT OR IGNORE INTO triples_new "
        "SELECT * FROM triples"
    )
    db.execute("DROP TABLE triples")
    db.execute("ALTER TABLE triples_new RENAME TO triples")
    # Recreate indexes
    for idx_sql in TRIPLES_INDEXES:
        db.execute(idx_sql)


def _migrate_iri_column(db: SemantikaDB) -> None:
    """Add ``iri`` column to nodes/predicates tables.

    The column stays **empty** for entities using the default IRI template.
    It is populated only for entities with an explicit ``--canonical`` override.
    """
    for table in ("nodes", "nodes_trash", "predicates", "predicates_trash"):
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN iri TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists


def _ensure_fts(
    db: SemantikaDB,
    fts_table: str,
    content_table: str,
    columns: list[str],
) -> None:
    """Create an FTS5 virtual table and populate it if empty.

    Args:
        db: Database instance.
        fts_table: Name of the FTS virtual table (e.g. ``nodes_fts``).
        content_table: Name of the content table (e.g. ``nodes``).
        columns: Column names for the FTS index. The first column should be
                 ``UNINDEXED`` (the primary key), the rest are full-text
                 indexed.
    """
    col_defs = ",\n            ".join(columns)
    db.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {fts_table} USING fts5(\n"
        f"            {col_defs},\n"
        f"            content={content_table},\n"
        f"            content_rowid=rowid,\n"
        f"            tokenize='unicode61'\n"
        "        )"
    )
    row = db.execute_one(f"SELECT COUNT(*) AS cnt FROM {fts_table}")
    if row and row["cnt"] == 0:
        col_list = ", ".join(c.split()[0] for c in columns)
        try:
            db.execute(
                f"INSERT INTO {fts_table} (rowid, {col_list})"
                f" SELECT rowid, {col_list} FROM {content_table}"
            )
        except sqlite3.DatabaseError:
            logger.warning(
                "Failed to populate %s — LIKE fallback will be used", fts_table,
                exc_info=True,
            )


def _ensure_nodes_fts(db: SemantikaDB) -> None:
    """Create the nodes FTS5 virtual table if it doesn't exist."""
    _ensure_fts(
        db,
        fts_table="nodes_fts",
        content_table="nodes",
        columns=[
            "node_id UNINDEXED",
            "label_text",
            "definition_text",
            "code_content",
        ],
    )


def _ensure_predicates_fts(db: SemantikaDB) -> None:
    """Create the predicates FTS5 virtual table if it doesn't exist."""
    _ensure_fts(
        db,
        fts_table="predicates_fts",
        content_table="predicates",
        columns=[
            "predicate_id UNINDEXED",
            "labels",
            "descriptions",
            "aliases",
        ],
    )


def _migrate_code_columns(db: SemantikaDB) -> None:
    """Add ``code_content`` and ``code_language`` columns to nodes tables."""
    for table in ("nodes", "nodes_trash"):
        for col_name, col_def in [("code_content", "TEXT NOT NULL DEFAULT ''"),
                                   ("code_language", "TEXT NOT NULL DEFAULT ''")]:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass  # Column already exists


def _migrate_object_type_values(db: SemantikaDB) -> None:
    """Migrate legacy 'uri' -> 'node' in triples, proofs, and review_results object_type values.

    Runs on every startup; idempotent after the first run.
    """
    for table in ("triples", "proofs", "review_results"):
        db.execute(f"UPDATE {table} SET object_type = 'node' WHERE object_type = 'node'")


def _seed_default_predicates(db: SemantikaDB) -> None:
    """No-op — seeding moved to ``BuiltinTypeService.ensure_builtins()``.

    Kept as a no-op to avoid breaking callers during the migration.
    All predicates (RDF/OWL/sm:/file) are now seeded by
    :meth:`~semantika.graph.builtin_type_service.BuiltinTypeService.ensure_builtins`,
    called from ``create_app()`` lifespan.
    """
    return


def _iri_is_non_template(internal_id: str) -> bool:
    """Return True if *internal_id* produces an IRI that does NOT match the
    current user template (i.e. it must be stored in the ``iri`` column)."""
    if ":" in internal_id:
        prefix, _ = internal_id.split(":", 1)
        if prefix in KNOWN_PREFIXES:
            return True  # e.g. rdf:type → fixed namespace, never matches user template
    # Everything else follows the template → leave iri column empty
    return False
