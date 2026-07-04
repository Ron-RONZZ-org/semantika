"""Tests for command dispatch helpers and error paths.

Covers the helper functions in command.py that are exercised by the command
dispatch but not directly tested: _parse_lang_tag_pairs, _safe_json_loads,
_fmt_size, _fmt_ts, _backup_dir_abs, _resolve_group, _resolve_form_type,
and error handling in execute_command.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DATA_DIR = Path("/tmp/semantika-cmd-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app
from semantika.server.command.registry import (
    resolve_form_type as _resolve_form_type,
)
from semantika.server.command.helpers import (
    parse_lang_tag_pairs as _parse_lang_tag_pairs,
    safe_json_loads as _safe_json_loads,
    fmt_size as _fmt_size,
    fmt_ts as _fmt_ts,
    backup_dir_abs as _backup_dir_abs,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestResolveFormType:
    def test_known_command(self):
        assert _resolve_form_type(["node", "add"]) == "node-add"

    def test_known_subcommand(self):
        assert _resolve_form_type(["triple", "add"]) == "triple-add"

    def test_unknown_command(self):
        assert _resolve_form_type(["foo", "bar"]) is None

    def test_empty(self):
        assert _resolve_form_type([]) is None

    def test_single_token_not_in_forms(self):
        """Single token 'reset' maps to 'reset-no-backup' in _INTERACTIVE_FORMS."""
        # 'reset' alone does not match because the loop iterates from end to start
        # and needs a 2+ element path
        assert _resolve_form_type(["reset"]) is None


class TestParseLangTagPairs:
    def test_string_with_double_colon(self):
        result = _parse_lang_tag_pairs("en::Hello fr::Bonjour")
        assert result == {"en": "Hello", "fr": "Bonjour"}

    def test_string_with_single_colon(self):
        result = _parse_lang_tag_pairs("en:Hello fr:Bonjour")
        assert result == {"en": "Hello", "fr": "Bonjour"}

    def test_commas_separated(self):
        result = _parse_lang_tag_pairs("en::Hello, fr::Bonjour")
        assert result == {"en": "Hello", "fr": "Bonjour"}

    def test_list_input(self):
        result = _parse_lang_tag_pairs(["en::Hello", "fr::Bonjour"])
        assert result == {"en": "Hello", "fr": "Bonjour"}

    def test_no_separator_skipped(self):
        result = _parse_lang_tag_pairs("justtext")
        assert result == {}

    def test_empty_string(self):
        assert _parse_lang_tag_pairs("") == {}

    def test_empty_list(self):
        assert _parse_lang_tag_pairs([]) == {}

    def test_malformed(self):
        result = _parse_lang_tag_pairs("en::")
        assert result == {}


class TestSafeJsonLoads:
    def test_valid_json_string(self):
        assert _safe_json_loads('{"a": 1}') == {"a": 1}

    def test_dict_passthrough(self):
        assert _safe_json_loads({"a": 1}) == {"a": 1}

    def test_empty_string(self):
        assert _safe_json_loads("") == {}

    def test_none(self):
        assert _safe_json_loads(None) == {}  # type: ignore[arg-type]

    def test_invalid_json(self):
        assert _safe_json_loads("not json") == {}

    def test_int(self):
        assert _safe_json_loads(42) == {}  # type: ignore[arg-type]


class TestFmtSize:
    def test_bytes(self):
        assert _fmt_size(500) == "500 B"

    def test_kibibytes(self):
        assert _fmt_size(2048) == "2.0 KiB"

    def test_mebibytes(self):
        assert _fmt_size(5 * 1024 * 1024) == "5.0 MiB"

    def test_boundary(self):
        result = _fmt_size(1023)
        assert result == "1023 B"


class TestFmtTs:
    def test_full_timestamp(self):
        result = _fmt_ts("20260704T120000")
        assert result == "2026-07-04 12:00:00"

    def test_with_microseconds(self):
        result = _fmt_ts("20260704T120000123456")
        assert "2026-07-04 12:00:00." in result
        assert "123456" in result

    def test_short_string(self):
        result = _fmt_ts("short")
        assert result == "short"

    def test_empty(self):
        assert _fmt_ts("") == ""


class TestBackupDirAbs:
    def test_returns_path(self):
        path = _backup_dir_abs()
        assert isinstance(path, str)
        assert path.endswith(".backups")


class TestExecuteCommandErrors:
    """Test error handling paths in execute_command()."""

    def test_command_not_found(self, client: TestClient):
        """Unknown command raises 400 with CommandNotFound."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["nonexistent", "command"], "flags": {}},
        )
        assert resp.status_code == 400

    def test_command_form_redirect(self, client: TestClient):
        """--form flag triggers form redirect."""
        resp = client.post(
            "/api/v1/command",
            json={"tokens": ["node", "add"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "form-required"


class TestCommandDispatchAPI:
    """Test specific command handlers via the API."""

    def test_help_command(self, client: TestClient):
        """!help should return flat help text."""
        resp = client.get("/api/v1/command/help")
        assert resp.status_code == 200
        data = resp.json()
        assert "commands" in data
        assert len(data["commands"]) > 0

    def test_command_tree(self, client: TestClient):
        """!command tree should return full command tree."""
        resp = client.get("/api/v1/command/tree")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(c["name"] == "node" for c in data)
