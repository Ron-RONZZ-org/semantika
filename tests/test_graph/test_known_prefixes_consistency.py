"""Consistency test: all three ``KNOWN_PREFIXES`` consumers match the
single source of truth in ``graph/constants.py``.

This catches drift if someone adds a new prefix to one location but
forgets the others.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    from semantika.graph.builtin_loader import get_predicate_catalog

    catalog = get_predicate_catalog()
    for pid, entry in catalog.items():
        if pid.startswith("sm:"):
            assert entry.get("source") == "semantika", (
                f"{pid} has source={entry.get('source')!r}, expected 'semantika'"
            )


def test_sm_namespace_url() -> None:
    """``SM_NAMESPACE`` has the correct canonical URL."""
    from semantika.graph.constants import SM_NAMESPACE

    assert SM_NAMESPACE == "https://sm.ronzz.org/predicates/", (
        f"SM_NAMESPACE is {SM_NAMESPACE!r}, expected 'https://sm.ronzz.org/predicates/'"
    )


def test_default_node_template_url() -> None:
    """Default node IRI template uses sm.ronzz.org domain."""
    from semantika.core.config import DEFAULT_NODE_IRI

    assert DEFAULT_NODE_IRI == "https://sm.ronzz.org/nodes/$id", (
        f"DEFAULT_NODE_IRI is {DEFAULT_NODE_IRI!r}, "
        f"expected 'https://sm.ronzz.org/nodes/$id'"
    )


def test_default_predicate_template_url() -> None:
    """Default predicate IRI template uses sm.ronzz.org domain."""
    from semantika.core.config import DEFAULT_PREDICATE_IRI

    assert DEFAULT_PREDICATE_IRI == "https://sm.ronzz.org/predicates/$id", (
        f"DEFAULT_PREDICATE_IRI is {DEFAULT_PREDICATE_IRI!r}, "
        f"expected 'https://sm.ronzz.org/predicates/$id'"
    )


def test_compute_iri_default_node_template(tmp_path: Path, monkeypatch) -> None:
    """compute_iri with bare node ID uses DEFAULT_NODE_IRI when no config file."""
    from semantika.graph.db import compute_iri

    # Ensure no config file is found by pointing to an empty dir
    from semantika.core import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(cfg_mod, "ensure_dirs", lambda: None)
    cfg_mod.reload_config()

    iri = compute_iri("PHOTO")
    assert iri == "https://sm.ronzz.org/nodes/PHOTO", (
        f"compute_iri('PHOTO') returned {iri!r}, "
        f"expected 'https://sm.ronzz.org/nodes/PHOTO'"
    )


def test_compute_iri_default_predicate_template(tmp_path: Path, monkeypatch) -> None:
    """compute_iri with unknown-prefix predicate uses DEFAULT_PREDICATE_IRI."""
    from semantika.graph.db import compute_iri

    from semantika.core import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(cfg_mod, "ensure_dirs", lambda: None)
    cfg_mod.reload_config()

    iri = compute_iri(":hasFilePath")
    assert iri == "https://sm.ronzz.org/predicates/:hasFilePath", (
        f"compute_iri(':hasFilePath') returned {iri!r}, "
        f"expected 'https://sm.ronzz.org/predicates/:hasFilePath'"
    )
