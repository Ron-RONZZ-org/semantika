"""Shared fixtures for server tests.

Provides an isolated test database and mocked services that are
automatically patched into all handler modules.  When a new handler
module is added, it is auto-discovered — no manual fixture updates
needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from semantika.core import SemantikaDB
from semantika.graph.db import SCHEMA, PROOF_SCHEMA, REVIEW_SCHEMA
from semantika.graph.node_service import NodeService
from semantika.graph.predicate_group_service import PredicateGroupService
from semantika.graph.predicate_service import PredicateService
from semantika.graph.proof_service import ProofService
from semantika.graph.review_service import ReviewService
from semantika.graph.triple_service import TripleService

_HANDLERS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "semantika"
    / "server"
    / "command"
    / "handlers"
)

_HANDLER_MODULE = "semantika.server.command.handlers"


def _handler_modules_using_get_services() -> list[str]:
    """Discover handler modules that import ``get_services`` at module level.

    Returns fully-qualified module paths (e.g.
    ``semantika.server.command.handlers.graph``).
    """
    results: list[str] = []
    for fpath in _HANDLERS_DIR.glob("*.py"):
        if fpath.name == "__init__.py":
            continue
        source = fpath.read_text(encoding="utf-8")
        if re.search(
            r"from\s+semantika\.graph\.db\s+import\s+.*\bget_services\b",
            source,
        ):
            mod_name = fpath.stem
            results.append(f"{_HANDLER_MODULE}.{mod_name}")
    return results


@pytest.fixture
def db(tmp_path: Path) -> SemantikaDB:
    """Create an isolated test database."""
    db_path = tmp_path / "test.db"
    db = SemantikaDB(db_path)
    for table, sql in SCHEMA.items():
        db.init_schema({table: sql})
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_triples_pos ON triples(predicate_id, object_value, subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_triples_osp ON triples(object_value, object_type, predicate_id, subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_triples_pred_subj ON triples(predicate_id, subject_id)",
    ]:
        db.execute(idx)
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
        "  node_id UNINDEXED, label_text, definition_text,"
        "  content=nodes, content_rowid=rowid, tokenize='unicode61'"
        ")"
    )
    for table, sql in {**REVIEW_SCHEMA, **PROOF_SCHEMA}.items():
        db.init_schema({table: sql})
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _build_services(db: SemantikaDB) -> dict:
    """Construct the standard services dict for a given DB."""
    from semantika.graph.builtin_type_service import BuiltinTypeService
    return {
        "node": NodeService(db),
        "predicate": PredicateService(db),
        "predicate_group": PredicateGroupService(db),
        "triple": TripleService(db),
        "review": ReviewService(db),
        "proof": ProofService(db),
        "builtin_type": BuiltinTypeService(
            db,
            NodeService(db),
            TripleService(db),
            PredicateService(db),
        ),
    }


@pytest.fixture
def services(db: SemantikaDB, mock_services: None) -> dict:
    """Return all services initialized on the test DB.

    Also triggers ``mock_services`` so handler dispatch calls use the
    isolated database automatically.
    """
    return _build_services(db)


@pytest.fixture
def mock_services(monkeypatch: pytest.MonkeyPatch, db: SemantikaDB) -> None:
    """Mock get_services() in graph.db and all handler modules.

    Patching is automatic — every handler module that imports
    ``get_services`` at module level is discovered and patched.

    **Not autouse**: handler dispatch tests must explicitly request this
    fixture (or a fixture that depends on it, like ``seeded``) so that
    API E2E tests (``test_api_e2e.py``) are not affected.
    """
    svc = _build_services(db)
    import semantika.graph.db as graph_db

    monkeypatch.setattr(graph_db, "get_services", lambda: svc)

    for mod_path in _handler_modules_using_get_services():
        monkeypatch.setattr(f"{mod_path}.get_services", lambda: svc)
