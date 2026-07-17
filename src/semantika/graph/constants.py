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

SM_NAMESPACE = "https://sm.ronzz.org/predicates/"

KNOWN_PREFIXES: dict[str, str] = {
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd":  "http://www.w3.org/2001/XMLSchema#",
    "owl":  "http://www.w3.org/2002/07/owl#",
    "sm":   SM_NAMESPACE,
}

# ── Core predicate IDs (soft-protected from accidental deletion) ────────
#
# These are now derived from the YAML seed file (``builtins.yaml``) via
# :func:`semantika.graph.builtin_loader.get_core_predicate_ids`, which
# collects all predicates with ``tier: 1`` or ``tier: w3c``.
#
# ``CORE_SM_PREDICATES`` is a lazy proxy object that behaves like a
# ``frozenset[str]`` for the ``in`` operator, but delegates to the
# cached loader so that ``!builtins reload`` (which calls
# :func:`builtin_loader.invalidate_caches`) takes effect without a
# server restart.

from typing import Iterator as _Iterator


class _CorePredicateSet:
    """Lazy-delegating frozenset-like container for core predicate IDs.

    Supports ``in``, ``len``, ``iter``, and ``repr`` — enough for the
    ``PredicateService.is_core_predicate()`` use case.
    """

    def __contains__(self, item: object) -> bool:
        from semantika.graph.builtin_loader import get_core_predicate_ids
        return item in get_core_predicate_ids()

    def __iter__(self) -> _Iterator[str]:
        from semantika.graph.builtin_loader import get_core_predicate_ids
        return iter(get_core_predicate_ids())

    def __len__(self) -> int:
        from semantika.graph.builtin_loader import get_core_predicate_ids
        return len(get_core_predicate_ids())

    def __repr__(self) -> str:
        from semantika.graph.builtin_loader import get_core_predicate_ids
        return repr(get_core_predicate_ids())


CORE_SM_PREDICATES: frozenset[str] = _CorePredicateSet()  # type: ignore[assignment]


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
