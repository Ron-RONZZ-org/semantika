"""API E2E tests for prompt command endpoints.

Covers:
- GET  /api/v1/prompt-commands/list
- POST /api/v1/prompt-commands/expand
- POST /api/v1/prompt-commands/execute
- POST /api/v1/prompt-commands/execute/resume
- POST /api/v1/prompt-commands/execute/stream

Because these endpoints depend on user-defined prompt-command files on disk
and an optional LLM provider, tests focus on parameter validation, 404
handling, and disk-based setup.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Must override config/data dirs before importing app
TEST_DATA_DIR = Path("/tmp/semantika-pcmd-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

# Point config dir to a temp location so we can plant prompt command files
TEST_CONFIG_DIR = TEST_DATA_DIR / "config"
TEST_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_CONFIG_DIR"] = str(TEST_CONFIG_DIR)

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB and config dir."""
    app = create_app()
    with TestClient(app) as c:
        yield c


def _write_prompt_command(name: str, content: str) -> None:
    """Write a prompt-command file into the test config dir."""
    cmds_dir = TEST_CONFIG_DIR / "commands"
    cmds_dir.mkdir(parents=True, exist_ok=True)
    (cmds_dir / f"{name}.md").write_text(content, encoding="utf-8")


# ── GET /list ───────────────────────────────────────────────────────────


class TestPromptCommandsList:
    """GET /api/v1/prompt-commands/list"""

    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/v1/prompt-commands/list")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_commands(self, client: TestClient):
        _write_prompt_command("greet", "# Say hello\nHello $1!")
        resp = client.get("/api/v1/prompt-commands/list")
        assert resp.status_code == 200
        data = resp.json()
        assert any(c["name"] == "greet" for c in data)

    def test_list_entry_structure(self, client: TestClient):
        _write_prompt_command("test-cmd", "# A test command\nTemplate body with $1")
        resp = client.get("/api/v1/prompt-commands/list")
        assert resp.status_code == 200
        for entry in resp.json():
            assert "name" in entry
            assert "description" in entry
            assert "param_count" in entry

    def test_list_ignores_files_without_heading(self, client: TestClient):
        _write_prompt_command("no-heading", "No heading here")
        resp = client.get("/api/v1/prompt-commands/list")
        names = [c["name"] for c in resp.json()]
        assert "no-heading" not in names


# ── POST /expand ────────────────────────────────────────────────────────


class TestPromptCommandsExpand:
    """POST /api/v1/prompt-commands/expand"""

    def test_expand_missing_name(self, client: TestClient):
        resp = client.post("/api/v1/prompt-commands/expand", json={})
        assert resp.status_code == 400
        assert "name" in resp.text.lower()

    def test_expand_not_found(self, client: TestClient):
        resp = client.post(
            "/api/v1/prompt-commands/expand",
            json={"name": "nonexistent", "args": []},
        )
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_expand_with_args(self, client: TestClient):
        _write_prompt_command("repeat", "# Repeat {{arg}}\nYou said: $1")
        resp = client.post(
            "/api/v1/prompt-commands/expand",
            json={"name": "repeat", "args": ["hello"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "repeat"
        assert "You said: hello" in data.get("expanded", "")

    def test_expand_returns_template_and_expanded(self, client: TestClient):
        _write_prompt_command("show", "# Show it\nShow me $1 and $2")
        resp = client.post(
            "/api/v1/prompt-commands/expand",
            json={"name": "show", "args": ["A", "B"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "template" in data
        assert "expanded" in data
        assert "A" in data["expanded"]
        assert "B" in data["expanded"]

    def test_expand_no_args_removes_placeholders(self, client: TestClient):
        """With no args, positional placeholders are stripped (not replaced)."""
        _write_prompt_command("hi", "# Say hi\nSay $1!")
        resp = client.post(
            "/api/v1/prompt-commands/expand",
            json={"name": "hi", "args": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        # $1 without args becomes empty string after expansion
        assert "Say " in data["expanded"]
        assert "$1" not in data["expanded"]


# ── POST /execute ───────────────────────────────────────────────────────


class TestPromptCommandsExecute:
    """POST /api/v1/prompt-commands/execute"""

    def test_execute_missing_name(self, client: TestClient):
        resp = client.post("/api/v1/prompt-commands/execute", json={})
        assert resp.status_code == 400

    def test_execute_not_found(self, client: TestClient):
        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "ghost", "args": []},
        )
        assert resp.status_code == 404

    def test_execute_always_returns_valid_structure(self, client: TestClient):
        """Execute always returns a structured response, even without LLM."""
        _write_prompt_command("test-run", "# Run\nRun this!")
        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "test-run", "args": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "type" in data
        # Valid types: "status" (no LLM), "chat" (empty result), "confirm_tool"
        assert data["type"] in ("status", "chat")

    def test_execute_template_special_case(self, client: TestClient):
        """/template special case returns search_plan or status."""
        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "template", "args": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Without LLM or args, should indicate missing description
        assert "type" in data


# ── POST /execute/resume ────────────────────────────────────────────────


class TestPromptCommandsResume:
    """POST /api/v1/prompt-commands/execute/resume"""

    def test_resume_missing_session_id(self, client: TestClient):
        resp = client.post("/api/v1/prompt-commands/execute/resume", json={})
        assert resp.status_code == 404

    def test_resume_invalid_session_id(self, client: TestClient):
        resp = client.post(
            "/api/v1/prompt-commands/execute/resume",
            json={"session_id": "does-not-exist"},
        )
        assert resp.status_code == 404


# ── POST /execute/stream (SSE) ──────────────────────────────────────────


class TestPromptCommandsStream:
    """POST /api/v1/prompt-commands/execute/stream"""

    def test_stream_missing_name(self, client: TestClient):
        resp = client.post("/api/v1/prompt-commands/execute/stream", json={})
        assert resp.status_code == 400

    def test_stream_not_found(self, client: TestClient):
        resp = client.post(
            "/api/v1/prompt-commands/execute/stream",
            json={"name": "no-such-command", "args": []},
        )
        assert resp.status_code == 200  # SSE returns 200 with error in body
        assert resp.headers.get("content-type", "").startswith("text/event-stream")

    def test_stream_returns_sse_events(self, client: TestClient):
        _write_prompt_command("stream-test", "# Stream test\nHello from stream!")
        resp = client.post(
            "/api/v1/prompt-commands/execute/stream",
            json={"name": "stream-test", "args": []},
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        body = resp.text
        # Should contain SSE events
        assert "data:" in body
        assert "[DONE]" in body or "data: [DONE]" in body
