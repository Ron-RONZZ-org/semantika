"""Graph database schema and initialization.

Ported from A-semantika's ``data/storage.py`` with Esperanto-to-English migration.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from semantika.core import SemantikaDB, data_dir, ensure_dirs
from semantika.core.crud import now

logger = logging.getLogger(__name__)

_DB_FILENAME = "semantika.db"

_db_instance: SemantikaDB | None = None
_db_path: Path | None = None


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


def get_services() -> dict[str, Any]:
    """Return a dict of all service singletons.

    Lazily initializes the DB and all services.
    """
    init_db()
    from semantika.graph.node_service import NodeService
    from semantika.graph.predicate_group_service import PredicateGroupService
    from semantika.graph.predicate_service import PredicateService
    from semantika.graph.proof_service import ProofService
    from semantika.graph.review_service import ReviewService
    from semantika.graph.triple_service import TripleService

    db = get_db()
    return {
        "node": NodeService(db),
        "predicate": PredicateService(db),
        "predicate_group": PredicateGroupService(db),
        "triple": TripleService(db),
        "review": ReviewService(db),
        "proof": ProofService(db),
    }


# ── Schema DDL ─────────────────────────────────────────────────────────

SCHEMA = {
    "nodes": """
        CREATE TABLE IF NOT EXISTS nodes (
            node_id       TEXT PRIMARY KEY,
            labels        TEXT NOT NULL DEFAULT '{}',   -- JSON: {"en": "Label"}
            label_text    TEXT NOT NULL DEFAULT '',
            definitions   TEXT NOT NULL DEFAULT '{}',   -- JSON: {"en": "Definition"}
            definition_text TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
    """,
    "nodes_trash": """
        CREATE TABLE IF NOT EXISTS nodes_trash (
            node_id       TEXT PRIMARY KEY,
            labels        TEXT NOT NULL DEFAULT '{}',
            label_text    TEXT NOT NULL DEFAULT '',
            definitions   TEXT NOT NULL DEFAULT '{}',
            definition_text TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            deleted_at    TEXT NOT NULL
        )
    """,
    "predicates": """
        CREATE TABLE IF NOT EXISTS predicates (
            predicate_id  TEXT PRIMARY KEY,
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
            object_type     TEXT NOT NULL DEFAULT 'uri',   -- 'uri' or 'literal'
            object_value    TEXT NOT NULL,
            object_lang     TEXT DEFAULT NULL,
            object_datatype TEXT DEFAULT NULL,
            object_unit     TEXT DEFAULT NULL,
            created_at      TEXT NOT NULL,
            object_node_id  TEXT GENERATED ALWAYS AS (
                CASE WHEN object_type='uri' THEN object_value ELSE NULL END
            ) STORED REFERENCES nodes(node_id),
            PRIMARY KEY (subject_id, predicate_id, object_value, object_type)
        ) WITHOUT ROWID
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
            object_type  TEXT NOT NULL DEFAULT 'uri',
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
            object_type TEXT NOT NULL DEFAULT 'uri',
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

    # Create FTS tables + populate
    _ensure_nodes_fts(db)
    _ensure_predicates_fts(db)

    # Migrate existing tables
    _migrate_review_schema(db)
    _migrate_triples_schema(db)

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


def _seed_default_predicates(db: SemantikaDB) -> None:
    """Seed default RDF/OWL predicates if the predicates table is empty."""
    count = db.execute_one("SELECT COUNT(*) AS cnt FROM predicates")
    if count and count["cnt"] > 0:
        return

    defaults = [
        ("rdf:type", "rdf", {"en": "type", "eo": "tipo"}, {"en": "Is a type of", "eo": "Estas tipo de"}),
        ("rdfs:subClassOf", "rdfs", {"en": "subclass of", "eo": "subklaso de"}, {"en": "Is a subclass of", "eo": "Estas subklaso de"}),
        ("rdfs:label", "rdfs", {"en": "label", "eo": "etikedo"}, {"en": "Label for an entity", "eo": "Etikedo por ento"}),
        ("owl:sameAs", "owl", {"en": "same as", "eo": "sama kiel"}, {"en": "Same entity as", "eo": "Sama ento kiel"}),
        ("owl:disjointWith", "owl", {"en": "disjoint from", "eo": "malapoga al"}, {"en": "Disjoint from", "eo": "Malapoga al"}),
        ("owl:inverseOf", "owl", {"en": "inverse of", "eo": "inverso de"}, {"en": "Inverse property of", "eo": "Inversa eco de"}),
        ("rdfs:seeAlso", "rdfs", {"en": "see also", "eo": "vidu ankau"}, {"en": "Related resource", "eo": "Rilata rimedo"}),
        # File attachment predicates
        (":hasFilePath", "manual", {"en": "file path", "eo": "dosiero-loko"}, {"en": "Path to attached file", "eo": "Loko de alkroĉita dosiero"}),
        (":hasFileMime", "manual", {"en": "MIME type", "eo": "MIME-tipo"}, {"en": "MIME type of attached file", "eo": "MIME-tipo de alkroĉita dosiero"}),
        (":hasFileSize", "manual", {"en": "file size", "eo": "grandeco"}, {"en": "File size in bytes", "eo": "Dosiergrandeco en bajtoj"}),
        (":hasFileSource", "manual", {"en": "file source", "eo": "fontindiko"}, {"en": "Original source path/URL", "eo": "Origina fonta vojo/URL"}),
    ]

    ts = now()
    for pred_id, source, labels, descriptions in defaults:
        db.execute(
            "INSERT INTO predicates (predicate_id, source, labels, descriptions, aliases, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, '[]', ?, ?)",
            (pred_id, source, json.dumps(labels), json.dumps(descriptions), ts, ts),
        )
