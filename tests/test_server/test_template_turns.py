"""Tests for template turn prompt expansion and style example injection.

Covers:
- ``_expand_turn_prompt`` with named-only variables
- ``_get_style_example`` with and without templates
- DEFAULT_TURN1 / DEFAULT_TURN2 content (named placeholders, predicate creation)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from semantika.server.llm.prompt_defaults import DEFAULT_TURN1, DEFAULT_TURN2


# ── _expand_turn_prompt tests ─────────────────────────────────────────────────


class TestExpandTurnPrompt:
    """Named-only variable expansion in turn prompts."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from semantika.server.routes.prompt_commands_helpers import _expand_turn_prompt
        self._expand = _expand_turn_prompt

    def test_simple_named_substitution(self):
        """A named $VARIABLE is replaced with its value."""
        result = self._expand("Hello $NAME!", {"NAME": "World"})
        assert result == "Hello World!"

    def test_multiple_variables(self):
        """Multiple named vars are all substituted."""
        result = self._expand(
            "$A and $B",
            {"A": "first", "B": "second"},
        )
        assert result == "first and second"

    def test_unknown_placeholder_left_as_is(self):
        """An old-style $1 or unknown $FOO is NOT substituted."""
        result = self._expand(
            "Old: $1, known: $GREETING",
            {"GREETING": "hello"},
        )
        assert "$1" in result
        assert "hello" in result

    def test_no_variables_no_change(self):
        """Template with no placeholders is returned as-is."""
        result = self._expand("Static text", {})
        assert result == "Static text"

    def test_variable_not_in_template_ignored(self):
        """Passing a var that is not present in the template is safe."""
        result = self._expand("Hello $NAME", {"NAME": "World", "EXTRA": "ignored"})
        assert result == "Hello World"

    def test_repeated_variable(self):
        """Same variable used multiple times is replaced everywhere."""
        result = self._expand("$X, $X, $X", {"X": "echo"})
        assert result == "echo, echo, echo"

    def test_dollar_sign_in_content(self):
        """Literal $ not followed by a variable name is left alone."""
        result = self._expand("Price: $5.00", {"PRICE": "10"})
        assert result == "Price: $5.00"


# ── _get_style_example tests ──────────────────────────────────────────────────


class TestGetStyleExample:
    """Style example from user-created templates."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Point config_dir to tmp_path."""
        monkeypatch.setattr(
            "semantika.server.routes.prompt_commands_helpers.config_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "semantika.server.templates.loader.config_dir",
            lambda: tmp_path,
        )
        self.templates_dir = tmp_path / "templates"
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def _import(self):
        from semantika.server.routes.prompt_commands_helpers import _get_style_example
        return _get_style_example

    def test_no_templates_returns_empty(self):
        """No templates → empty string."""
        assert self._import()() == ""

    def test_with_template_returns_content(self):
        """A single template returns its file content."""
        yaml_content = (
            "name: book\n"
            "description: A test template\n"
            "params:\n"
            "  - name: subject\n"
            "    label: Subject\n"
            "    type: node\n"
            "    required: true\n"
            "triples:\n"
            "  - \"{subject} hasAuthor {author}\"\n"
        )
        tpl_file = self.templates_dir / "book.yaml"
        tpl_file.write_text(yaml_content, encoding="utf-8")

        result = self._import()()
        assert result == yaml_content.strip()

    def test_picks_most_recently_modified(self):
        """When multiple templates exist, picks the most recently modified."""
        old_content = "name: old\ndescription: Old template\n"
        new_content = "name: new\ndescription: New template\n"

        old_file = self.templates_dir / "old.yaml"
        old_file.write_text(old_content, encoding="utf-8")

        new_file = self.templates_dir / "new.yaml"
        new_file.write_text(new_content, encoding="utf-8")

        # Touch new_file to make it newer
        new_file.touch()

        result = self._import()()
        assert "New template" in result
        assert "Old template" not in result

    def test_skips_bad_template_file(self, caplog: pytest.LogCaptureFixture):
        """A template file that can't be read returns empty."""
        import logging
        caplog.set_level(logging.WARNING)

        tpl_file = self.templates_dir / "book.yaml"
        tpl_file.write_text("name: book\ndescription: Test\n", encoding="utf-8")

        # Make the file unreadable
        tpl_file.chmod(0o000)

        result = self._import()()
        assert result == ""  # Graceful fallback


# ── Default prompt content ────────────────────────────────────────────────────


class TestDefaultTurnPrompts:
    """Shipped defaults for turn1 and turn2 should use named placeholders."""

    def test_turn1_has_creation_instructions(self):
        """DEFAULT_TURN1 should tell the LLM to create predicates if missing."""
        assert "predicate.add" in DEFAULT_TURN1
        assert "create" in DEFAULT_TURN1.lower()
        assert "search" in DEFAULT_TURN1.lower()

    def test_turn1_uses_arguments_placeholder(self):
        """DEFAULT_TURN1 should use $ARGUMENTS for user input."""
        assert "$ARGUMENTS" in DEFAULT_TURN1

    def test_turn1_mentions_naming_conventions(self):
        """DEFAULT_TURN1 should reference AGENTS.md conventions."""
        assert "AGENTS.md" in DEFAULT_TURN1 or "naming" in DEFAULT_TURN1.lower()

    def test_turn1_mentions_node_discovery(self):
        """DEFAULT_TURN1 should instruct the LLM to find/create nodes."""
        assert "node.search" in DEFAULT_TURN1 or "**node.search**" in DEFAULT_TURN1
        assert "node.add" in DEFAULT_TURN1 or "**node.add**" in DEFAULT_TURN1
        assert "type nodes" in DEFAULT_TURN1.lower() or "rdf:type" in DEFAULT_TURN1

    def test_turn2_uses_named_placeholders(self):
        """DEFAULT_TURN2 should use $TEMPLATE_DESCRIPTION and $STYLE_EXAMPLE."""
        assert "$AVAILABLE_PREDICATES" not in DEFAULT_TURN2  # replaced by context.get
        assert "$TEMPLATE_DESCRIPTION" in DEFAULT_TURN2
        assert "$STYLE_EXAMPLE" in DEFAULT_TURN2
        assert "context.get" in DEFAULT_TURN2

    def test_turn2_has_no_positional_placeholders(self):
        """DEFAULT_TURN2 should NOT use $1, $2 positional placeholders."""
        assert "$1" not in DEFAULT_TURN2
        assert "$2" not in DEFAULT_TURN2

    def test_turn2_includes_template_schema(self):
        """DEFAULT_TURN2 should reference the YAML schema."""
        assert "template.save" in DEFAULT_TURN2
        assert "name:" in DEFAULT_TURN2

    def test_turn2_includes_style_example_section(self):
        """DEFAULT_TURN2 should have a style example section."""
        assert "Style example" in DEFAULT_TURN2
        assert "$STYLE_EXAMPLE" in DEFAULT_TURN2

    def test_turn2_mentions_predicate_creation(self):
        """DEFAULT_TURN2 should tell LLM to create predicates if missing."""
        assert "predicate.add" in DEFAULT_TURN2
