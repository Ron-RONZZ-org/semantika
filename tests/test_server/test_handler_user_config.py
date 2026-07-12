"""Tests for user config command handler via dispatch().

Uses mocked ``load_config`` / ``set_locale`` / ``get_bool`` / ``set_bool``
to avoid file I/O.
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
    @patch("semantika.server.command.handlers.user_config.get_bool")
    def test_config_show_default(
        self, mock_get_bool: pytest.MagicMock, mock_load: pytest.MagicMock
    ) -> None:
        mock_load.return_value = {}
        mock_get_bool.return_value = False
        result = dispatch(["user", "config"], {})
        assert result["type"] == "settings"
        assert result["data"]["locale"] == "en"
        assert result["data"]["normalise_node_ids"] is False
        assert result["data"]["strip_diacritics_from_predicate_ids"] is False

    @patch("semantika.server.command.handlers.user_config.load_config")
    @patch("semantika.server.command.handlers.user_config.get_bool")
    def test_config_show_custom(
        self, mock_get_bool: pytest.MagicMock, mock_load: pytest.MagicMock
    ) -> None:
        mock_load.return_value = {"locale": "fr"}
        mock_get_bool.return_value = True
        result = dispatch(["user", "config"], {})
        assert result["type"] == "settings"
        assert result["data"]["locale"] == "fr"
        assert result["data"]["normalise_node_ids"] is True
        assert result["data"]["strip_diacritics_from_predicate_ids"] is True

    @patch("semantika.server.command.handlers.user_config.set_locale")
    @patch("semantika.server.command.handlers.user_config.load_config")
    def test_config_set_locale(
        self, mock_load: pytest.MagicMock, mock_set: pytest.MagicMock
    ) -> None:
        mock_load.return_value = {}
        result = dispatch(["user", "config"], {"locale": "de"})
        assert result["type"] == "status"
        assert "Configuration updated" in result["data"]["message"]
        assert result["data"]["locale"] == "en"

    @patch("semantika.server.command.handlers.user_config.set_locale")
    def test_config_set_locale_invalid(self, mock_set: pytest.MagicMock) -> None:
        with pytest.raises(Exception, match="Locale should be"):
            dispatch(["user", "config"], {"locale": "toolong"})

    @patch("semantika.server.command.handlers.user_config.load_config")
    @patch("semantika.server.command.handlers.user_config.get_bool")
    def test_root_shows_settings(
        self, mock_get_bool: pytest.MagicMock, mock_load: pytest.MagicMock
    ) -> None:
        mock_load.return_value = {"locale": "en"}
        mock_get_bool.return_value = False
        result = dispatch(["user"], {})
        assert result["type"] == "settings"
        assert result["data"]["locale"] == "en"
        assert "normalise_node_ids" in result["data"]
        assert "strip_diacritics_from_predicate_ids" in result["data"]

    @patch("semantika.server.command.handlers.user_config.set_bool")
    @patch("semantika.server.command.handlers.user_config.load_config")
    @patch("semantika.server.command.handlers.user_config.get_bool")
    def test_set_normalise_node_ids(
        self,
        mock_get_bool: pytest.MagicMock,
        mock_load: pytest.MagicMock,
        mock_set: pytest.MagicMock,
    ) -> None:
        mock_load.return_value = {}
        mock_get_bool.return_value = True
        result = dispatch(["user", "config"], {"normalise-node-ids": "on"})
        assert result["type"] == "status"
        assert "Configuration updated" in result["data"]["message"]
        mock_set.assert_called_once_with("normalise_node_ids", True)

    @patch("semantika.server.command.handlers.user_config.set_bool")
    @patch("semantika.server.command.handlers.user_config.load_config")
    def test_set_strip_predicate_diacritics(
        self,
        mock_load: pytest.MagicMock,
        mock_set: pytest.MagicMock,
    ) -> None:
        mock_load.return_value = {}
        result = dispatch(["user", "config"], {"strip-predicate-diacritics": "on"})
        assert result["type"] == "status"
        assert "Configuration updated" in result["data"]["message"]
        mock_set.assert_called_once_with("strip_diacritics_from_predicate_ids", True)

    @patch("semantika.server.command.handlers.user_config.set_bool")
    def test_set_invalid_flag_value(self, mock_set: pytest.MagicMock) -> None:
        with pytest.raises(Exception, match="must be 'on' or 'off'"):
            dispatch(["user", "config"], {"normalise-node-ids": "maybe"})
