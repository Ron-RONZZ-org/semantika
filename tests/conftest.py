"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def temp_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
    """Redirect data directory to a temp path for test isolation."""
    # Will be implemented once core/paths is vendored
    pass
