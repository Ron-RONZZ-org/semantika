"""Cowrite — LLM-assisted form editing for Semantika.

Backend context gathering, DB schema, and route handler.
"""

from __future__ import annotations

# Writing samples table schema (registered in graph/db.py init_db)
COWRITE_SAMPLES_SCHEMA = {
    "cowrite_samples": """
        CREATE TABLE IF NOT EXISTS cowrite_samples (
            uuid            TEXT PRIMARY KEY,
            form_type       TEXT NOT NULL,
            instruction     TEXT NOT NULL DEFAULT '',
            original        TEXT NOT NULL,  -- JSON: {field: text}
            revised         TEXT NOT NULL,  -- JSON: {field: text}
            word_count      INTEGER NOT NULL DEFAULT 0,
            source_domain   TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL
        )
    """,
}

__all__ = [
    "COWRITE_SAMPLES_SCHEMA",
]
