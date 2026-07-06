"""Tests for user config command handler via dispatch().

Uses mocked ``load_config`` / ``set_locale`` to avoid file I/O.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# Trigger handler registration
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.registry import dispatch


class TestUserConfig:
    """!user config handler"""

    @patch("semantika.server.command.handlers.user_config.load_config")
    def test_config_show_default(self, mock_load: pytest.MagicMock) -> None:
        mock_load.return_value = {}
        result = dispatch(["user", "config"], {})
        assert result["type"] == "status"
        assert result["data"]["locale"] == "en"

    @patch("semantika.server.command.handlers.user_config.load_config")
    def test_config_show_custom(self, mock_load: pytest.MagicMock) -> None:
        mock_load.return_value = {"locale": "fr"}
        result = dispatch(["user", "config"], {})
        assert result["type"] == "status"
        assert result["data"]["locale"] == "fr"

    @patch("semantika.server.command.handlers.user_config.set_locale")
    def test_config_set_locale(self, mock_set: pytest.MagicMock) -> None:
        result = dispatch(["user", "config"], {"locale": "de"})
        assert result["type"] == "status"
        assert "Locale set" in result["data"]["message"]

    @patch("semantika.server.command.handlers.user_config.set_locale")
    def test_config_set_locale_invalid(self, mock_set: pytest.MagicMock) -> None:
        with pytest.raises(Exception, match="Locale should be"):
            dispatch(["user", "config"], {"locale": "toolong"})

    @patch("semantika.server.command.handlers.user_config.load_config")
    def test_root_shows_summary(self, mock_load: pytest.MagicMock) -> None:
        mock_load.return_value = {"locale": "en"}
        result = dispatch(["user"], {})
        assert result["type"] == "status"
        assert "Current locale" in result["data"]["_summary"]
