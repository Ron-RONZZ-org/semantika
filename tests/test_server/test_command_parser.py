"""Tests for the server-side command parser — parse_expanded()."""

from __future__ import annotations

import pytest

from semantika.server.command.parser import parse_expanded


class TestParseExpanded:
    """Test the parse_expanded() function."""

    def test_simple_command(self):
        tokens, flags = parse_expanded("!node list")
        assert tokens == ["node", "list"]
        assert flags == {}

    def test_without_bang(self):
        tokens, flags = parse_expanded("node list")
        assert tokens == ["node", "list"]

    def test_strips_whitespace(self):
        tokens, flags = parse_expanded("  !node list  ")
        assert tokens == ["node", "list"]

    def test_empty_string(self):
        tokens, flags = parse_expanded("")
        assert tokens == []
        assert flags == {}

    def test_nothing_after_bang(self):
        tokens, flags = parse_expanded("!")
        assert tokens == []
        assert flags == {}

    def test_positional_args(self):
        tokens, flags = parse_expanded("!node view TESTNODE")
        assert tokens == ["node", "view", "TESTNODE"]
        assert flags == {}

    def test_double_dash_flag_with_value(self):
        tokens, flags = parse_expanded('!node add --labels \'{"en":"Dog"}\'')
        assert tokens == ["node", "add"]
        assert flags == {"labels": '{"en":"Dog"}'}

    def test_double_dash_flag_with_equals(self):
        tokens, flags = parse_expanded('!serci --q=hello --limit=10')
        assert tokens == ["serci"]
        assert flags == {"q": "hello", "limit": "10"}

    def test_double_dash_flag_as_boolean(self):
        tokens, flags = parse_expanded("!serci --details")
        assert tokens == ["serci"]
        assert flags == {"details": "true"}

    def test_short_flag_with_value(self):
        tokens, flags = parse_expanded("!node merge -s SOURCE -t TARGET")
        assert tokens == ["node", "merge"]
        assert flags == {"s": "SOURCE", "t": "TARGET"}

    def test_short_flag_as_boolean(self):
        tokens, flags = parse_expanded("!node delete --soft")
        assert tokens == ["node", "delete"]
        assert flags == {"soft": "true"}

    def test_mixed_positional_and_flags(self):
        tokens, flags = parse_expanded('!node update MYNODE --labels \'{"en":"New"}\'')
        assert tokens == ["node", "update", "MYNODE"]
        assert flags == {"labels": '{"en":"New"}'}

    def test_quoted_strings_with_spaces(self):
        tokens, flags = parse_expanded('!node add --labels "My Label"')
        assert tokens == ["node", "add"]
        assert flags == {"labels": "My Label"}

    def test_consecutive_flags(self):
        tokens, flags = parse_expanded("!cmd --flag1 --flag2 val")
        assert tokens == ["cmd"]
        assert flags == {"flag1": "true", "flag2": "val"}

    def test_flag_after_positional(self):
        tokens, flags = parse_expanded("!cmd pos1 pos2 --flag val")
        assert tokens == ["cmd", "pos1", "pos2"]
        assert flags == {"flag": "val"}

    def test_multiple_values(self):
        tokens, flags = parse_expanded("!node add --labels en::Dog --labels fr::Chien")
        assert tokens == ["node", "add"]
        # shlex doesn't deduplicate, so --labels will appear only once
        assert "labels" in flags

    def test_flag_with_leading_digit_not_confused_with_negative(self):
        tokens, flags = parse_expanded("!cmd --val -1")
        assert tokens == ["cmd"]
        assert flags == {"val": "-1"}

    def test_invalid_quoting_raises(self):
        """When shlex fails (e.g. unmatched quote), raise ValueError."""
        with pytest.raises(ValueError, match="Failed to parse command"):
            parse_expanded("!cmd unclosed'quote")

    def test_flag_with_no_value_after_is_boolean(self):
        tokens, flags = parse_expanded("!cmd --flag")
        assert tokens == ["cmd"]
        assert flags == {"flag": "true"}

    def test_only_flags(self):
        tokens, flags = parse_expanded("!--verbose")
        assert tokens == []
        assert flags == {"verbose": "true"}
