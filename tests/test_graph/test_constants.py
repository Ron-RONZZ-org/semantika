"""Tests for graph/constants.py — heuristics and FTS5 keyword constants."""

from __future__ import annotations

from semantika.graph.constants import FTS5_KEYWORDS, looks_like_uuid_prefix, is_numeric


class TestFTS5Keywords:
    def test_contains_expected(self):
        assert "AND" in FTS5_KEYWORDS
        assert "OR" in FTS5_KEYWORDS
        assert "NOT" in FTS5_KEYWORDS
        assert "NEAR" in FTS5_KEYWORDS

    def test_is_frozenset(self):
        assert isinstance(FTS5_KEYWORDS, frozenset)

    def test_is_immutable(self):
        """FTS5_KEYWORDS should not be modifiable."""
        try:
            FTS5_KEYWORDS.add("EXTRA")  # type: ignore[attr-defined]
            assert False, "frozenset should not have add()"
        except AttributeError:
            pass


class TestLooksLikeUUIDPrefix:
    def test_valid_8_chars(self):
        assert looks_like_uuid_prefix("a1b2c3d4") is True

    def test_valid_16_chars(self):
        assert looks_like_uuid_prefix("a1b2c3d4e5f6a7b8") is True

    def test_too_short(self):
        assert looks_like_uuid_prefix("abc") is False

    def test_too_long(self):
        assert looks_like_uuid_prefix("a1b2c3d4e5f6a7b8c9") is False

    def test_invalid_chars(self):
        assert looks_like_uuid_prefix("zzzzzzzz") is False

    def test_empty(self):
        assert looks_like_uuid_prefix("") is False

    def test_with_canonical_hyphen(self):
        """Hyphen only allowed after first 8 hex chars (UUID prefix format)."""
        assert looks_like_uuid_prefix("a1b2c3d4-e5f6") is True

    def test_non_canonical_hyphen(self):
        """Hyphen at wrong position is rejected."""
        assert looks_like_uuid_prefix("a1b2-c3d4") is False

    def test_uppercase(self):
        assert looks_like_uuid_prefix("ABCDEF01") is True


class TestIsNumeric:
    def test_integer_string(self):
        assert is_numeric("42") is True

    def test_float_string(self):
        assert is_numeric("3.14") is True

    def test_negative(self):
        assert is_numeric("-10") is True

    def test_scientific_notation(self):
        assert is_numeric("1e5") is True

    def test_non_numeric(self):
        assert is_numeric("hello") is False

    def test_empty_string(self):
        assert is_numeric("") is False

    def test_none(self):
        assert is_numeric(None) is False  # type: ignore[arg-type]

    def test_mixed(self):
        assert is_numeric("123abc") is False

    def test_zero(self):
        assert is_numeric("0") is True
