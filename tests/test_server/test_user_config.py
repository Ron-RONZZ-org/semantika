"""Direct unit tests for the user_config module (not through API handlers)."""

from __future__ import annotations

import os
import importlib
import pytest
from pathlib import Path


class TestUserConfigDirect:
    """Direct unit tests for user_config module (not through handlers)."""

    def test_load_empty_config(self, tmp_path: Path):
        """load_config returns empty dict when file missing."""
        os.environ["SEMANTIKA_DATA_DIR"] = str(tmp_path)
        import semantika.server.user_config as ucfg
        importlib.reload(ucfg)
        assert ucfg.load_config() == {}

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        """save_config followed by load_config returns same data."""
        os.environ["SEMANTIKA_DATA_DIR"] = str(tmp_path)
        import semantika.server.user_config as ucfg
        importlib.reload(ucfg)

        cfg = {"locale": "fr", "theme": "dark"}
        ucfg.save_config(cfg)
        loaded = ucfg.load_config()
        assert loaded == cfg

    def test_set_locale(self, tmp_path: Path):
        """set_locale updates and persists locale."""
        os.environ["SEMANTIKA_DATA_DIR"] = str(tmp_path)
        import semantika.server.user_config as ucfg
        importlib.reload(ucfg)

        ucfg.set_locale("de")
        assert ucfg.get_locale() == "de"
        loaded = ucfg.load_config()
        assert loaded.get("locale") == "de"

    def test_get_bool_default_false(self, tmp_path: Path):
        """get_bool returns default for missing key."""
        os.environ["SEMANTIKA_DATA_DIR"] = str(tmp_path)
        import semantika.server.user_config as ucfg
        importlib.reload(ucfg)

        assert ucfg.get_bool("nonexistent") is False
        assert ucfg.get_bool("nonexistent", True) is True

    def test_get_bool_various_types(self, tmp_path: Path):
        """get_bool handles bool, string and int values."""
        os.environ["SEMANTIKA_DATA_DIR"] = str(tmp_path)
        import semantika.server.user_config as ucfg
        importlib.reload(ucfg)

        ucfg.save_config({
            "flag_true": True,
            "flag_false": False,
            "str_true": "true",
            "str_false": "false",
            "int_1": 1,
            "int_0": 0,
        })
        assert ucfg.get_bool("flag_true") is True
        assert ucfg.get_bool("flag_false") is False
        assert ucfg.get_bool("str_true") is True
        assert ucfg.get_bool("str_false") is False
        assert ucfg.get_bool("int_1") is True
        assert ucfg.get_bool("int_0") is False

    def test_set_bool_roundtrip(self, tmp_path: Path):
        """set_bool persists boolean values correctly."""
        os.environ["SEMANTIKA_DATA_DIR"] = str(tmp_path)
        import semantika.server.user_config as ucfg
        importlib.reload(ucfg)

        ucfg.set_bool("normalise_node_ids", True)
        assert ucfg.get_bool("normalise_node_ids") is True
        ucfg.set_bool("normalise_node_ids", False)
        assert ucfg.get_bool("normalise_node_ids") is False
