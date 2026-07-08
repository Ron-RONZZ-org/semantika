"""API E2E tests for user configuration endpoints.

Covers ``GET /api/v1/user/config`` and ``PATCH /api/v1/user/config``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Must override data dir before importing app
TEST_DATA_DIR = Path("/tmp/semantika-ucfg-test") / str(os.getpid())
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SEMANTIKA_DATA_DIR"] = str(TEST_DATA_DIR)

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestUserConfigGet:
    """GET /api/v1/user/config"""

    def test_get_config_returns_locale(self, client: TestClient):
        resp = client.get("/api/v1/user/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "locale" in data
        assert isinstance(data["locale"], str)

    def test_default_locale_is_en(self, client: TestClient):
        resp = client.get("/api/v1/user/config")
        assert resp.status_code == 200
        assert resp.json()["locale"] == "en"


class TestUserConfigPatch:
    """PATCH /api/v1/user/config"""

    def test_update_locale(self, client: TestClient):
        resp = client.patch("/api/v1/user/config", json={"locale": "fr"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["locale"] == "fr"

    def test_update_locale_persists(self, client: TestClient):
        # First update
        client.patch("/api/v1/user/config", json={"locale": "de"})
        # Then read back
        resp = client.get("/api/v1/user/config")
        assert resp.status_code == 200
        assert resp.json()["locale"] == "de"

    def test_update_locale_with_region(self, client: TestClient):
        resp = client.patch("/api/v1/user/config", json={"locale": "en-US"})
        assert resp.status_code == 200
        assert resp.json()["locale"] == "en-US"

    def test_invalid_locale_too_short(self, client: TestClient):
        resp = client.patch("/api/v1/user/config", json={"locale": "x"})
        assert resp.status_code == 400

    def test_invalid_locale_too_long(self, client: TestClient):
        resp = client.patch("/api/v1/user/config", json={"locale": "toolong"})
        assert resp.status_code == 400

    def test_empty_payload_is_noop(self, client: TestClient):
        resp = client.patch("/api/v1/user/config", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "locale" in data

    def test_unknown_field_is_ignored(self, client: TestClient):
        resp = client.patch("/api/v1/user/config", json={"locale": "es", "unknown_field": "value"})
        assert resp.status_code == 200
        assert resp.json()["locale"] == "es"

    def test_update_twice_different_locales(self, client: TestClient):
        client.patch("/api/v1/user/config", json={"locale": "ja"})
        resp = client.patch("/api/v1/user/config", json={"locale": "ko"})
        assert resp.status_code == 200
        assert resp.json()["locale"] == "ko"

    def test_get_after_patch_returns_updated_value(self, client: TestClient):
        client.patch("/api/v1/user/config", json={"locale": "pt"})
        resp = client.get("/api/v1/user/config")
        assert resp.json()["locale"] == "pt"
