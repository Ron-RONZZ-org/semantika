"""Tests for the editable system prompt module — two-file model.

Covers:
- :func:`load_system_prompt` auto-seeds both files on first access
- :func:`reload_system_prompt` re-reads from disk
- :func:`system_prompt_path` / :func:`agents_path` return correct paths
- Two-file append: base prompt + AGENTS.md combined
- Backward compat: migrated single-file content returned as-is
- ``GET /api/v1/llm/prompt`` endpoint
- ``POST /api/v1/llm/reload-prompt`` endpoint
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app
from semantika.server.llm.system_prompt import (
    DEFAULT_AGENTS_STYLE,
    DEFAULT_SEMANTIKA_PROMPT,
    SEMANTIKA_SYSTEM_PROMPT,
    agents_path,
    load_system_prompt,
    reload_system_prompt,
    system_prompt_path,
)


# ── Unit tests ─────────────────────────────────────────────────────────────


class TestSystemPromptModule:
    """Test the system_prompt module functions directly."""

    def test_default_constant_unchanged(self):
        """SEMANTIKA_SYSTEM_PROMPT backward-compat alias equals the default."""
        assert SEMANTIKA_SYSTEM_PROMPT == DEFAULT_SEMANTIKA_PROMPT
        assert isinstance(SEMANTIKA_SYSTEM_PROMPT, str)
        assert len(SEMANTIKA_SYSTEM_PROMPT) > 100

    def test_system_prompt_path_returns_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """system_prompt_path() returns a Path under the config dir."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        path = system_prompt_path()
        assert isinstance(path, Path)
        assert path.name == "system_prompt.md"
        assert str(tmp_path) in str(path)

    def test_agents_path_returns_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """agents_path() returns the AGENTS.md path."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        path = agents_path()
        assert isinstance(path, Path)
        assert path.name == "AGENTS.md"
        assert str(tmp_path) in str(path)


class TestLoadSystemPrompt:
    """Test the two-file lazy auto-seed and combine logic."""

    def test_first_run_seeds_both_files(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """First call auto-seeds both files and returns combined content."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        assert not (tmp_path / "system_prompt.md").exists()
        assert not (tmp_path / "AGENTS.md").exists()

        content = load_system_prompt()

        assert (tmp_path / "system_prompt.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        # Content should be base + separator + AGENTS
        assert content.startswith(DEFAULT_SEMANTIKA_PROMPT)
        assert DEFAULT_AGENTS_STYLE.strip() in content

    def test_empty_agents_is_reseeded(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """An empty AGENTS.md is reseeded with the default on first access."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")

        content = load_system_prompt()
        # AGENTS.md was empty but load_user_style() reseeds it
        assert DEFAULT_AGENTS_STYLE.strip() in content

    def test_appends_agents_content(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """When both files exist, AGENTS.md content is appended."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        # Pre-seed system_prompt.md
        (tmp_path / "system_prompt.md").write_text("Base prompt.", encoding="utf-8")
        style = "Always use eo, fr, en labels."
        (tmp_path / "AGENTS.md").write_text(style, encoding="utf-8")

        content = load_system_prompt()
        assert content == "Base prompt.\n\n" + style

    def test_does_not_double_append_migrated_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """A system_prompt.md with migration marker is returned as-is (no double-append)."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        # Simulate a migrated file from the previous single-file version
        migrated = DEFAULT_SEMANTIKA_PROMPT + "\n\n---\n*migrated from AGENTS.md*\n---\n\nlegacy content"
        (tmp_path / "system_prompt.md").write_text(migrated, encoding="utf-8")
        # AGENTS.md also exists (left intact by migration)
        (tmp_path / "AGENTS.md").write_text("Should NOT be appended.", encoding="utf-8")

        content = load_system_prompt()
        assert content == migrated
        assert "Should NOT be appended" not in content

    def test_editing_base_respects_changes(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """After editing system_prompt.md, the edited content is used."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        # First call seeds
        load_system_prompt()

        # Edit the base file
        custom_base = "You are a custom Semantika assistant."
        (tmp_path / "system_prompt.md").write_text(custom_base, encoding="utf-8")

        content = load_system_prompt()
        assert custom_base in content
        assert DEFAULT_AGENTS_STYLE.strip() in content  # AGENTS still appended

    def test_reload_returns_new_content(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Reload re-reads both files after edits."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        # Seed by loading first
        load_system_prompt()

        # Edit both files — reload should re-read them fresh
        (tmp_path / "system_prompt.md").write_text("New base.", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("New style.", encoding="utf-8")

        content = reload_system_prompt()
        assert content == "New base.\n\nNew style."


class TestLLMAPIRoutes:
    """Test the API endpoints work with the two-file model."""

    @pytest.fixture(scope="class")
    def client(self) -> TestClient:
        app = create_app()
        with TestClient(app) as c:
            yield c

    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))

    def test_get_prompt_combined(self, client: TestClient):
        """GET /api/v1/llm/prompt returns the combined prompt."""
        resp = client.get("/api/v1/llm/prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt" in data
        assert data["prompt"].startswith(DEFAULT_SEMANTIKA_PROMPT)
        assert DEFAULT_AGENTS_STYLE.strip() in data["prompt"]

    def test_reload_respects_edits(self, client: TestClient, tmp_path: Path):
        """POST /api/v1/llm/reload-prompt reflects file edits."""
        # First call to seed
        client.get("/api/v1/llm/prompt")

        # Edit the base prompt
        custom = "Custom base prompt."
        (tmp_path / "system_prompt.md").write_text(custom, encoding="utf-8")

        resp = client.post("/api/v1/llm/reload-prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reloaded"
        # Length should be custom base + AGENTS.md (which was auto-seeded on first GET)
        assert data["length"] == len(custom + "\n\n" + DEFAULT_AGENTS_STYLE.strip())

    def test_chat_stub_works_with_custom_prompt(self, client: TestClient):
        """Chat endpoint still works with the two-file prompt (stub fallback)."""
        resp = client.post("/api/v1/llm/chat", json={"message": "hello"})
        assert resp.status_code == 200
        assert "reply" in resp.json()
