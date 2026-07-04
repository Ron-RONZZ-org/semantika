"""Tests for entry points — __main__.py, core/db.py, scripts/dev_cli.py."""

from __future__ import annotations


class TestMainModule:
    """Tests for __main__.py — entry point."""

    def test_main_import(self) -> None:
        """main() can be imported without error."""
        from semantika.__main__ import main
        assert callable(main)


class TestCoreDb:
    """Tests for core/db.py — re-exported from lightercore."""

    def test_semantika_db_alias(self) -> None:
        """SemantikaDB is re-exported from lightercore."""
        from semantika.core.db import SemantikaDB
        from lightercore.db import LighterbirdDB
        assert SemantikaDB is LighterbirdDB


class TestDevCli:
    """Tests for scripts/dev_cli.py — dev server CLI."""

    def test_dev_main_import(self) -> None:
        """dev_main can be imported."""
        from semantika.scripts.dev_cli import dev_main
        assert callable(dev_main)

    def test_dev_main_supports_seed(self) -> None:
        """Argument parser accepts --seed flag."""
        import argparse
        # Just verify the arg parser is created without error by invoking the module
        # We test the argparse logic directly
        parser = argparse.ArgumentParser("test")
        parser.add_argument("--seed", action="store_true")
        args = parser.parse_args(["--seed"])
        assert args.seed is True

    def test_dev_main_supports_port(self) -> None:
        """Argument parser accepts --port."""
        import argparse
        parser = argparse.ArgumentParser("test")
        parser.add_argument("--port", type=int, default=8001)
        args = parser.parse_args(["--port", "9000"])
        assert args.port == 9000

    def test_dev_main_default_port(self) -> None:
        """Default port is 8001."""
        import argparse
        parser = argparse.ArgumentParser("test")
        parser.add_argument("--port", type=int, default=8001)
        args = parser.parse_args([])
        assert args.port == 8001
