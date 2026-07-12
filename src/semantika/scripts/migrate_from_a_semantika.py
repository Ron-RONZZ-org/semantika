#!/usr/bin/env python3
"""Migrate data from an A-semantika user DB to the semantika schema.

Column mapping (Esperanto → English):
  Nodes:            etikedoj→labels, difinoj→definitions,
                    difin_text→definition_text, kreita_je→created_at,
                    modifita_je→updated_at
  Predicates:       etikedoj→labels, priskriboj→descriptions,
                    kreita_je→created_at, modifita_je→updated_at
  Triples:          subject_uuid→subject_id, kreita_je→created_at
  Groups:           kreita_je→created_at, modifita_je→updated_at
  GroupMembers:     kreita_je→created_at
  Trash:            + forigita_je→deleted_at
  ReviewSessions:   modo→mode, dato_de→date_from, dato_gis→date_to,
                    totalo→total, korekta→correct, finita→finished,
                    kreita_je→created_at
  ReviewResults:    sesio_uuid→session_uuid, subject_uuid→subject_id,
                    korekta→is_correct, respondo→response, pozicio→position,
                    kreita_je→answered_at

Usage:
  uv run python src/semantika/scripts/migrate_from_a_semantika.py \\
      <source_db_path> <target_db_path>

Example:
  uv run python src/semantika/scripts/migrate_from_a_semantika.py \\
      ~/.local/share/A/A-semantika/semantika.db \\
      ~/kodo/lighter-config/semantika/data/semantika.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


# ── Table mapping: (source_table, target_table, column_map, pk_column) ──

TABLES: list[tuple[str, str, dict[str, str], str | None]] = [
    # Main tables
    ("nodes", "nodes", {
        "node_id": "node_id",
        "etikedoj": "labels",
        "label_text": "label_text",
        "difinoj": "definitions",
        "difin_text": "definition_text",
        "kreita_je": "created_at",
        "modifita_je": "updated_at",
    }, "node_id"),
    ("predicates", "predicates", {
        "predicate_id": "predicate_id",
        "source": "source",
        "etikedoj": "labels",
        "priskriboj": "descriptions",
        "aliases": "aliases",
        "kreita_je": "created_at",
        "modifita_je": "updated_at",
    }, "predicate_id"),
    ("triples", "triples", {
        "subject_uuid": "subject_id",
        "predicate_id": "predicate_id",
        "object_type": "object_type",
        "object_value": "object_value",
        "object_lang": "object_lang",
        "object_datatype": "object_datatype",
        "object_unit": "object_unit",
        "kreita_je": "created_at",
    }, None),  # composite PK
    ("predicate_groups", "predicate_groups", {
        "uuid": "uuid",
        "group_name": "group_name",
        "kreita_je": "created_at",
        "modifita_je": "updated_at",
    }, "uuid"),
    ("predicate_group_members", "predicate_group_members", {
        "uuid": "uuid",
        "group_uuid": "group_uuid",
        "predicate_id": "predicate_id",
        "kreita_je": "created_at",
    }, "uuid"),
    # Trash tables
    ("nodes_rubujo", "nodes_trash", {
        "node_id": "node_id",
        "etikedoj": "labels",
        "label_text": "label_text",
        "difinoj": "definitions",
        "difin_text": "definition_text",
        "kreita_je": "created_at",
        "modifita_je": "updated_at",
        "forigita_je": "deleted_at",
    }, "node_id"),
    ("predicates_rubujo", "predicates_trash", {
        "predicate_id": "predicate_id",
        "source": "source",
        "etikedoj": "labels",
        "priskriboj": "descriptions",
        "aliases": "aliases",
        "kreita_je": "created_at",
        "modifita_je": "updated_at",
        "forigita_je": "deleted_at",
    }, "predicate_id"),
    ("predicate_groups_rubujo", "predicate_groups_trash", {
        "uuid": "uuid",
        "group_name": "group_name",
        "kreita_je": "created_at",
        "modifita_je": "updated_at",
        "forigita_je": "deleted_at",
    }, "uuid"),
    # Review sessions
    ("recenzo_sesio", "review_sessions", {
        "uuid": "uuid",
        "modo": "mode",
        "dato_de": "date_from",
        "dato_gis": "date_to",
        "totalo": "total",
        "korekta": "correct",
        "finita": "finished",
        "kreita_je": "created_at",
    }, "uuid"),
    # Review results
    ("recenzo_rezulto", "review_results", {
        "uuid": "uuid",
        "sesio_uuid": "session_uuid",
        "subject_uuid": "subject_id",
        "predicate_id": "predicate_id",
        "object_value": "object_value",
        "object_type": "object_type",
        "korekta": "is_correct",
        "respondo": "response",
        "pozicio": "position",
        "kreita_je": "answered_at",
    }, "uuid"),
]


def copy_table(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    src_table: str,
    dst_table: str,
    col_map: dict[str, str],
    pk_column: str | None,
) -> int:
    """Copy rows from *src_table* to *dst_table* with column renaming.

    Returns the number of rows copied.
    """
    src_cols = list(col_map.keys())
    dst_cols = list(col_map.values())

    src_exists = src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (src_table,),
    ).fetchone()
    if not src_exists:
        print(f"  ⏭  Source table '{src_table}' does not exist, skipping")
        return 0

    count = src.execute(f"SELECT COUNT(*) FROM [{src_table}]").fetchone()[0]
    if count == 0:
        print(f"  ⏭  '{src_table}' is empty, skipping")
        return 0

    src_cols_esc = ", ".join(f"[{c}]" for c in src_cols)
    dst_cols_esc = ", ".join(f"[{c}]" for c in dst_cols)
    placeholders = ", ".join("?" for _ in src_cols)

    select_sql = f"SELECT {src_cols_esc} FROM [{src_table}]"
    insert_sql = (
        f"INSERT INTO [{dst_table}] ({dst_cols_esc}) VALUES ({placeholders})"
    )

    src_rows = src.execute(select_sql).fetchall()

    copied = 0
    skipped = 0
    for row in src_rows:
        try:
            dst.execute(insert_sql, row)
            copied += 1
        except sqlite3.IntegrityError as exc:
            pk_val = row[0] if pk_column else "(composite)"
            print(f"  ⚠  Skipping duplicate in '{dst_table}' pk={pk_val}: {exc}")
            skipped += 1

    if skipped:
        print(f"  ✅ {copied} copied, {skipped} skipped from '{src_table}' → '{dst_table}'")
    else:
        print(f"  ✅ {copied} rows from '{src_table}' → '{dst_table}'")
    dst.commit()
    return copied


def _create_schema(db: sqlite3.Connection) -> None:
    """Create all target tables from the semantika schema DDL."""
    db.execute("""CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY, labels TEXT NOT NULL DEFAULT '{}',
            label_text TEXT NOT NULL DEFAULT '', definitions TEXT NOT NULL DEFAULT '{}',
            definition_text TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS nodes_trash (
            node_id TEXT PRIMARY KEY, labels TEXT NOT NULL DEFAULT '{}',
            label_text TEXT NOT NULL DEFAULT '', definitions TEXT NOT NULL DEFAULT '{}',
            definition_text TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, deleted_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS predicates (
            predicate_id TEXT PRIMARY KEY, source TEXT NOT NULL DEFAULT 'manual',
            labels TEXT NOT NULL DEFAULT '{}', descriptions TEXT NOT NULL DEFAULT '{}',
            aliases TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS predicates_trash (
            predicate_id TEXT PRIMARY KEY, source TEXT NOT NULL DEFAULT 'manual',
            labels TEXT NOT NULL DEFAULT '{}', descriptions TEXT NOT NULL DEFAULT '{}',
            aliases TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, deleted_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS predicate_groups (
            uuid TEXT PRIMARY KEY, group_name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS predicate_groups_trash (
            uuid TEXT PRIMARY KEY, group_name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            deleted_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS predicate_group_members (
            uuid TEXT PRIMARY KEY, group_uuid TEXT NOT NULL
            REFERENCES predicate_groups(uuid), predicate_id TEXT NOT NULL
            REFERENCES predicates(predicate_id), created_at TEXT NOT NULL,
            UNIQUE(group_uuid, predicate_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS triples (
            subject_id TEXT NOT NULL REFERENCES nodes(node_id),
            predicate_id TEXT NOT NULL REFERENCES predicates(predicate_id),
            object_type TEXT NOT NULL DEFAULT 'uri', object_value TEXT NOT NULL,
            object_lang TEXT DEFAULT NULL, object_datatype TEXT DEFAULT NULL,
            object_unit TEXT DEFAULT NULL, created_at TEXT NOT NULL,
            object_node_id TEXT GENERATED ALWAYS AS (
                CASE WHEN object_type='uri' THEN object_value ELSE NULL END
            ) STORED REFERENCES nodes(node_id),
            PRIMARY KEY (subject_id, predicate_id, object_value, object_type)
        ) WITHOUT ROWID""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_triples_pos ON triples(predicate_id, object_value, subject_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_triples_osp ON triples(object_value, object_type, predicate_id, subject_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_triples_pred_subj ON triples(predicate_id, subject_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_node_id_nocase ON nodes(node_id COLLATE NOCASE)")
    db.execute("""CREATE TABLE IF NOT EXISTS review_sessions (
            uuid TEXT PRIMARY KEY, mode TEXT NOT NULL DEFAULT 'view',
            date_from TEXT, date_to TEXT, created_at TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0, correct INTEGER NOT NULL DEFAULT 0,
            finished INTEGER NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE IF NOT EXISTS review_results (
            uuid TEXT PRIMARY KEY, session_uuid TEXT NOT NULL
            REFERENCES review_sessions(uuid), subject_id TEXT NOT NULL,
            predicate_id TEXT NOT NULL, object_value TEXT NOT NULL,
            object_type TEXT NOT NULL DEFAULT 'uri', is_correct INTEGER NOT NULL DEFAULT 0,
            response TEXT, position INTEGER NOT NULL DEFAULT 0,
            answered_at TEXT NOT NULL DEFAULT '')""")
    db.execute("""CREATE TABLE IF NOT EXISTS proofs (
            uuid TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES nodes(node_id),
            predicate_id TEXT NOT NULL REFERENCES predicates(predicate_id),
            object_value TEXT NOT NULL, object_type TEXT NOT NULL DEFAULT 'uri',
            proof_type TEXT NOT NULL DEFAULT 'observation', source TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
    db.commit()


def _rebuild_fts(db: sqlite3.Connection) -> None:
    """Create and populate FTS5 tables."""
    db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
            node_id UNINDEXED, label_text, definition_text,
            content=nodes, content_rowid=rowid, tokenize='unicode61')""")
    cnt = db.execute("SELECT COUNT(*) AS c FROM nodes_fts").fetchone()["c"]
    if cnt == 0:
        try:
            db.execute("""INSERT INTO nodes_fts (rowid, node_id, label_text, definition_text)
                SELECT rowid, node_id, label_text, definition_text FROM nodes""")
        except sqlite3.DatabaseError as exc:
            print(f"  ⚠  Failed to populate nodes_fts: {exc}")

    db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS predicates_fts USING fts5(
            predicate_id UNINDEXED, labels, descriptions, aliases,
            content=predicates, content_rowid=rowid, tokenize='unicode61')""")
    cnt = db.execute("SELECT COUNT(*) AS c FROM predicates_fts").fetchone()["c"]
    if cnt == 0:
        try:
            db.execute("""INSERT INTO predicates_fts (rowid, predicate_id, labels, descriptions, aliases)
                SELECT rowid, predicate_id, labels, descriptions, aliases FROM predicates""")
        except sqlite3.DatabaseError as exc:
            print(f"  ⚠  Failed to populate predicates_fts: {exc}")
    db.commit()


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    src_path = Path(sys.argv[1])
    dst_path = Path(sys.argv[2])

    if not src_path.exists():
        print(f"❌ Source DB not found: {src_path}")
        sys.exit(1)

    print(f"📂 Source: {src_path}")
    print(f"📂 Target: {dst_path}")

    src = sqlite3.connect(str(src_path))
    src.row_factory = sqlite3.Row

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(str(dst_path))
    dst.execute("PRAGMA journal_mode=wal")
    dst.execute("PRAGMA foreign_keys=OFF")
    dst.row_factory = sqlite3.Row

    print("\n🔨 Creating target schema...")
    _create_schema(dst)

    total_copied = 0
    for src_table, dst_table, col_map, pk in TABLES:
        n = copy_table(src, dst, src_table, dst_table, col_map, pk)
        total_copied += n

    print("🔨 Rebuilding FTS indexes...")
    _rebuild_fts(dst)

    src.close()
    dst.close()
    print(f"\n🎉 Migration complete! {total_copied} total rows copied.")
    print(f"   Target DB: {dst_path}")
    print(f"   Size: {dst_path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
