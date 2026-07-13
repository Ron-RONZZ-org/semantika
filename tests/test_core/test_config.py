"""Tests for the semantika.jsonc config loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from semantika.core.config import DEFAULT_NODE_IRI, DEFAULT_PREDICATE_IRI, get_config, get_iri_template, reload_config

# Import the real module to restore after patching
from semantika.core import config as _cfg_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_config():
    """Ensure config cache is restored after each test so other tests aren't affected."""
    yield
    # Restore the real config_dir and ensure_dirs by reloading with the unpatched module
    reload_config()


def test_default_config_when_no_file():
    """When no semantika.jsonc exists, built-in defaults are used."""
    cfg = get_config()
    # Should be empty dict (no file found)
    assert isinstance(cfg, dict)


def test_default_templates():
    """Default IRI templates are returned when no config file."""
    assert get_iri_template("node") == DEFAULT_NODE_IRI
    assert get_iri_template("predicate") == DEFAULT_PREDICATE_IRI
    assert "$id" in DEFAULT_NODE_IRI
    assert "$id" in DEFAULT_PREDICATE_IRI


def test_reload_clears_cache():
    """reload_config() clears cache and re-reads."""
    # Initial state
    cfg1 = get_config()
    assert cfg1 is not None
    # Reload should not raise
    cfg2 = reload_config()
    assert isinstance(cfg2, dict)


def test_iri_template_with_custom_file(tmp_path: Path, monkeypatch):
    """When semantika.jsonc specifies custom templates, they are used."""
    custom_node = "https://example.org/entities/$id"
    custom_pred = "https://example.org/relations/$id"
    config_dir = tmp_path / ".config" / "semantika"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "semantika.jsonc"
    config_file.write_text(
        '{\n'
        '    // custom IRI templates\n'
        '    "node_iri": "https://example.org/entities/$id",\n'
        '    "predicate_iri": "https://example.org/relations/$id"\n'
        '}\n',
        encoding="utf-8",
    )
    # Point config_dir to our temp dir
    monkeypatch.setattr("semantika.core.config.config_dir", lambda: config_dir)
    monkeypatch.setattr("semantika.core.config.ensure_dirs", lambda: None)

    reload_config()
    assert get_iri_template("node") == custom_node
    assert get_iri_template("predicate") == custom_pred


def test_iri_template_fallback_for_unknown_kind():
    """An unknown kind falls back to the predicate default (since kind != "node")."""
    tpl = get_iri_template("unknown")
    assert tpl == DEFAULT_PREDICATE_IRI


def test_config_accepts_semantika_json_fallback(tmp_path: Path, monkeypatch):
    """If semantika.jsonc doesn't exist but semantika.json does, it is read."""
    config_dir = tmp_path / ".config" / "semantika"
    config_dir.mkdir(parents=True)
    json_file = config_dir / "semantika.json"
    json_file.write_text(
        json.dumps({"node_iri": "https://test.local/item/$id"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("semantika.core.config.config_dir", lambda: config_dir)
    monkeypatch.setattr("semantika.core.config.ensure_dirs", lambda: None)

    reload_config()
    assert get_iri_template("node") == "https://test.local/item/$id"
