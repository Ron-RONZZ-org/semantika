"""Shared constants and heuristic helpers for the graph module.

Ported from A-semantika's ``_constants.py``.
"""

from __future__ import annotations

import re

# FTS5 keywords that need to be lowercased (not stripped) when they
# appear in user search queries, so they are treated as content terms
# rather than FTS5 operators.
FTS5_KEYWORDS: frozenset[str] = frozenset({
    "AND",
    "OR",
    "NOT",
    "NEAR",
    "COLUMN",
})

# ── Known RDF prefix namespaces ─────────────────────────────────────────
# Single source of truth — imported by db.py, sparql/engine.py, triple_turtle.py.
# Never maintain duplicate copies in those files.

SM_NAMESPACE = "https://semantika.app/sm/"

KNOWN_PREFIXES: dict[str, str] = {
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd":  "http://www.w3.org/2001/XMLSchema#",
    "owl":  "http://www.w3.org/2002/07/owl#",
    "sm":   SM_NAMESPACE,
}

# ── Core sm: predicates (soft-protected from accidental deletion) ───────

CORE_SM_PREDICATES: frozenset[str] = frozenset({
    "sm:depicts",
    "sm:programmingLanguage",
    "sm:theme",
    "sm:dimension",
    "sm:canonicalLink",
    "sm:hasSource",
    "sm:attributedTo",
    "sm:partOf",
})

_UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{8}([0-9a-f]{1,8}|-[0-9a-f]{1,7})?$", re.IGNORECASE)


def looks_like_uuid_prefix(text: str) -> bool:
    """Check if text looks like a UUID prefix (8-16 hex chars, optional canonical hyphen)."""
    return 8 <= len(text) <= 16 and bool(_UUID_PREFIX_RE.match(text))


def is_numeric(text: str) -> bool:
    """Check if text represents a numeric value (int or float)."""
    try:
        float(text)
        return True
    except (ValueError, TypeError):
        return False


# ── Esperanto → English label mapping reference ────────────────────────
# These are the EO→EN renames applied throughout the port:
#
#  nodes table:
#    node_id        ← node_id (kept)
#    labels         ← etikedoj
#    label_text     ← (kept)
#    definitions    ← difinoj
#    definition_text ← difin_text
#    created_at     ← kreita_je
#    updated_at     ← modifita_je
#    deleted_at     ← forigita_je
#
#  predicates table:
#    predicate_id   ← (kept)
#    labels         ← etikedoj
#    descriptions   ← priskriboj
#    created_at     ← kreita_je
#    updated_at     ← modifita_je
#
#  triples table:
#    subject_id     ← subject_uuid
#    predicate_id   ← (kept)
#    object_type    ← (kept)
#    object_value   ← (kept)
#    object_lang    ← (kept)
#    object_datatype ← (kept)
#    object_node_id ← object_node_uuid (generated)
#    created_at     ← kreita_je
