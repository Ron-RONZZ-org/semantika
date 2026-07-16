"""Consistency test: all three ``KNOWN_PREFIXES`` consumers match the
single source of truth in ``graph/constants.py``.

This catches drift if someone adds a new prefix to one location but
forgets the others.
"""

from __future__ import annotations

from semantika.graph.constants import KNOWN_PREFIXES


def test_sparql_engine_imports_same_prefixes() -> None:
    """``sparql/engine.py`` must import from ``graph/constants.py``."""
    from semantika.graph.sparql.engine import _KNOWN_PREFIXES  # type: ignore[attr-defined]

    assert _KNOWN_PREFIXES is KNOWN_PREFIXES, (
        "sparql/engine.py has a local copy of KNOWN_PREFIXES instead of "
        "importing from graph.constants"
    )


def test_triple_turtle_imports_same_prefixes() -> None:
    """``triple_turtle.py`` must import from ``graph/constants.py``."""
    from semantika.graph.triple_turtle import _KNOWN_PREFIXES  # type: ignore[attr-defined]

    assert _KNOWN_PREFIXES is KNOWN_PREFIXES, (
        "triple_turtle.py has a local copy of KNOWN_PREFIXES instead of "
        "importing from graph.constants"
    )


def test_db_uses_same_prefixes() -> None:
    """``db.py`` must use the same KNOWN_PREFIXES (imported from constants)."""
    from semantika.graph.db import compute_iri
    from semantika.graph.constants import SM_NAMESPACE

    # If db.py has its own copy, sm: predicates would resolve via the
    # user's configured template rather than the stable Semantika namespace.
    iri = compute_iri("sm:depicts")
    assert iri == f"{SM_NAMESPACE}depicts", (
        f"compute_iri returned {iri!r} instead of {SM_NAMESPACE}depicts. "
        "db.py may have its own copy of KNOWN_PREFIXES."
    )


def test_compute_iri_known_prefixes_roundtrip() -> None:
    """compute_iri on all known prefixes returns the expected URIs."""
    from semantika.graph.constants import SM_NAMESPACE
    from semantika.graph.db import compute_iri

    cases: dict[str, str] = {
        "rdf:type": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
        "rdfs:label": "http://www.w3.org/2000/01/rdf-schema#label",
        "rdfs:subClassOf": "http://www.w3.org/2000/01/rdf-schema#subClassOf",
        "owl:sameAs": "http://www.w3.org/2002/07/owl#sameAs",
        "owl:disjointWith": "http://www.w3.org/2002/07/owl#disjointWith",
        "owl:inverseOf": "http://www.w3.org/2002/07/owl#inverseOf",
        "rdfs:seeAlso": "http://www.w3.org/2000/01/rdf-schema#seeAlso",
        "sm:depicts": f"{SM_NAMESPACE}depicts",
        "sm:theme": f"{SM_NAMESPACE}theme",
        "xsd:string": "http://www.w3.org/2001/XMLSchema#string",
    }
    for internal_id, expected_iri in cases.items():
        assert compute_iri(internal_id) == expected_iri, (
            f"compute_iri({internal_id!r}) should be {expected_iri!r}"
        )


def test_sm_iri_rejects_template() -> None:
    """``sm:`` predicates have stable IRIs and never match user templates."""
    from semantika.graph.db import _iri_is_non_template

    assert _iri_is_non_template("sm:depicts") is True, (
        "sm:depicts should be recognized as a known-prefix predicate "
        "with a fixed namespace"
    )
    assert _iri_is_non_template("sm:theme") is True


def test_sm_predicate_source_is_semantika() -> None:
    """All ``sm:`` seed predicates should have source='semantika'."""
    from semantika.graph.builtin_seed_data import TIER1_SM_PREDICATES, TIER2_SM_PREDICATES

    for pid, source, _, _ in TIER1_SM_PREDICATES + TIER2_SM_PREDICATES:
        assert source == "semantika", (
            f"{pid} has source={source!r}, expected 'semantika'"
        )
