"""Tests for LLM tool registry — registration, dispatch, permission, and domain tools.

Covers:
- ``@llm_tool`` decorator and registry queries
- ``dispatch_llm_tool()`` success / unknown / error paths
- ``get_llm_tool_level()`` and ``get_llm_tool_metadata()``
- Each domain tool with a mocked/in-memory service layer
- Chat endpoint verifies LLM tools are used
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from lightercore.permissions import PermissionLevel

from semantika.server.app import create_app

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_keyring(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replace system keyring with an in-memory dict."""
    store: dict[str, str] = {}

    def set_pw(service: str, key: str, value: str) -> None:
        store[f"{service}:{key}"] = value

    def get_pw(service: str, key: str) -> str | None:
        return store.get(f"{service}:{key}")

    def del_pw(service: str, key: str) -> None:
        store.pop(f"{service}:{key}", None)

    import keyring as _kr
    monkeypatch.setattr(_kr, "set_password", set_pw)
    monkeypatch.setattr(_kr, "get_password", get_pw)
    monkeypatch.setattr(_kr, "delete_password", del_pw)

    from semantika.server.llm.provider import reset_provider
    reset_provider()
    return store


# ── Tools we test —─────────────────────────────────────────────────────────


from semantika.server.llm.tools import (  # noqa: E402
    _llm_registry,
    dispatch_llm_tool,
    get_llm_tool_level,
    get_llm_tool_metadata,
    get_llm_tool_names,
    get_llm_tools,
    is_llm_tool,
    llm_tool,
)


def _clean_registry() -> None:
    """Remove any test helpers from the shared registry."""
    for key in list(_llm_registry.keys()):
        if key.startswith("_test."):
            _llm_registry.pop(key, None)


@pytest.fixture(autouse=True)
def _auto_clean_test_tools() -> None:
    """Clean up any _test.* tools after each test method."""
    yield
    _clean_registry()


@contextmanager
def _with_test_tool():
    """Register a ``_test.hello`` tool and clean it up after the block."""
    @llm_tool(
        name="_test.hello",
        description="A test tool",
        params=[{"name": "name", "type": "string", "description": "Your name", "required": True}],
        permission_level=PermissionLevel.READ,
    )
    def _handler(name: str = "", **kwargs) -> dict:
        return {"success": True, "data": {"greeting": f"Hello, {name}!"}}

    try:
        yield
    finally:
        _llm_registry.pop("_test.hello", None)


# ── Registry tests ─────────────────────────────────────────────────────────


class TestToolRegistry:
    """Test the @llm_tool decorator and registry infrastructure."""

    def test_decorator_registers(self) -> None:
        with _with_test_tool():
            assert is_llm_tool("_test.hello")

    def test_get_llm_tools_format(self) -> None:
        with _with_test_tool():
            tools = get_llm_tools()
            names = [t["function"]["name"] for t in tools]
            assert "_test_hello" in names
            fn = next(t["function"] for t in tools if t["function"]["name"] == "_test_hello")
            assert "description" in fn
            assert "parameters" in fn
            assert fn["parameters"]["type"] == "object"

    def test_dispatch_success(self) -> None:
        with _with_test_tool():
            result = dispatch_llm_tool("_test.hello", {"name": "Alice"})
            assert result["success"] is True
            assert result["data"]["greeting"] == "Hello, Alice!"

    def test_dispatch_unknown(self) -> None:
        result = dispatch_llm_tool("nonexistent.tool", {})
        assert result["success"] is False
        assert "Unknown" in result["error"]

    def test_get_llm_tool_level(self) -> None:
        with _with_test_tool():
            level = get_llm_tool_level("_test.hello")
            assert level == PermissionLevel.READ

    def test_get_llm_tool_level_unknown(self) -> None:
        assert get_llm_tool_level("nonexistent") is None

    def test_get_llm_tool_metadata(self) -> None:
        with _with_test_tool():
            meta = get_llm_tool_metadata("_test.hello")
            assert meta is not None
            assert meta["description"] == "A test tool"

    def test_get_llm_tool_metadata_unknown(self) -> None:
        assert get_llm_tool_metadata("nonexistent") is None

    def test_get_llm_tool_names_includes_test(self) -> None:
        with _with_test_tool():
            names = get_llm_tool_names()
            assert "_test.hello" in names

    def test_is_llm_tool(self) -> None:
        with _with_test_tool():
            assert is_llm_tool("_test.hello")
            assert not is_llm_tool("nonexistent")

    def test_is_llm_tool_empty(self) -> None:
        assert not is_llm_tool("")

    def test_dispatch_handler_exception(self) -> None:
        """Handler that throws an exception should return error dict."""

        @llm_tool(name="_test.error", description="Always fails")
        def _fail(**kwargs) -> dict:
            raise RuntimeError("boom")

        try:
            result = dispatch_llm_tool("_test.error", {})
            assert result["success"] is False
            assert "boom" in result["error"]
        finally:
            _llm_registry.pop("_test.error", None)


# ── system.now tool ────────────────────────────────────────────────────────


class TestSystemNow:
    """Test the system.now tool."""

    def test_system_now_returns_datetime(self) -> None:
        result = dispatch_llm_tool("system.now", {})
        assert result["success"] is True
        data = result["data"]
        assert "datetime" in data
        assert "date" in data
        assert "weekday" in data


# ── graph.stats tool ────────────────────────────────────────────────────────


class TestGraphStats:
    """Test the graph.stats tool with mocked services."""

    @patch("semantika.server.llm.tools.graph.get_services")
    @patch("semantika.server.llm.tools.graph.get_sparql_engine")
    def test_graph_stats_with_sparql(self, mock_engine: MagicMock, mock_get_svc: MagicMock) -> None:
        mock_engine.return_value = MagicMock()
        node_svc = MagicMock()
        node_svc.count.return_value = 42
        pred_svc = MagicMock()
        pred_svc.count.return_value = 15
        triple_svc = MagicMock()
        triple_svc.count.return_value = 237
        mock_get_svc.return_value = {"node": node_svc, "predicate": pred_svc, "triple": triple_svc}

        result = dispatch_llm_tool("graph.stats", {})
        assert result["success"] is True
        data = result["data"]
        assert data["nodes"] == 42
        assert data["predicates"] == 15
        assert data["triples"] == 237
        assert data["sparql_available"] is True

    @patch("semantika.server.llm.tools.graph.get_services")
    def test_graph_stats_no_sparql(self, mock_get_svc: MagicMock) -> None:
        node_svc = MagicMock()
        node_svc.count.return_value = 5
        mock_get_svc.return_value = {"node": node_svc}

        result = dispatch_llm_tool("graph.stats", {})
        assert result["success"] is True
        assert result["data"]["sparql_available"] is False


# ── node.* tools ────────────────────────────────────────────────────────────


class TestNodeTools:
    """Test node tools with mocked NodeService."""

    @patch("semantika.server.llm.tools.node.get_services")
    def test_node_search(self, mock_get_svc: MagicMock) -> None:
        node_svc = MagicMock()
        node_svc.search.return_value = [
            {"node_id": "ALICE", "labels": '{"en":"Alice"}', "label_text": "Alice"},
        ]
        mock_get_svc.return_value = {"node": node_svc}

        result = dispatch_llm_tool("node.search", {"q": "Alice", "limit": 10})
        assert result["success"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["node_id"] == "ALICE"

    @patch("semantika.server.llm.tools.node.get_services")
    def test_node_view_found(self, mock_get_svc: MagicMock) -> None:
        node_svc = MagicMock()
        node_svc.get.return_value = {"node_id": "ALICE", "labels": '{"en":"Alice"}'}
        triple_svc = MagicMock()
        triple_svc.search.side_effect = lambda **kw: []
        mock_get_svc.return_value = {"node": node_svc, "triple": triple_svc}

        result = dispatch_llm_tool("node.view", {"id": "ALICE"})
        assert result["success"] is True
        assert result["data"]["node_id"] == "ALICE"

    @patch("semantika.server.llm.tools.node.get_services")
    def test_node_view_not_found(self, mock_get_svc: MagicMock) -> None:
        node_svc = MagicMock()
        node_svc.get.return_value = None
        mock_get_svc.return_value = {"node": node_svc}

        result = dispatch_llm_tool("node.view", {"id": "NONEXISTENT"})
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("semantika.server.llm.tools.node.get_services")
    def test_node_create(self, mock_get_svc: MagicMock) -> None:
        node_svc = MagicMock()
        node_svc.create.return_value = {"node_id": "ALICE", "labels": '{"en":"Alice"}'}
        mock_get_svc.return_value = {"node": node_svc}

        result = dispatch_llm_tool("node.create", {
            "type": "concept",
            "labels": '{"en":"Alice","fr":"Alice"}',
        })
        assert result["success"] is True
        assert result["data"]["node_id"] == "ALICE"

    @patch("semantika.server.llm.tools.node.get_services")
    def test_node_create_missing_type(self, mock_get_svc: MagicMock) -> None:
        result = dispatch_llm_tool("node.create", {})
        assert result["success"] is False
        assert "type is required" in result["error"]

    @patch("semantika.server.llm.tools.node.get_services")
    def test_node_delete(self, mock_get_svc: MagicMock) -> None:
        node_svc = MagicMock()
        node_svc.delete.return_value = True
        mock_get_svc.return_value = {"node": node_svc}

        result = dispatch_llm_tool("node.delete", {"id": "ALICE"})
        assert result["success"] is True
        assert result["data"]["deleted"] == "ALICE"

    @patch("semantika.server.llm.tools.node.get_services")
    def test_node_delete_not_found(self, mock_get_svc: MagicMock) -> None:
        node_svc = MagicMock()
        node_svc.delete.return_value = False
        mock_get_svc.return_value = {"node": node_svc}

        result = dispatch_llm_tool("node.delete", {"id": "NONEXISTENT"})
        assert result["success"] is False


# ── predicate.* tools ────────────────────────────────────────────────────────


class TestPredicateTools:
    """Test predicate tools with mocked PredicateService."""

    @patch("semantika.server.llm.tools.predicate.get_services")
    def test_predicate_search(self, mock_get_svc: MagicMock) -> None:
        pred_svc = MagicMock()
        pred_svc.search.return_value = [
            {"predicate_id": "rdf:type", "labels": '{"en":"type"}', "descriptions": '{}'},
        ]
        mock_get_svc.return_value = {"predicate": pred_svc}

        result = dispatch_llm_tool("predicate.search", {"q": "type"})
        assert result["success"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["predicate_id"] == "rdf:type"

    @patch("semantika.server.llm.tools.predicate.get_services")
    def test_predicate_view(self, mock_get_svc: MagicMock) -> None:
        pred_svc = MagicMock()
        pred_svc.get.return_value = {"predicate_id": "sm:depicts", "labels": '{"en":"depicts"}'}
        mock_get_svc.return_value = {"predicate": pred_svc}

        result = dispatch_llm_tool("predicate.view", {"id": "sm:depicts"})
        assert result["success"] is True
        assert result["data"]["predicate_id"] == "sm:depicts"


# ── triple.* tools ──────────────────────────────────────────────────────────


class TestTripleTools:
    """Test triple tools with mocked TripleService."""

    @patch("semantika.server.llm.tools.triple.get_services")
    def test_triple_search_by_subject(self, mock_get_svc: MagicMock) -> None:
        triple_svc = MagicMock()
        triple_svc.get_by_subject.return_value = [
            {"subject_id": "ALICE", "predicate_id": "rdf:type", "object_value": "Person"},
        ]
        mock_get_svc.return_value = {"triple": triple_svc}

        result = dispatch_llm_tool("triple.search", {"subject": "ALICE"})
        assert result["success"] is True
        assert len(result["data"]) == 1

    @patch("semantika.server.llm.tools.triple.get_services")
    def test_triple_search_no_params(self, mock_get_svc: MagicMock) -> None:
        result = dispatch_llm_tool("triple.search", {})
        assert result["success"] is False
        assert "required" in result["error"]

    @patch("semantika.server.llm.tools.triple.get_services")
    def test_triple_add_single(self, mock_get_svc: MagicMock) -> None:
        triple_svc = MagicMock()
        mock_get_svc.return_value = {"triple": triple_svc}

        result = dispatch_llm_tool("triple.add", {
            "subject": "ALICE",
            "predicate": "rdf:type",
            "object": "Person",
        })
        assert result["success"] is True
        assert result["data"]["added"] == 1

    @patch("semantika.server.llm.tools.triple.get_services")
    def test_triple_delete(self, mock_get_svc: MagicMock) -> None:
        triple_svc = MagicMock()
        triple_svc.remove.return_value = 3
        mock_get_svc.return_value = {"triple": triple_svc}

        result = dispatch_llm_tool("triple.delete", {"subject": "ALICE"})
        assert result["success"] is True
        assert result["data"]["removed"] == 3


# ── search.fts tool ─────────────────────────────────────────────────────────


class TestSearchFts:
    """Test the cross-domain search.fts tool."""

    @patch("semantika.server.llm.tools.search.get_services")
    def test_search_fts(self, mock_get_svc: MagicMock) -> None:
        node_svc = MagicMock()
        node_svc.search.return_value = [{"node_id": "ALICE", "label_text": "Alice"}]
        pred_svc = MagicMock()
        pred_svc.search.return_value = []
        mock_get_svc.return_value = {"node": node_svc, "predicate": pred_svc}

        result = dispatch_llm_tool("search.fts", {"q": "Alice", "limit": 5})
        assert result["success"] is True
        assert len(result["data"]["nodes"]) == 1
        assert len(result["data"]["predicates"]) == 0


# ── Permission level tests ─────────────────────────────────────────────────


class TestToolPermission:
    """Test that LLM tools report correct permission levels."""

    def test_read_tools_are_read(self) -> None:
        read_tools = (
            "system.now", "node.search", "node.view",
            "predicate.search", "predicate.view",
            "triple.search",
            "search.fts", "graph.stats",
            "template.list", "template.view",
            "sparql.query", "sparql.status",
            "review.status",
            "unit.search", "unit.info",
        )
        for name in read_tools:
            level = get_llm_tool_level(name)
            assert level == PermissionLevel.READ, f"{name} should be READ (got {level})"

    def test_write_tools_are_write(self) -> None:
        write_tools = (
            "node.create", "node.update", "node.delete",
            "predicate.create",
            "triple.add", "triple.delete",
            "template.apply",
        )
        for name in write_tools:
            level = get_llm_tool_level(name)
            assert level == PermissionLevel.WRITE, f"{name} should be WRITE (got {level})"

    def test_all_tools_have_permission(self) -> None:
        """Every registered tool must have a permission level."""
        names = get_llm_tool_names()
        assert len(names) > 0
        for name in names:
            level = get_llm_tool_level(name)
            assert level is not None, f"{name} has no permission level"


# ── Chat endpoint uses LLM tools ──────────────────────────────────────────


class TestChatEndpointUsesLLMTools:
    """Verify the chat endpoint uses dedicated LLM tools (not CLI defs)."""

    def test_chat_no_provider_uses_stub(self, client: TestClient) -> None:
        """Without an LLM provider, the stub response should mention commands."""
        resp = client.post("/api/v1/llm/chat", json={"message": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data

    def test_chat_calls_get_llm_tools(self, client: TestClient) -> None:
        """Verify the chat endpoint calls get_llm_tools() not get_command_definitions()."""
        # Configure a provider so it doesn't hit the stub path
        client.post("/api/v1/llm/configure", json={
            "provider_type": "deepseek",
            "api_key": "test-key",
            "model": "deepseek-chat",
        })

        with patch("semantika.server.routes.llm.get_llm_tools") as mock_get_tools, \
             patch("semantika.server.routes.llm.run_tool_loop") as mock_run:
            mock_get_tools.return_value = [{"type": "function", "function": {"name": "test_tool"}}]
            mock_run.return_value = "Hello from LLM!"

            resp = client.post("/api/v1/llm/chat", json={"message": "hi"})
            assert resp.status_code == 200
            mock_get_tools.assert_called_once()
            _, kwargs = mock_run.call_args
            assert kwargs["tools"] == mock_get_tools.return_value

    def test_chat_passes_dispatch_llm_tool(self, client: TestClient) -> None:
        """Verify the chat endpoint passes dispatch_llm_tool (not CLI dispatch)."""
        from semantika.server.llm.tools import dispatch_llm_tool as _dispatch

        client.post("/api/v1/llm/configure", json={
            "provider_type": "deepseek",
            "api_key": "test-key",
            "model": "deepseek-chat",
        })

        with patch("semantika.server.routes.llm.get_llm_tools") as mock_get_tools, \
             patch("semantika.server.routes.llm.run_tool_loop") as mock_run:
            mock_get_tools.return_value = []
            mock_run.return_value = "Hello!"
            resp = client.post("/api/v1/llm/chat", json={"message": "hi"})
            assert resp.status_code == 200
            _, kwargs = mock_run.call_args
            assert kwargs["dispatch_fn"] is _dispatch


# ── registration integrity ────────────────────────────────────────────────


class TestToolRegistrationIntegrity:
    """Verify all expected tools are registered."""

    def test_expected_tools_exist(self) -> None:
        names = get_llm_tool_names()
        expected = {
            "system.now",
            "graph.stats",
            "node.search", "node.view", "node.create", "node.update", "node.delete",
            "predicate.search", "predicate.view", "predicate.create",
            "triple.search", "triple.add", "triple.delete",
            "template.list", "template.view", "template.apply",
            "search.fts",
            "sparql.query", "sparql.status",
            "review.status",
            "unit.search", "unit.info",
        }
        missing = expected - set(names)
        extra = set(names) - expected
        assert not missing, f"Expected tools missing: {missing}"
        assert not extra, f"Unexpected tools registered: {extra}"
