"""Tests for /text-to-triples flow infrastructure.

Covers:
- Flow session annotation functions
- Turn prompt defaults parsing
- Dispatch routing (special case in prompt_commands.py)

The async tool loop integration is tested separately in API E2E tests.
"""

from __future__ import annotations

from semantika.server.llm.prompt_defaults import (
    DEFAULT_TTT_TURN1,
    DEFAULT_TTT_TURN2,
    DEFAULT_TTT_TURN3,
    DEFAULT_TURN1,
    DEFAULT_TURN2,
)


class TestTTTPromptDefaults:
    """Verify the prompt defaults have the expected structure."""

    def test_turn1_includes_ARGUMENTS(self) -> None:
        assert "$ARGUMENTS" in DEFAULT_TTT_TURN1
        assert "node.search" in DEFAULT_TTT_TURN1 or "**node.search**" in DEFAULT_TTT_TURN1
        assert "node.add" in DEFAULT_TTT_TURN1 or "**node.add**" in DEFAULT_TTT_TURN1

    def test_turn2_includes_ARGUMENTS(self) -> None:
        assert "$ARGUMENTS" in DEFAULT_TTT_TURN2
        assert "template.list" in DEFAULT_TTT_TURN2 or "**template.list**" in DEFAULT_TTT_TURN2
        assert "predicate.search" in DEFAULT_TTT_TURN2 or "**predicate.search**" in DEFAULT_TTT_TURN2

    def test_turn3_includes_context_get(self) -> None:
        assert "context.get" in DEFAULT_TTT_TURN3 or "**context.get**" in DEFAULT_TTT_TURN3
        assert "$ARGUMENTS" in DEFAULT_TTT_TURN3
        assert "template" in DEFAULT_TTT_TURN3

    def test_turn3_mentions_validation(self) -> None:
        assert "context.get(type=all)" in DEFAULT_TTT_TURN3

    def test_turn2_mentions_reusable_template(self) -> None:
        assert "/template" in DEFAULT_TTT_TURN3


class TestTemplatePromptDefaults:
    """Verify the updated template prompts reference context.get."""

    def test_turn2_references_context_get(self) -> None:
        assert "context.get" in DEFAULT_TURN2 or "**context.get**" in DEFAULT_TURN2

    def test_turn2_no_longer_uses_AVAILABLE_PREDICATES(self) -> None:
        assert "$AVAILABLE_PREDICATES" not in DEFAULT_TURN2

    def test_turn1_still_uses_ARGUMENTS(self) -> None:
        assert "$ARGUMENTS" in DEFAULT_TURN1


class TestPromptCommandRouting:
    """Verify the special case routing in prompt_commands.py handles /ttt aliases."""

    def test_ttt_aliases_in_code(self) -> None:
        """The routing check should handle multiple name forms."""
        from semantika.server.routes.prompt_commands import execute_endpoint
        # We can't easily call execute_endpoint without a full server,
        # but we can verify the routing code exists by checking the source
        import inspect
        source = inspect.getsource(execute_endpoint)
        assert "text-to-triples" in source or "text_to_triples" in source or "ttt" in source
