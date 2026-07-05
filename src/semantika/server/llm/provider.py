"""LLM provider for Semantika — backed by lightercore shared infrastructure.

Port of lighterbird's singleton + wrapper pattern.  Config and named
profiles are persisted in the system keyring via lightercore modules.

Three-phase command flow:
1. Generate structured command from natural language.
2. Permission check (gate destructive commands behind user confirm).
3. Execute and summarise.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from lightercore.exceptions import AIError
from lightercore.llm import BaseLLMProvider, ProfileManager, ProviderConfig
from lightercore.llm.config import (
    clear_active_config as _clear_active,
    load_active_config as _load_active,
    save_active_config as _save_active,
)

logger = logging.getLogger(__name__)

_SERVICE_NAME = "semantika-llm"

# ── Command definitions ───────────────────────────────────────────────────


def _flatten_tree(tree: list[dict]) -> list[dict]:
    """Walk the command tree and produce a flat list for the LLM prompt.

    Each item includes the full dot-path, description, params, and flags.
    """
    result: list[dict] = []

    def _walk(children: list[dict], parent_path: list[str] | None = None) -> None:
        for entry in children:
            path: list[str] = list(parent_path or []) + [entry["name"]]
            item: dict[str, Any] = {
                "path": path,
                "canonical": "!" + ".".join(path),
                "description": entry.get("description", ""),
                "params": entry.get("params", []),
                "flags": entry.get("flags", []),
            }
            result.append(item)
            sub = entry.get("children")
            if sub:
                _walk(sub, path)

    _walk(tree)
    return result


# ── Provider class ────────────────────────────────────────────────────────


class LLMProvider(BaseLLMProvider):
    """Semantika's LLM provider with config/profile management.

    This is a **singleton** — use :func:`get_provider` instead of
    constructing directly.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        if config is None:
            config = _load_active(_SERVICE_NAME) or ProviderConfig(
                provider_type="deepseek",
            )
        super().__init__(config)
        self._active_profile_name: str | None = None

    # ── Hooks ────────────────────────────────────────────────────────────

    def _default_model(self) -> str:
        """Deepseek defaults for Semantika."""
        defaults = {
            "openai": "gpt-4o",
            "deepseek": "deepseek-chat",
            "ollama": "llama3.2",
        }
        return defaults.get(self.config.provider_type, "gpt-4o")

    def _command_system_prompt(self, defs_text: str) -> str:
        return (
            "You are a command parser for the Semantika knowledge graph. "
            "The user speaks to you in natural language. Your job is to "
            "translate their request into a structured command.\n\n"
            "Respond with ONLY a valid JSON object — no markdown, no explanation, "
            "no extra text. The JSON must match this schema:\n"
            '{"tokens": ["command", "subcommand", ...], "flags": {"name": "value"}}\n\n'
            "Flags correspond to command parameters. Use the param names from "
            "the command definitions below.\n\n"
            "If the user's request does NOT map to any available command, "
            "respond with an empty JSON object: {}\n\n"
            "Available commands (machine-readable):\n" + defs_text
        )

    # ── Active config persistence ────────────────────────────────────────

    @property
    def available(self) -> bool:
        """Check whether the provider has valid credentials configured."""
        return self.config.is_available()

    def configure(self, provider_type: str, **kwargs: Any) -> ProviderConfig:
        """Save active provider configuration to keyring.

        Args:
            provider_type: ``"openai"``, ``"deepseek"``, ``"ollama"``, etc.
            **kwargs: ``api_key``, ``base_url``, ``model``, ``temperature``,
                      ``max_tokens``.
        """
        config = ProviderConfig(
            provider_type=provider_type,
            api_key=kwargs.get("api_key", ""),
            base_url=kwargs.get("base_url", ""),
            model=kwargs.get("model", ""),
            temperature=float(kwargs.get("temperature", 0.7)),
            max_tokens=int(kwargs.get("max_tokens", 2048)),
        )
        _save_active(_SERVICE_NAME, config)
        # Re-initialise with the new config
        self.config = config
        self.base_url = config.base_url or self._default_base_url(config.provider_type)
        self.model = config.model or self._default_model()
        self._active_profile_name = None
        return self.config

    @staticmethod
    def _default_base_url(provider_type: str) -> str:
        from lightercore.llm.utils import resolve_base_url
        return resolve_base_url(provider_type, "")

    def clear_config(self) -> None:
        """Remove active provider configuration from keyring."""
        _clear_active(_SERVICE_NAME)
        self.config = ProviderConfig()
        self.base_url = ""
        self.model = self._default_model()
        self._active_profile_name = None

    # ── Profile management (delegated to ProfileManager) ─────────────────

    @property
    def profiles(self) -> ProfileManager:
        """Return a ProfileManager instance for this service."""
        return ProfileManager(_SERVICE_NAME)

    @property
    def active_profile_name(self) -> str | None:
        return self._active_profile_name

    def save_profile(self, name: str, provider_type: str, **kwargs: Any) -> dict:
        """Save a named LLM profile to keyring."""
        config = ProviderConfig(
            provider_type=provider_type,
            api_key=kwargs.get("api_key", ""),
            base_url=kwargs.get("base_url", ""),
            model=kwargs.get("model", ""),
            temperature=float(kwargs.get("temperature", 0.7)),
            max_tokens=int(kwargs.get("max_tokens", 2048)),
        )
        self.profiles.save(name, config)
        return config.to_dict()

    def list_profiles(self) -> list[dict]:
        """List saved profiles (without API keys)."""
        return self.profiles.list()

    def get_profile(self, name: str) -> dict | None:
        """Get a single profile config (with API key) or None."""
        cfg = self.profiles.get(name)
        if cfg is None:
            return None
        return cfg.to_dict()

    def delete_profile(self, name: str) -> bool:
        """Delete a named profile. Returns True if deleted."""
        return self.profiles.delete(name)

    def switch_to_profile(self, name: str) -> ProviderConfig | None:
        """Activate a saved profile. Returns the config or None."""
        config = self.profiles.switch_to(name)
        if config is None:
            return None
        self.config = config
        self.base_url = config.base_url or self._default_base_url(config.provider_type)
        self.model = config.model or self._default_model()
        self._active_profile_name = name
        return config

    # ── Command helpers ──────────────────────────────────────────────────

    def get_command_definitions(self, tree: list[dict]) -> list[dict]:
        """Flatten command tree for LLM consumption."""
        return _flatten_tree(tree)


# ── Singleton ──────────────────────────────────────────────────────────────


_provider_instance: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Return the singleton LLM provider (lazy-loaded from keyring)."""
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance
    _provider_instance = LLMProvider()
    return _provider_instance


def reset_provider() -> None:
    """Force provider re-initialisation on next access."""
    global _provider_instance
    _provider_instance = None


__all__ = [
    "LLMProvider",
    "ProviderConfig",  # re-exported for backward compat
    "get_provider",
    "reset_provider",
]
