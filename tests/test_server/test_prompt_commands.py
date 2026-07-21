"""Tests for prompt command endpoints with multi-round tool-calling.

Covers:
- Standard prompt command execution (plain chat fallback when no tools)
- Multi-round tool-calling with real command dispatch
- Human-in-the-loop confirmation gating for write/destructive commands
- Resume endpoint for confirming/rejecting tool calls
- Error handling for missing commands and LLM failures
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lighterllm.llm.base import ChatResult, ToolCall

from semantika.server.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Helpers ──────────────────────────────────────────────────────────────────


def _create_prompt_command(tmp_path: Path, name: str, content: str) -> None:
    """Create a prompt command file under the isolated config dir."""
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / f"{name}.md").write_text(content, encoding="utf-8")


def _configure_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the provider available with a fake key (needed before mocking)."""
    from semantika.server.llm.provider import get_provider
    provider = get_provider()
    provider.configure(provider_type="openai", api_key="sk-fake-test")


def _mock_chat_with_tools(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[ChatResult],
) -> None:
    """Mock ``chat_with_tools`` to return controlled :class:`ChatResult` objects.

    Each call pops the first response; the last is reused.
    """
    _configure_provider(monkeypatch)
    from semantika.server.llm.provider import get_provider
    provider = get_provider()
    call_count = 0

    async def _mock(messages, tools, *, tool_choice=None):
        nonlocal call_count
        idx = min(call_count, len(responses) - 1) if responses else 0
        call_count += 1
        return responses[idx] if responses else ChatResult(content="(empty)")

    monkeypatch.setattr(provider, "chat_with_tools", _mock)


# ── Standard prompt command execution ────────────────────────────────────────


class TestStandardPromptCommand:
    """Test basic prompt command execution (plain chat, no tool calls)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        _create_prompt_command(tmp_path, "greet", "# Hello\nSay hello to $1\n")
        _mock_chat_with_tools(monkeypatch, [ChatResult(content="Hello, World!")])

    def test_execute_basic(self, client: TestClient):
        """A simple prompt command returns a chat response."""
        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "greet", "args": ["World"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "chat"

    def test_execute_not_found(self, client: TestClient):
        """Unknown command returns 404."""
        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "nonexistent", "args": []},
        )
        assert resp.status_code == 404

    def test_execute_no_name(self, client: TestClient):
        """Missing name returns 400."""
        resp = client.post("/api/v1/prompt-commands/execute", json={"args": []})
        assert resp.status_code == 400


# ── Multi-round tool-calling ─────────────────────────────────────────────────


class TestToolCalling:
    """Test that the LLM can call tools, get results, and continue the loop."""

    GREET_TEMPLATE = "# Search and summarise\nSearch for $1 and tell me what you find.\n"

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        _create_prompt_command(tmp_path, "search-summarise", self.GREET_TEMPLATE)

    def test_tool_call_round_trip(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """LLM calls a READ tool, gets real result, then produces final answer."""
        # First call: LLM calls node_search
        # Second call: LLM produces final answer
        _mock_chat_with_tools(monkeypatch, [
            ChatResult(tool_calls=[
                ToolCall(
                    id="call_1",
                    function={"name": "node_search", "arguments": '{"q": "nostalgia"}'},
                ),
            ]),
            ChatResult(content="I found nodes about nostalgia."),
        ])

        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "search-summarise", "args": ["nostalgia"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "chat"
        assert data["data"]["html"] is not None

    def test_empty_args_still_works(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Prompt command with empty args still reaches the LLM."""
        _mock_chat_with_tools(monkeypatch, [ChatResult(content="Please provide a search term.")])

        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "search-summarise", "args": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "chat"


# ── Human-in-the-loop confirmation ──────────────────────────────────────────


class TestConfirmationGate:
    """Write and destructive tool calls are gated behind user confirmation.

    READ-level commands (search, list, view, stats) pass through without
    confirmation.  WRITE-level (add, update) and DESTRUCTIVE-level (delete,
    merge, reset) commands trigger the confirmation gate.
    """

    MERGE_TEMPLATE = "# Merge nodes\nMerge $1 into $2.\n"

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Isolate both config and data directories per test.
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("SEMANTIKA_DATA_DIR", str(tmp_path))
        _create_prompt_command(tmp_path, "merge-nodes", self.MERGE_TEMPLATE)
        # Reset DB/services singletons so this test starts clean regardless
        # of state left by previous test classes.
        from semantika.graph.db import close_db, reset_services
        close_db()
        reset_services()
        yield

    @staticmethod
    def _make_nodes(**ids: str) -> None:
        """Create nodes with the given keyword IDs (id → label)."""
        from semantika.graph.db import get_services
        svc = get_services()
        for nid, label in ids.items():
            svc["node"].create({"node_id": nid, "labels": {"en": label}})

    def test_destructive_triggers_confirm(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """LLM calling !node.merge returns confirm_tool."""
        self._make_nodes(SRC_A="Source A", TGT_A="Target A")
        _mock_chat_with_tools(monkeypatch, [
            ChatResult(tool_calls=[
                ToolCall(
                    id="call_d1",
                    function={"name": "node_merge", "arguments": '{"source": "SRC_A", "target": "TGT_A", "force": "true"}'},
                ),
            ]),
        ])

        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "merge-nodes", "args": ["SRC_A", "TGT_A"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "confirm_tool"
        assert "session_id" in data
        assert data["batch"][0]["tokens"] == ["node", "merge"]
        assert "Review and approve" in data["message"]
        assert "batch" in data
        assert len(data["batch"]) == 1

    def test_write_triggers_confirm(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """LLM calling !node.add (WRITE-level) returns confirm_tool."""
        _mock_chat_with_tools(monkeypatch, [
            ChatResult(tool_calls=[
                ToolCall(
                    id="call_w1",
                    function={"name": "node_add", "arguments": '{"labels": "WriteTest"}'},
                ),
            ]),
        ])

        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "merge-nodes", "args": ["WriteTest"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "confirm_tool"
        assert "session_id" in data
        assert data["batch"][0]["tokens"] == ["node", "add"]

    def test_confirm_and_resume(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """After user approves, the destructive tool executes."""
        self._make_nodes(SRC_B="Source B", TGT_B="Target B")
        _mock_chat_with_tools(monkeypatch, [
            ChatResult(tool_calls=[
                ToolCall(
                    id="call_d1",
                    function={"name": "node_merge", "arguments": '{"source": "SRC_B", "target": "TGT_B", "force": "true"}'},
                ),
            ]),
            ChatResult(content="Nodes merged successfully."),
        ])

        # First request triggers confirmation
        resp1 = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "merge-nodes", "args": ["SRC_B", "TGT_B"]},
        )
        assert resp1.status_code == 200
        confirm = resp1.json()
        assert confirm["type"] == "confirm_tool"
        session_id = confirm["session_id"]

        # Second request resumes with approval → merge happens
        resp2 = client.post(
            "/api/v1/prompt-commands/execute/resume",
            json={"session_id": session_id, "confirmed": True},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["type"] == "chat"

    def test_reject_and_resume(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """After user rejects, the destructive tool is not executed."""
        self._make_nodes(SRC_C="Source C", TGT_C="Target C")
        _mock_chat_with_tools(monkeypatch, [
            ChatResult(tool_calls=[
                ToolCall(
                    id="call_d1",
                    function={"name": "node_merge", "arguments": '{"source": "SRC_C", "target": "TGT_C", "force": "true"}'},
                ),
            ]),
            ChatResult(content="Merge cancelled by user."),
        ])

        resp1 = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "merge-nodes", "args": ["SRC_C", "TGT_C"]},
        )
        assert resp1.status_code == 200
        confirm = resp1.json()
        assert confirm["type"] == "confirm_tool"
        session_id = confirm["session_id"]

        # Resume with rejection
        resp2 = client.post(
            "/api/v1/prompt-commands/execute/resume",
            json={"session_id": session_id, "confirmed": False},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["type"] == "chat"

        # Verify SRC_C still exists (merge did NOT happen)
        from semantika.graph.db import get_services
        svc = get_services()
        assert svc["node"].get("SRC_C") is not None

    def test_resume_invalid_session(self, client: TestClient):
        """Unknown session_id returns 404."""
        resp = client.post(
            "/api/v1/prompt-commands/execute/resume",
            json={"session_id": "nonexistent", "confirmed": True},
        )
        assert resp.status_code == 404

    def test_multiple_tool_calls_in_batch(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Multiple non-destructive tool calls in one batch are all dispatched."""
        _mock_chat_with_tools(monkeypatch, [
            ChatResult(tool_calls=[
                ToolCall(
                    id="call_m1",
                    function={"name": "graph_stats", "arguments": "{}"},
                ),
                ToolCall(
                    id="call_m2",
                    function={"name": "node_search", "arguments": '{"q": "test"}'},
                ),
            ]),
            ChatResult(content="Here are the stats and search results."),
        ])

        resp = client.post(
            "/api/v1/prompt-commands/execute",
            json={"name": "merge-nodes", "args": ["test"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "chat"
