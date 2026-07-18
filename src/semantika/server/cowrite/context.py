"""Context gatherers for LLM co-writing.

Provides ``gather_context()`` that retrieves recent writing samples to
help the LLM match the user's personal style.  This is the READ side
of the writing samples RAG system — the WRITE side (saving samples after
approved edits) is deferred to a future implementation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def gather_context(form_type: str, fields: dict[str, str]) -> dict[str, Any]:
    """Gather relevant context data for the given form type.

    Currently returns up to 5 most recent writing samples, regardless
    of form_type.  Future versions may filter by domain or perform
    semantic vector search.

    Returns:
        Dict with a ``"writing_samples"`` key, or empty dict if no
        samples are available.
    """
    # Skip context gathering if we have no field text to match against
    text_values = [v.strip() for v in fields.values() if v.strip()]
    if not text_values:
        return {}

    try:
        from semantika.graph.db import get_db

        db = get_db()
    except Exception:
        logger.warning("Cannot open graph DB for context gathering")
        return {}

    return _recent_samples_only(db)


def _recent_samples_only(db: Any) -> dict[str, Any]:
    """Return the 5 most recent writing samples (no vector search).

    Args:
        db: Database connection with ``cowrite_samples`` table.

    Returns:
        Dict with ``writing_samples`` key, or empty dict if no samples.
    """
    try:
        rows = db.execute(
            "SELECT uuid, form_type, instruction, original, revised, "
            "       word_count, source_domain "
            "FROM cowrite_samples "
            "ORDER BY created_at DESC LIMIT 5"
        )
        samples = [
            {
                "uuid": r["uuid"],
                "form_type": r["form_type"] or "",
                "instruction": r["instruction"] or "",
                "original": json.loads(r["original"]) if isinstance(r.get("original"), str) else {},
                "revised": json.loads(r["revised"]) if isinstance(r.get("revised"), str) else {},
                "word_count": r["word_count"],
                "source_domain": r["source_domain"] or "",
            }
            for r in rows
        ]
        if samples:
            return {"writing_samples": samples}
    except Exception:
        logger.debug("No writing samples found or table missing")
        pass
    return {}
