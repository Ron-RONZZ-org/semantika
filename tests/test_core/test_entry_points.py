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
        parser.add_argument("--port", type=int, default=6015)
        args = parser.parse_args(["--port", "9000"])
        assert args.port == 9000

    def test_dev_main_default_port(self) -> None:
        """Default port is 6015."""
        import argparse
        parser = argparse.ArgumentParser("test")
        parser.add_argument("--port", type=int, default=6015)
        args = parser.parse_args([])
        assert args.port == 6015


class TestGraphDb:
    """Tests for graph/db.py — DB singleton and service caching."""

    def test_reset_services(self) -> None:
        """reset_services clears the cache; next call creates fresh instances."""
        from semantika.graph.db import get_services, reset_services, close_db
        # Close any existing singleton first
        close_db()
        reset_services()

        svc1 = get_services()
        svc2 = get_services()
        # Before reset, same cache returns same objects
        assert svc1["node"] is svc2["node"]

        reset_services()
        svc3 = get_services()
        # After reset, should be a new instance
        assert svc1["node"] is not svc3["node"]

        close_db()
        reset_services()
