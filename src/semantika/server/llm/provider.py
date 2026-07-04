"""LLM provider abstraction — OpenAI-compatible + Ollama.

Port of lighterbird's provider pattern: text-based command generation
via system prompt (no native function-calling), plus plain chat.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx


# ── Config ───────────────────────────────────────────────────────────────

_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "ollama": "http://localhost:11434/v1",
}


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
                "deepseek": "deepseek-v4-flash",
                "ollama": "llama3.2",
            }
            self.model = defaults.get(self.provider_type, "gpt-4o")


# ── Base provider ────────────────────────────────────────────────────────


class LLMProvider:
    """OpenAI-compatible chat provider (used for OpenAI, DeepSeek, Ollama, custom)."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._available = bool(config.api_key) or config.provider_type == "ollama"

    @property
    def available(self) -> bool:
        return self._available

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str:
        """Send a chat completion request and return the response text."""
        if not self._available:
            return "LLM is not configured. Please configure a provider first."

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


# ── Command definitions helper ───────────────────────────────────────────


def get_command_definitions(tree: list[dict]) -> list[dict]:
    """Flatten the command tree into machine-readable definitions for the LLM."""
    definitions: list[dict] = []

    def _walk(nodes: list[dict], prefix: list[str] | None = None) -> None:
        for node in nodes:
            path = (prefix or []) + [node["name"]]
            entry: dict[str, Any] = {
                "path": path,
                "canonical": f"!{' '.join(path)}",
                "description": node.get("description", ""),
            }
            if node.get("params"):
                entry["params"] = [
                    {
                        "name": p["name"],
                        "required": p.get("required", False),
                        "type": p.get("type", "string"),
                    }
                    for p in node["params"]
                ]
            if node.get("flags"):
                entry["flags"] = [
                    {
                        "name": f["name"],
                        "type": f.get("type", "string"),
                        "required": f.get("required", False),
                    }
                    for f in node["flags"]
                ]
            definitions.append(entry)
            if node.get("children"):
                _walk(node["children"], path)

    _walk(tree)
    return definitions
