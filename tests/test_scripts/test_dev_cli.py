"""Tests for semantika.scripts.dev_cli — dev_main using lightercore.dev_helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestDevMain:
    """Test dev_main() — the entry point for `semantika-dev`.

    The underlying helper functions (find_dot_dev, is_seeded, setup_data_dir,
    etc.) are tested in lightercore's test suite. Here we verify that
    dev_main correctly delegates to them.
    """

    _BASE_ARGS = {
        "seed": None,
        "prod": None,
        "seed_from": None,
        "data_dir": None,
        "port": None,
        "keep_data": False,
        "quiet": True,
        "no_hooks": False,
    }

    def _make_args(self, **overrides: object) -> MagicMock:
        d = dict(self._BASE_ARGS)
        d.update(overrides)
        return MagicMock(**d)

    # ── Normal flow: calls create_app + uvicorn.run ───────────────────────

    @patch("uvicorn.run")
    def test_starts_uvicorn(self, mock_uvicorn, tmp_path: Path) -> None:
        """dev_main should call uvicorn.run."""
        with (
            patch("semantika.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("semantika.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("semantika.server.app.create_app") as mock_create_app,
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args()
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)
            mock_create_app.return_value = MagicMock()

            from semantika.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            assert mock_uvicorn.called
            assert mock_create_app.called

    @patch("uvicorn.run")
    def test_passes_no_hooks(self, mock_uvicorn, tmp_path: Path) -> None:
        """--no-hooks should be passed to create_app."""
        with (
            patch("semantika.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("semantika.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("semantika.server.app.create_app") as mock_create_app,
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(no_hooks=True)
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)
            mock_create_app.return_value = MagicMock()

            from semantika.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            mock_create_app.assert_called_once_with(no_hooks=True)

    # ── Seed sources ──────────────────────────────────────────────────────

    @patch("uvicorn.run")
    def test_seed_calls_seed_prompt_commands(self, mock_uvicorn, tmp_path: Path) -> None:
        """--seed should call _seed_prompt_commands when data dir is empty."""
        with (
            patch("semantika.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("semantika.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("semantika.scripts.dev_cli.is_seeded", return_value=False),
            patch("semantika.scripts.dev_cli.find_dot_dev") as mock_find_dot,
            patch("semantika.scripts.dev_cli._seed_prompt_commands") as mock_seed_cmds,
            patch("semantika.scripts.dev_cli._auto_configure_llm"),
            patch("semantika.server.app.create_app"),
        ):
            dot_dev = tmp_path / ".dev"
            dot_dev.write_text("DEEPSEEK_API_KEY=sk-test\n")
            mock_find_dot.return_value = dot_dev

            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(seed="auto")
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)

            from semantika.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            mock_seed_cmds.assert_called_once()

    @patch("uvicorn.run")
    def test_seed_skipped_when_already_seeded(self, mock_uvicorn, tmp_path: Path) -> None:
        """--seed should skip seeding when data dir already has content."""
        with (
            patch("semantika.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("semantika.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("semantika.scripts.dev_cli.is_seeded", return_value=True),
            patch("semantika.scripts.dev_cli._seed_prompt_commands") as mock_seed_cmds,
            patch("semantika.server.app.create_app"),
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(seed="auto")
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)

            from semantika.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            mock_seed_cmds.assert_not_called()

    # ── Mutual exclusivity ────────────────────────────────────────────────

    def test_mutual_exclusivity_enforced(self) -> None:
        """--seed and --prod together should exit."""
        with (
            patch("semantika.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(seed="auto", prod="auto")
            mock_parser_factory.return_value = mock_parser

            from semantika.scripts.dev_cli import dev_main

            with pytest.raises(SystemExit):
                dev_main()


class TestParseDotDev:
    def test_parses_key_value(self, tmp_path: Path) -> None:
        from semantika.scripts.dev_cli import _parse_dot_dev
        f = tmp_path / ".dev"
        f.write_text('DEEPSEEK_API_KEY="sk-test"\nKEY2=val2\n')
        result = _parse_dot_dev(f)
        assert result == {"DEEPSEEK_API_KEY": "sk-test", "KEY2": "val2"}

    def test_empty_file(self, tmp_path: Path) -> None:
        from semantika.scripts.dev_cli import _parse_dot_dev
        f = tmp_path / ".dev"
        f.write_text("")
        result = _parse_dot_dev(f)
        assert result == {}

    def test_skips_comments(self, tmp_path: Path) -> None:
        from semantika.scripts.dev_cli import _parse_dot_dev
        f = tmp_path / ".dev"
        f.write_text("# comment\nKEY=val\n")
        result = _parse_dot_dev(f)
        assert result == {"KEY": "val"}

    def test_missing_file(self, tmp_path: Path) -> None:
        from semantika.scripts.dev_cli import _parse_dot_dev
        result = _parse_dot_dev(tmp_path / "nonexistent")
        assert result == {}
