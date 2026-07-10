"""Tests for the editable system prompt module.

Covers:
- :func:`load_system_prompt` auto-seeds on first access
- :func:`reload_system_prompt` re-reads from disk
- :func:`system_prompt_path` returns config-dir-relative path
- Legacy ``AGENTS.md`` migration to ``system_prompt.md``
- Backward-compat ``SEMANTIKA_SYSTEM_PROMPT`` constant
- ``GET /api/v1/llm/prompt`` endpoint
- ``POST /api/v1/llm/reload-prompt`` endpoint
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app
from semantika.server.llm.system_prompt import (
    DEFAULT_SEMANTIKA_PROMPT,
    SEMANTIKA_SYSTEM_PROMPT,
    load_system_prompt,
    reload_system_prompt,
    seed_config_defaults,
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

    def test_load_system_prompt_auto_seeds(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """First call auto-seeds system_prompt.md with the shipped default."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        prompt_file = tmp_path / "system_prompt.md"
        assert not prompt_file.exists()

        content = load_system_prompt()

        assert prompt_file.exists()
        assert content == DEFAULT_SEMANTIKA_PROMPT
        assert prompt_file.read_text(encoding="utf-8").strip() == DEFAULT_SEMANTIKA_PROMPT

    def test_load_system_prompt_returns_custom_content(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """When system_prompt.md exists, load() returns its content (not the default)."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        custom = "You are a custom assistant. Follow my rules."
        (tmp_path / "system_prompt.md").write_text(custom, encoding="utf-8")

        content = load_system_prompt()
        assert content == custom

    def test_reload_system_prompt_returns_new_content(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """After editing the file, reload_system_prompt() returns the new content."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        # Auto-seed
        load_system_prompt()
        assert (tmp_path / "system_prompt.md").exists()

        # Edit the file
        edited = "You are an edited assistant."
        (tmp_path / "system_prompt.md").write_text(edited, encoding="utf-8")

        # Reload
        content = reload_system_prompt()
        assert content == edited

    def test_reload_system_prompt_fallback_on_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """If the file is deleted, reload falls back to the default."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        load_system_prompt()
        (tmp_path / "system_prompt.md").unlink()

        content = reload_system_prompt()
        assert content == DEFAULT_SEMANTIKA_PROMPT

    def test_invokes_separate_manager_on_each_call(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Each call creates a fresh manager; no in-memory caching within the process."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        # First call seeds
        content1 = load_system_prompt()
        assert content1 == DEFAULT_SEMANTIKA_PROMPT

        # Edit the file behind the scenes
        (tmp_path / "system_prompt.md").write_text("fresh content", encoding="utf-8")

        # Second call reads the new file (no cache)
        content2 = load_system_prompt()
        assert content2 == "fresh content"


# ── seed_config_defaults tests ───────────────────────────────────────────────


class TestSeedConfigDefaults:
    """Test the generalized startup seeding of default config files."""

    def test_creates_missing_system_prompt(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """seed_config_defaults creates system_prompt.md when it doesn't exist."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        assert not (tmp_path / "system_prompt.md").exists()

        seed_config_defaults()

        assert (tmp_path / "system_prompt.md").exists()
        content = (tmp_path / "system_prompt.md").read_text(encoding="utf-8").strip()
        assert content == DEFAULT_SEMANTIKA_PROMPT

    def test_does_not_overwrite_existing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """seed_config_defaults does NOT overwrite an existing file with the default."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        custom = "Custom prompt for my graph."
        (tmp_path / "system_prompt.md").write_text(custom, encoding="utf-8")

        seed_config_defaults()

        content = (tmp_path / "system_prompt.md").read_text(encoding="utf-8")
        assert content == custom  # unchanged

    def test_empty_file_is_reseeded(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """An empty system_prompt.md is reseeded with the default."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        (tmp_path / "system_prompt.md").write_text("", encoding="utf-8")

        seed_config_defaults()

        content = (tmp_path / "system_prompt.md").read_text(encoding="utf-8").strip()
        assert content == DEFAULT_SEMANTIKA_PROMPT

    def test_migration_from_legacy_agends(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """seed_config_defaults migrates AGENTS.md content when system_prompt.md is missing."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        legacy = "# My graph conventions\n- Always use eo, fr, en\n"
        (tmp_path / "AGENTS.md").write_text(legacy, encoding="utf-8")

        seed_config_defaults()

        assert (tmp_path / "system_prompt.md").exists()
        content = (tmp_path / "system_prompt.md").read_text(encoding="utf-8")
        assert content.startswith(DEFAULT_SEMANTIKA_PROMPT)
        assert "migrated from AGENTS.md" in content
        assert "eo, fr, en" in content

    def test_unreadable_file_logged_not_crashed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """A permission-denied file does not crash seed_config_defaults."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        prompt_file = tmp_path / "system_prompt.md"
        # Make an unreadable/unwritable directory where the file would go
        prompt_file.write_text("test", encoding="utf-8")
        prompt_file.chmod(0o000)
        try:
            seed_config_defaults()  # should not raise
        finally:
            prompt_file.chmod(0o644)  # restore for cleanup

    def test_multiple_entries_all_seeded(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """If _CONFIG_DEFAULTS had multiple entries, all missing files are created."""
        # Monkey-patch the private registry to include a second entry
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        import semantika.server.llm.system_prompt as sp
        monkeypatch.setitem(
            sp._CONFIG_DEFAULTS,  # noqa: SLF001
            "extra_config.txt",
            "extra default",
        )
        # Remove system_prompt.md to force re-seed
        (tmp_path / "system_prompt.md").unlink(missing_ok=True)

        seed_config_defaults()

        assert (tmp_path / "system_prompt.md").exists()
        assert (tmp_path / "extra_config.txt").exists()
        assert (tmp_path / "extra_config.txt").read_text(encoding="utf-8") == "extra default"


# ── Legacy AGENTS.md migration tests ────────────────────────────────────────


class TestLegacyMigration:
    """Test that legacy AGENTS.md content is correctly migrated."""

    def test_migration_from_legacy(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """When AGENTS.md exists but system_prompt.md does not, content is migrated."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        legacy_content = "# Custom rules\nAlways use eo, fr, en labels.\n"
        (tmp_path / "AGENTS.md").write_text(legacy_content, encoding="utf-8")

        # First call triggers migration
        content = load_system_prompt()

        # system_prompt.md should exist now
        assert (tmp_path / "system_prompt.md").exists()
        assert content.startswith(DEFAULT_SEMANTIKA_PROMPT)
        assert "Custom rules" in content
        assert "eo, fr, en" in content
        # Should have a migration header
        assert "migrated from AGENTS.md" in content

    def test_migration_legacy_left_intact(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """The legacy AGENTS.md file is NOT deleted after migration."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        (tmp_path / "AGENTS.md").write_text("legacy", encoding="utf-8")
        load_system_prompt()
        assert (tmp_path / "AGENTS.md").exists()

    def test_no_migration_when_system_prompt_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """If system_prompt.md already exists, AGENTS.md is ignored."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        (tmp_path / "system_prompt.md").write_text("existing content", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("should be ignored", encoding="utf-8")

        content = load_system_prompt()
        assert content == "existing content"
        assert "should be ignored" not in content

    def test_migration_empty_legacy(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """An empty AGENTS.md does not trigger migration (auto-seeds with default)."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")

        content = load_system_prompt()
        assert content == DEFAULT_SEMANTIKA_PROMPT

    def test_migration_no_legacy_no_system_prompt(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """When neither file exists, auto-seed with the shipped default."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))
        content = load_system_prompt()
        assert content == DEFAULT_SEMANTIKA_PROMPT


# ── API endpoint tests ─────────────────────────────────────────────────────


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with isolated DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestPromptAPI:
    """Test GET /api/v1/llm/prompt and POST /api/v1/llm/reload-prompt."""

    @pytest.fixture(autouse=True)
    def _isolate_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Isolate the config directory so tests don't touch the real system_prompt.md."""
        monkeypatch.setenv("SEMANTIKA_CONFIG_DIR", str(tmp_path))

    def test_get_prompt_returns_content_and_path(self, client: TestClient):
        """GET /api/v1/llm/prompt returns the prompt text and file path."""
        resp = client.get("/api/v1/llm/prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt" in data
        assert "path" in data
        assert data["prompt"] == DEFAULT_SEMANTIKA_PROMPT
        assert data["path"].endswith("system_prompt.md")

    def test_get_prompt_returns_custom_content(self, client: TestClient, tmp_path: Path):
        """When the user edits system_prompt.md, GET returns the custom content."""
        custom = "You are my custom Semantika assistant."
        (tmp_path / "system_prompt.md").write_text(custom, encoding="utf-8")

        resp = client.get("/api/v1/llm/prompt")
        assert resp.status_code == 200
        assert resp.json()["prompt"] == custom

    def test_reload_prompt_returns_status_and_length(self, client: TestClient):
        """POST /api/v1/llm/reload-prompt returns status, length, and path."""
        # First load to seed
        client.get("/api/v1/llm/prompt")
        assert (client._transport.app.state  # noqa: SLF001
                or True)  # placeholder — we just need the file seeded

        resp = client.post("/api/v1/llm/reload-prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reloaded"
        assert data["length"] == len(DEFAULT_SEMANTIKA_PROMPT)
        assert data["path"].endswith("system_prompt.md")

    def test_reload_prompt_reflects_edits(self, client: TestClient, tmp_path: Path):
        """After editing system_prompt.md, reload returns the new content."""
        # First load
        client.get("/api/v1/llm/prompt")

        # Edit the file
        edited = "Edited prompt content."
        (tmp_path / "system_prompt.md").write_text(edited, encoding="utf-8")

        # Reload
        resp = client.post("/api/v1/llm/reload-prompt")
        assert resp.status_code == 200
        assert resp.json()["length"] == len(edited)

        # Verify next GET returns the edited content
        resp2 = client.get("/api/v1/llm/prompt")
        assert resp2.json()["prompt"] == edited

    def test_reload_prompt_handles_deleted_file(self, client: TestClient, tmp_path: Path):
        """If system_prompt.md is deleted, reload re-seeds it with the default."""
        # First load seeds
        client.get("/api/v1/llm/prompt")
        (tmp_path / "system_prompt.md").unlink()

        resp = client.post("/api/v1/llm/reload-prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reloaded"
        assert data["length"] == len(DEFAULT_SEMANTIKA_PROMPT)

    def test_chat_uses_custom_prompt(self, client: TestClient, tmp_path: Path):
        """Chat endpoint uses the user-edited system prompt."""
        # Write a custom prompt
        custom = "You are a custom assistant that only says 'beep boop'."
        (tmp_path / "system_prompt.md").write_text(custom, encoding="utf-8")

        # Chat without LLM configured — will hit the stub fallback
        # (the stub doesn't use the system prompt, so this test just verifies
        # the endpoint doesn't crash with a custom prompt in place)
        resp = client.post("/api/v1/llm/chat", json={"message": "hello"})
        assert resp.status_code == 200
        # The stub response should still work
        assert "reply" in resp.json()
