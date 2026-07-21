"""Tests for the LLM provider — config persistence, profile management, chat."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from lightercore.exceptions import AIError
from lighterllm.llm import ProviderConfig
from lighterllm.llm.utils import parse_command_result
from semantika.server.command.registry import get_command_definitions
from semantika.server.llm.provider import LLMProvider, get_provider, reset_provider


# ── Fixtures ─────────────────────────────────────────────────────────────


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

    return store


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset the provider singleton before each test."""
    reset_provider()


@pytest.fixture
def provider(mock_keyring: dict) -> LLMProvider:
    """Freshly-created provider with no config."""
    return LLMProvider()


# ── ProviderConfig tests ─────────────────────────────────────────────────


class TestProviderConfig:
    def test_defaults(self):
        cfg = ProviderConfig()
        assert cfg.provider_type == ""  # unopinionated in core
        assert cfg.api_key == ""
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 2048

    def test_provider_defaults_to_deepseek(self):
        """LLMProvider creates a config defaulting to deepseek."""
        p = LLMProvider()
        assert p.config.provider_type == "deepseek"

    def test_custom_values(self):
        cfg = ProviderConfig(
            provider_type="custom",
            base_url="http://localhost:8080/v1",
            model="my-model",
        )
        assert cfg.base_url == "http://localhost:8080/v1"
        assert cfg.model == "my-model"
        assert cfg.api_key == ""

    def test_to_dict_and_from_dict_roundtrip(self):
        cfg = ProviderConfig(provider_type="deepseek", api_key="sk-ds", model="deepseek-chat")
        data = cfg.to_dict()
        restored = ProviderConfig.from_dict(data)
        assert restored.provider_type == "deepseek"
        assert restored.api_key == "sk-ds"
        assert restored.model == "deepseek-chat"


# ── Configuration persistence ────────────────────────────────────────────


class TestConfigure:
    def test_configure_saves_to_keyring(self, provider: LLMProvider, mock_keyring: dict):
        provider.configure("openai", api_key="sk-test123")
        stored = json.loads(mock_keyring.get("semantika-llm:active-config", "{}"))
        assert stored["provider_type"] == "openai"
        assert stored["api_key"] == "sk-test123"

    def test_configure_makes_available(self, provider: LLMProvider):
        provider.configure("openai", api_key="sk-test")
        assert provider.available is True

    def test_configure_ollama_no_key(self, provider: LLMProvider):
        provider.configure("ollama")
        assert provider.available is True  # Ollama doesn't need API key

    def test_default_not_available(self, provider: LLMProvider):
        assert provider.available is False  # No key, not ollama

    def test_clear_config(self, provider: LLMProvider, mock_keyring: dict):
        provider.configure("openai", api_key="sk-test")
        provider.clear_config()
        assert provider.available is False
        assert mock_keyring.get("semantika-llm:active-config") is None

    def test_config_roundtrip(self, provider: LLMProvider):
        provider.configure("deepseek", api_key="sk-ds", model="deepseek-v4")
        # Create a new provider — it should load the saved config
        provider2 = LLMProvider()
        assert provider2.config.provider_type == "deepseek"
        assert provider2.config.api_key == "sk-ds"
        assert provider2.config.model == "deepseek-v4"


# ── Profile management ───────────────────────────────────────────────────


class TestProfiles:
    def test_save_and_list_profile(self, provider: LLMProvider):
        provider.save_profile("test-profile", "openai", api_key="sk-test")
        profiles = provider.list_profiles()
        assert any(p["name"] == "test-profile" for p in profiles)

    def test_list_profiles_hides_api_key(self, provider: LLMProvider):
        provider.save_profile("secret", "openai", api_key="sk-hidden")
        profiles = provider.list_profiles()
        for p in profiles:
            if p["name"] == "secret":
                assert p["has_api_key"] is True

    def test_get_profile_includes_key(self, provider: LLMProvider):
        provider.save_profile("test", "openai", api_key="sk-mykey")
        profile = provider.get_profile("test")
        assert profile is not None
        assert profile["api_key"] == "sk-mykey"

    def test_get_nonexistent_profile(self, provider: LLMProvider):
        assert provider.get_profile("nonexistent") is None

    def test_delete_profile(self, provider: LLMProvider):
        provider.save_profile("delete-me", "openai", api_key="sk-del")
        assert provider.delete_profile("delete-me") is True
        assert provider.get_profile("delete-me") is None

    def test_delete_nonexistent_profile(self, provider: LLMProvider):
        assert provider.delete_profile("nonexistent") is False

    def test_switch_to_profile(self, provider: LLMProvider):
        provider.save_profile("work", "openai", api_key="sk-work", model="gpt-4o")
        result = provider.switch_to_profile("work")
        assert result is not None
        assert result.provider_type == "openai"
        assert result.api_key == "sk-work"
        assert provider.active_profile_name == "work"

    def test_switch_to_nonexistent(self, provider: LLMProvider):
        assert provider.switch_to_profile("nope") is None

    def test_list_empty(self, provider: LLMProvider):
        assert provider.list_profiles() == []


# ── Chat tests (mocked HTTP) ─────────────────────────────────────────────


class TestChat:
    async def test_chat_not_available(self, provider: LLMProvider):
        with pytest.raises(AIError, match="not configured"):
            await provider.chat([{"role": "user", "content": "hi"}])

    async def test_chat_success(self, provider: LLMProvider):
        provider.configure("openai", api_key="sk-test")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}]
        }

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
            reply = await provider.chat([{"role": "user", "content": "hi"}])
            assert reply == "Hello!"

    async def test_chat_empty_choices_raises(self, provider: LLMProvider):
        provider.configure("openai", api_key="sk-test")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {"choices": []}

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
            with pytest.raises(AIError, match="No response"):
                await provider.chat([{"role": "user", "content": "hi"}])

    async def test_chat_api_error_raises(self, provider: LLMProvider):
        provider.configure("openai", api_key="sk-test")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = True
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Unauthorized"}}

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
            with pytest.raises(AIError, match="LLM API error"):
                await provider.chat([{"role": "user", "content": "hi"}])

    async def test_chat_timeout_raises(self, provider: LLMProvider):
        provider.configure("openai", api_key="sk-test")

        with patch(
            "httpx.AsyncClient.post",
            new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
        ):
            with pytest.raises(httpx.TimeoutException):
                await provider.chat([{"role": "user", "content": "hi"}])

    async def test_chat_generic_error_raises(self, provider: LLMProvider):
        provider.configure("openai", api_key="sk-test")

        with patch(
            "httpx.AsyncClient.post",
            new=AsyncMock(side_effect=RuntimeError("network error")),
        ):
            with pytest.raises(RuntimeError, match="network error"):
                await provider.chat([{"role": "user", "content": "hi"}])


# ── Command generation ───────────────────────────────────────────────────


class TestGenerateCommand:
    async def test_generates_command(self, provider: LLMProvider):
        provider.configure("openai", api_key="sk-test")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"tokens": ["node", "list"], "flags": {}}'}}]
        }

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
            result = await provider.generate_command("list all nodes", [])
            assert result is not None
            assert result["tokens"] == ["node", "list"]

    async def test_generate_no_llm(self, provider: LLMProvider):
        result = await provider.generate_command("list nodes", [])
        assert result is None

    async def test_generate_ai_error_returns_none(self, provider: LLMProvider):
        provider.configure("openai", api_key="sk-test")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = True
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": {"message": "Rate limited"}}

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
            result = await provider.generate_command("list nodes", [])
            assert result is None


# ── Command result parser ────────────────────────────────────────────────


class TestParseCommandResult:
    """Tests for parse_command_result from lightercore.utils."""

    def test_parse_json(self):
        result = parse_command_result('{"tokens": ["node", "list"], "flags": {}}')
        assert result == {"tokens": ["node", "list"], "flags": {}}

    def test_parse_markdown_fenced(self):
        result = parse_command_result(
            '```json\n{"tokens": ["node", "add"], "flags": {"labels": "Dog"}}\n```'
        )
        assert result is not None
        assert result["tokens"] == ["node", "add"]

    def test_parse_plain_text_command(self):
        result = parse_command_result("Run !node list for me")
        assert result is not None
        assert result["tokens"][:2] == ["node", "list"]

    def test_parse_empty(self):
        assert parse_command_result("") is None
        assert parse_command_result(None) is None  # type: ignore[arg-type]

    def test_parse_invalid_json_without_command(self):
        assert parse_command_result("some random text") is None

    def test_parse_missing_tokens_key(self):
        assert parse_command_result('{"something": "else"}') is None

    def test_parse_markdown_fenced_with_lang(self):
        result = parse_command_result(
            '```\n{"tokens": ["predicate", "list"]}\n```'
        )
        assert result is not None
        assert result["tokens"] == ["predicate", "list"]


# ── Singleton tests ──────────────────────────────────────────────────────


class TestSingleton:
    def test_get_provider_returns_same_instance(self):
        p1 = get_provider()
        p2 = get_provider()
        assert p1 is p2

    def test_reset_provider_creates_new_instance(self):
        p1 = get_provider()
        reset_provider()
        p2 = get_provider()
        assert p1 is not p2


# ── Command definitions helper ───────────────────────────────────────────


class TestGetCommandDefinitions:
    def test_flatten_tree(self):
        tree = [
            {
                "name": "node",
                "description": "Manage nodes",
                "children": [
                    {
                        "name": "list",
                        "description": "List all nodes",
                        "params": [{"name": "limit", "type": "number", "default": 100}],
                    },
                    {
                        "name": "add",
                        "description": "Add a node",
                        "interactive": True,
                        "params": [{"name": "labels", "type": "string"}],
                        "flags": [{"name": "definitions", "type": "string"}],
                    },
                ],
            }
        ]
        defs = get_command_definitions(tree)
        # Bare group node "node" (no handler, only children) is correctly
        # excluded — only leaf commands appear in the flattened list.
        assert len(defs) == 2
        by_path = {tuple(d["path"]): d for d in defs}
        assert ("node", "list") in by_path
        assert ("node", "add") in by_path
        assert "flags" in by_path[("node", "add")]
        assert len(by_path[("node", "add")]["flags"]) == 1

    def test_empty_tree(self):
        assert get_command_definitions([]) == []

    def test_node_without_children(self):
        tree = [{"name": "help", "description": "Show help"}]
        defs = get_command_definitions(tree)
        assert len(defs) == 1
        assert defs[0]["canonical"] == "!help"
