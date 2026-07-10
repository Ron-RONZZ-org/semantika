"""Tests for !llm prompt commands and /api/v1/llm/prompts endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from semantika.server.app import create_app
from semantika.server.llm.prompt_defaults import (
    DEFAULT_AGENTS_STYLE,
    DEFAULT_SEMANTIKA_PROMPT,
    SEMANTIKA_PROMPT_FILES,
    get_prompt_files_manager,
)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def patch_config_to_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point config_dir to tmp_path and seed a couple of prompt files."""
    monkeypatch.setattr(
        "lightercore.paths.config_dir",
        lambda: tmp_path,
    )

    # Seed two files: one exact default, one modified
    sys_path = tmp_path / "system_prompt.md"
    sys_path.parent.mkdir(parents=True, exist_ok=True)
    sys_path.write_text(DEFAULT_SEMANTIKA_PROMPT, encoding="utf-8")

    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("# Custom AGENTS content\nModified!", encoding="utf-8")

    return tmp_path


def test_defaults_loaded() -> None:
    assert len(SEMANTIKA_PROMPT_FILES) == 4
    names = [pf.name for pf in SEMANTIKA_PROMPT_FILES]
    assert "system-prompt" in names
    assert "agents" in names
    assert "template/turn1" in names
    assert "template/turn2" in names


def test_integration_list_all(patch_config_to_tmp: Path) -> None:
    mgr = get_prompt_files_manager()
    entries = mgr.list_all()
    assert len(entries) == 4

    system = next(e for e in entries if e["name"] == "system-prompt")
    assert system["exists"] is True
    assert system["is_modified"] is False, f"Expected not modified, got: {system}"

    agents = next(e for e in entries if e["name"] == "agents")
    assert agents["exists"] is True
    assert agents["is_modified"] is True  # different from default


def test_integration_modified_count(patch_config_to_tmp: Path) -> None:
    mgr = get_prompt_files_manager()
    assert mgr.modified_count() == 1  # only agents is modified


def test_integration_reset_restores_default(patch_config_to_tmp: Path) -> None:
    mgr = get_prompt_files_manager()
    mgr.reset("agents")
    assert mgr.modified_count() == 0


def test_api_list(client, patch_config_to_tmp):
    resp = client.get("/api/v1/llm/prompts/list")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4


def test_api_modified_count(client, patch_config_to_tmp):
    resp = client.get("/api/v1/llm/prompts/modified-count")
    assert resp.status_code == 200
    data = resp.json()
    assert data["modified_count"] == 1
    assert data["total"] == 4


def test_api_view(client, patch_config_to_tmp):
    resp = client.get("/api/v1/llm/prompts/system-prompt")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "system-prompt"
    assert DEFAULT_SEMANTIKA_PROMPT[:50] in data["current"]


def test_api_view_not_found(client):
    resp = client.get("/api/v1/llm/prompts/nonexistent")
    assert resp.status_code == 404


def test_api_reset(client, patch_config_to_tmp):
    resp = client.post("/api/v1/llm/prompts/agents/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert "reset" in data["message"].lower()

    # Verify it's now unmodified
    resp = client.get("/api/v1/llm/prompts/modified-count")
    assert resp.json()["modified_count"] == 0


def test_api_save(client, patch_config_to_tmp):
    resp = client.post("/api/v1/llm/prompts/system-prompt/save", json={
        "content": "New content",
    })
    assert resp.status_code == 200

    # Verify content was saved
    from lightercore.paths import config_dir
    path = config_dir() / "system_prompt.md"
    assert path.read_text(encoding="utf-8") == "New content"


def test_api_save_no_content(client):
    resp = client.post("/api/v1/llm/prompts/system-prompt/save", json={})
    assert resp.status_code == 400


def test_cmd_prompt_list(client, patch_config_to_tmp):
    resp = client.post("/api/v1/command", json={
        "tokens": ["llm", "prompt", "list"],
        "flags": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "prompt-list"
    assert data["data"]["count"] == 4
    assert data["data"]["modified_count"] == 1


def test_cmd_prompt_view(client, patch_config_to_tmp):
    resp = client.post("/api/v1/command", json={
        "tokens": ["llm", "prompt", "view"],
        "flags": {"name": "system-prompt"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "status"
    # The current content should match the shipped default
    assert DEFAULT_SEMANTIKA_PROMPT[:50] in data["data"]["current"]


def test_cmd_prompt_view_not_found(client):
    resp = client.post("/api/v1/command", json={
        "tokens": ["llm", "prompt", "view"],
        "flags": {"name": "nonexistent"},
    })
    assert resp.status_code == 400


def test_cmd_prompt_reset(client, patch_config_to_tmp):
    resp = client.post("/api/v1/command", json={
        "tokens": ["llm", "prompt", "reset"],
        "flags": {"name": "agents"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "reset" in data["data"]["message"].lower()


def test_cmd_prompt_reset_all(client, patch_config_to_tmp):
    resp = client.post("/api/v1/command", json={
        "tokens": ["llm", "prompt", "reset"],
        "flags": {"all": ""},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "reset" in data["data"]["message"].lower()
