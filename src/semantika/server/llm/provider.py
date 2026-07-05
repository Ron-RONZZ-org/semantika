"""LLM provider abstraction — OpenAI-compatible + Ollama.

Port of lighterbird's provider pattern: text-based command generation
via system prompt (no native function-calling), plus plain chat, and
profile management persisted in the system keyring.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
import keyring as _kr
import keyring.errors as _kr_errors

logger = logging.getLogger(__name__)


# ── Config ───────────────────────────────────────────────────────────────

_KEYRING_SERVICE = "semantika-llm"
_ACTIVE_CONFIG_KEY = "active-config"
_PROFILES_KEY = "saved-profiles"

_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "ollama": "http://localhost:11434/v1",
}


def _set_kr(key: str, value: str) -> None:
    try:
        _kr.set_password(_KEYRING_SERVICE, key, value)
    except _kr_errors.KeyringError as e:
        logger.warning("Keyring write failed: %s", e)


def _get_kr(key: str) -> str | None:
    try:
        return _kr.get_password(_KEYRING_SERVICE, key)
    except _kr_errors.KeyringError:
        return None


def _del_kr(key: str) -> None:
    try:
        _kr.delete_password(_KEYRING_SERVICE, key)
    except _kr_errors.KeyringError:
        pass


@dataclass
class ProviderConfig:
    provider_type: str = "deepseek"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048

    def __post_init__(self) -> None:
        if not self.base_url:
            self.base_url = _DEFAULT_BASE_URLS.get(self.provider_type, "")
        if not self.model:
            defaults = {
                "openai": "gpt-4o",
                "deepseek": "deepseek-chat",
                "ollama": "llama3.2",
            }
            self.model = defaults.get(self.provider_type, "gpt-4o")


# ── Base provider ────────────────────────────────────────────────────────


class LLMProvider:
    """OpenAI-compatible chat provider (used for OpenAI, DeepSeek, Ollama, custom).

    Configuration and named profiles are persisted in the system keyring.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or self._load_config()
        self._active_profile_name: str | None = None
        self._available = bool(self.config.api_key) or self.config.provider_type == "ollama"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def active_profile_name(self) -> str | None:
        return self._active_profile_name

    # ── Configuration persistence ────────────────────────────────────────

    def configure(self, provider_type: str, **kwargs: Any) -> ProviderConfig:
        """Save provider configuration to keyring and return config.

        Args:
            provider_type: ``"openai"``, ``"deepseek"``, ``"ollama"``, etc.
            **kwargs: Additional config fields (api_key, base_url, model, etc.).
        """
        config_data = {
            "provider_type": provider_type,
            "api_key": kwargs.get("api_key", ""),
            "base_url": kwargs.get("base_url", ""),
            "model": kwargs.get("model", ""),
            "temperature": float(kwargs.get("temperature", 0.7)),
            "max_tokens": int(kwargs.get("max_tokens", 2048)),
        }
        _set_kr(_ACTIVE_CONFIG_KEY, json.dumps(config_data))
        self.config = ProviderConfig(**config_data)
        self._available = bool(self.config.api_key) or self.config.provider_type == "ollama"
        return self.config

    def _load_config(self) -> ProviderConfig:
        """Load provider config from keyring or return defaults."""
        raw = _get_kr(_ACTIVE_CONFIG_KEY)
        if not raw:
            return ProviderConfig()

        try:
            data = json.loads(raw)
            return ProviderConfig(
                provider_type=data.get("provider_type", "deepseek"),
                api_key=data.get("api_key", ""),
                base_url=data.get("base_url", ""),
                model=data.get("model", ""),
                temperature=float(data.get("temperature", 0.7)),
                max_tokens=int(data.get("max_tokens", 2048)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return ProviderConfig()

    def clear_config(self) -> None:
        """Remove provider configuration from keyring."""
        _del_kr(_ACTIVE_CONFIG_KEY)
        self.config = ProviderConfig()
        self._available = False
        self._active_profile_name = None

    # ── Named profile management ─────────────────────────────────────────

    def save_profile(self, name: str, provider_type: str, **kwargs: Any) -> dict:
        """Save a named LLM profile.

        Profiles are stored as a JSON dict keyed by name in keyring.
        """
        raw = _get_kr(_PROFILES_KEY) or "{}"
        try:
            profiles = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            profiles = {}

        profiles[name] = {
            "provider_type": provider_type,
            "api_key": kwargs.get("api_key", ""),
            "base_url": kwargs.get("base_url", ""),
            "model": kwargs.get("model", ""),
            "temperature": float(kwargs.get("temperature", 0.7)),
            "max_tokens": int(kwargs.get("max_tokens", 2048)),
        }
        _set_kr(_PROFILES_KEY, json.dumps(profiles))
        return profiles[name]

    def list_profiles(self) -> list[dict]:
        """Return all saved profiles (without API keys)."""
        raw = _get_kr(_PROFILES_KEY) or "{}"
        try:
            profiles = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []

        result = []
        for name, data in profiles.items():
            result.append({
                "name": name,
                "provider_type": data.get("provider_type", ""),
                "base_url": data.get("base_url", ""),
                "model": data.get("model", ""),
                "has_api_key": bool(data.get("api_key", "")),
            })
        return result

    def get_profile(self, name: str) -> dict | None:
        """Get a saved profile by name (WITH api_key)."""
        raw = _get_kr(_PROFILES_KEY) or "{}"
        try:
            profiles = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
        return profiles.get(name)

    def delete_profile(self, name: str) -> bool:
        """Delete a saved profile. Returns True if deleted."""
        raw = _get_kr(_PROFILES_KEY) or "{}"
        try:
            profiles = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return False
        if name not in profiles:
            return False
        del profiles[name]
        _set_kr(_PROFILES_KEY, json.dumps(profiles))
        return True

    def switch_to_profile(self, name: str) -> ProviderConfig | None:
        """Activate a saved profile. Returns the config or None."""
        profile = self.get_profile(name)
        if not profile:
            return None
        cfg = self.configure(
            provider_type=profile["provider_type"],
            api_key=profile.get("api_key", ""),
            base_url=profile.get("base_url", ""),
            model=profile.get("model", ""),
            temperature=profile.get("temperature", 0.7),
            max_tokens=profile.get("max_tokens", 2048),
        )
        self._active_profile_name = name
        return cfg

    # ── Chat ─────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_base_url(url: str) -> None:
        """Ensure the base URL is secure (HTTPS or localhost)."""
        if not url:
            return
        import urllib.parse as _up
        parsed = _up.urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return  # will fail on connect, not our problem
        if parsed.scheme == "http":
            host = parsed.hostname or ""
            if host not in ("127.0.0.1", "localhost"):
                raise ValueError(
                    f"Insecure LLM base URL: {url}. "
                    "Use HTTPS for remote endpoints or http://localhost for local models."
                )

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str:
        """Send a chat completion request and return the response text."""
        if not self._available:
            return "LLM is not configured. Please configure a provider first."

        self._validate_base_url(self.config.base_url)

        headers = {
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }

        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                if stream:
                    return await self._stream_chat(client, url, headers, payload)
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    return "No response from LLM."
                return choices[0].get("message", {}).get("content", "")
        except httpx.HTTPStatusError as e:
            return f"LLM API error: HTTP {e.response.status_code}"
        except httpx.TimeoutException:
            return "LLM request timed out. Check your provider configuration."
        except Exception as e:
            return f"LLM error: {e!s}"

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        payload: dict,
    ) -> str:
        """Handle streaming response and collect full text."""
        full_text = ""
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk_data = line[6:].strip()
                    if chunk_data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                    except json.JSONDecodeError:
                        continue
        return full_text

    async def generate_command(
        self,
        message: str,
        command_defs: list[dict],
    ) -> dict | None:
        """Ask the LLM to generate a structured command from natural language.

        Returns {"tokens": [...], "flags": {...}} or None.
        """
        defs_text = json.dumps(command_defs, indent=2) if command_defs else "[]"

        system_prompt = (
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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        try:
            result = await self.chat(messages, stream=False)
            if result.startswith("LLM error") or result.startswith("LLM API error"):
                return None
            return self._parse_command_result(result.strip())
        except Exception:
            return None

    @staticmethod
    def _parse_command_result(text: str) -> dict | None:
        """Parse LLM response into {"tokens": [...], "flags": {...}}.

        Handles bare JSON, markdown-fenced JSON, and plain text fallback.
        """
        if not text:
            return None

        # Strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
        text = text.strip()

        # Try JSON parse
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tokens" in data:
                return data
        except json.JSONDecodeError:
            pass

        # Fallback: extract !command from plain text
        cmd_match = re.search(r"!(\S+(?:\s+\S+)*)", text)
        if cmd_match:
            raw = cmd_match.group(1).strip()
            parts = raw.split()
            return {"tokens": parts, "flags": {}}

        return None

