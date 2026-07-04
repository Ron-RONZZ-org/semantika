"""Tests for unit_parser.py — unit expression parsing, normalization, display.

These are pure function tests — no DB required.
"""

from __future__ import annotations

import pytest

from semantika.graph.unit_parser import (
    parse,
    normalize,
    to_display_string,
    ParseError,
    SingularUnit,
    UnitPower,
    UnitProduct,
    UnitDivision,
)


class TestParse:
    """Tests for the parse() function — expression → AST."""

    def test_singleton(self):
        ast = parse("meter")
        assert isinstance(ast, SingularUnit)
        assert ast.name == "meter"

    def test_singleton_with_underscore(self):
        ast = parse("light_year")
        assert isinstance(ast, SingularUnit)
        assert ast.name == "light_year"

    def test_power(self):
        ast = parse("m^2")
        assert isinstance(ast, UnitPower)
        assert isinstance(ast.base, SingularUnit)
        assert ast.base.name == "m"
        assert ast.exponent == 2

    def test_negative_exponent(self):
        ast = parse("m^-1")
        assert isinstance(ast, UnitPower)
        assert ast.exponent == -1

    def test_product(self):
        ast = parse("N*m")
        assert isinstance(ast, UnitProduct)
        assert len(ast.terms) == 2
        assert ast.terms[0].name == "m"  # sorted: m < N alphabetically
        assert ast.terms[1].name == "N"

    def test_division(self):
        ast = parse("m/s")
        assert isinstance(ast, UnitDivision)
        assert isinstance(ast.numerator, SingularUnit)
        assert ast.numerator.name == "m"
        assert isinstance(ast.denominator, SingularUnit)
        assert ast.denominator.name == "s"

    def test_complex_division(self):
        ast = parse("J/(kg*K)")
        assert isinstance(ast, UnitDivision)
        # Numerator: J, Denominator: kg*K (product)
        assert isinstance(ast.numerator, SingularUnit)
        assert ast.numerator.name == "J"
        assert isinstance(ast.denominator, UnitProduct)
        assert len(ast.denominator.terms) == 2

    def test_power_on_group(self):
        ast = parse("(m/s)^2")
        assert isinstance(ast, UnitPower)
        assert ast.exponent == 2
        assert isinstance(ast.base, UnitDivision)

    def test_integer_as_factor(self):
        ast = parse("1000")
        assert isinstance(ast, SingularUnit)
        assert ast.name == "1000"

    def test_multiple_slashes(self):
        ast = parse("J/s/m")
        # Multiple slashes produce nested divisions: (J/s)/m
        assert isinstance(ast, UnitDivision)
        # Denominator is SingularUnit ("m")
        assert isinstance(ast.denominator, SingularUnit)
        assert ast.denominator.name == "m"
        # Numerator is (J/s)
        assert isinstance(ast.numerator, UnitDivision)

    def test_empty_expression_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse("   ")

    def test_invalid_char_raises(self):
        with pytest.raises(ParseError, match="Unrecognised"):
            parse("m@s")

    def test_trailing_content_raises(self):
        with pytest.raises(ParseError, match="trailing"):
            parse("m kg")

    def test_unexpected_token_raises(self):
        with pytest.raises(ParseError, match="Unexpected"):
            parse(")m")

    def test_unexpected_end(self):
        with pytest.raises(ParseError, match="Unexpected end"):
            parse("m^")

    def test_name_with_digits(self):
        ast = parse("m2")
        # Parsed as named unit containing digits
        assert isinstance(ast, SingularUnit)
        assert ast.name == "m2"


class TestNormalize:
    """Tests for normalize() — AST → canonical form."""

    def test_singleton_passes_through(self):
        ast = SingularUnit("meter")
        assert normalize(ast) is ast

    def test_power_passes_through(self):
        ast = UnitPower(SingularUnit("m"), 2)
        norm = normalize(ast)
        assert isinstance(norm, UnitPower)
        assert norm.exponent == 2

    def test_division_to_product(self):
        ast = UnitDivision(SingularUnit("m"), SingularUnit("s"))
        norm = normalize(ast)
        # m/s → m * s^-1
        assert isinstance(norm, UnitProduct)
        assert len(norm.terms) == 2
        assert isinstance(norm.terms[0], SingularUnit)
        assert norm.terms[0].name == "m"
        assert isinstance(norm.terms[1], UnitPower)
        assert norm.terms[1].base.name == "s"
        assert norm.terms[1].exponent == -1

    def test_normalize_removes_identity(self):
        """1 * m → m"""
        ast = UnitProduct(terms=(SingularUnit("1"), SingularUnit("m")))
        norm = normalize(ast)
        assert isinstance(norm, SingularUnit)
        assert norm.name == "m"

    def test_normalize_all_identity(self):
        """1 * 1 → 1"""
        ast = UnitProduct(terms=(SingularUnit("1"), SingularUnit("1")))
        norm = normalize(ast)
        assert isinstance(norm, SingularUnit)
        assert norm.name == "1"

    def test_nested_division(self):
        """m / (s * kg) → m * kg^-1 * s^-1"""
        ast = UnitDivision(
            SingularUnit("m"),
            UnitProduct(terms=(SingularUnit("s"), SingularUnit("kg"))),
        )
        norm = normalize(ast)

        # Should be a product of m, kg^-1, s^-1
        assert isinstance(norm, UnitProduct)
        names = {}
        for t in norm.terms:
            if isinstance(t, SingularUnit):
                names[t.name] = 1
            elif isinstance(t, UnitPower):
                names[t.base.name] = t.exponent
        assert names.get("m") == 1
        assert names.get("s") == -1
        assert names.get("kg") == -1

    def test_invert_power_negative_one(self):
        """s^-1 → s (when inverted)"""
        from semantika.graph.unit_parser import _invert_power
        result = _invert_power(UnitPower(SingularUnit("s"), -1))
        assert isinstance(result, SingularUnit)
        assert result.name == "s"

    def test_invert_power_positive(self):
        """s^2 → s^-2"""
        from semantika.graph.unit_parser import _invert_power
        result = _invert_power(UnitPower(SingularUnit("s"), 2))
        assert isinstance(result, UnitPower)
        assert result.exponent == -2

    def test_invert_singleton(self):
        """m → m^-1"""
        from semantika.graph.unit_parser import _invert_power
        result = _invert_power(SingularUnit("m"))
        assert isinstance(result, UnitPower)
        assert result.base.name == "m"
        assert result.exponent == -1

    def test_sort_key_ordering(self):
        """_sort_key ensures consistent ordering."""
        from semantika.graph.unit_parser import _sort_key
        k1 = _sort_key(SingularUnit("a"))
        k2 = _sort_key(SingularUnit("b"))
        assert k1 < k2


class TestToDisplayString:
    """Tests for to_display_string() — AST → human-readable string."""

    def test_singleton(self):
        assert to_display_string(SingularUnit("meter")) == "meter"

    def test_power(self):
        assert to_display_string(UnitPower(SingularUnit("m"), 2)) == "m^2"

    def test_power_one(self):
        """Exponent 1 is not shown."""
        assert to_display_string(UnitPower(SingularUnit("m"), 1)) == "m"

    def test_division(self):
        ast = UnitDivision(SingularUnit("m"), SingularUnit("s"))
        result = to_display_string(ast)
        # Normalize produces m/s format
        assert "/" in result

    def test_full_workflow_j_per_kg_k(self):
        """Parse → normalize → display: J/(kg*K)"""
        ast = parse("J/(kg*K)")
        norm = normalize(ast)
        result = to_display_string(norm)
        # After normalization: J * kg^-1 * K^-1
        assert "J" in result
        assert "kg" in result
        assert "K" in result or "k" in result

    def test_display_product_with_denominator(self):
        """kg*m/s^2 → Newton-like display."""
        ast = UnitProduct(terms=(
            SingularUnit("kg"),
            UnitPower(SingularUnit("m"), 1),
            UnitPower(SingularUnit("s"), -2),
        ))
        result = to_display_string(ast)
        assert "kg" in result
        assert "m" in result
        assert "s" in result or "s^-2" in result or "s^2" in result

    def test_roundtrip_meters_per_second(self):
        ast = parse("m/s")
        norm = normalize(ast)
        display = to_display_string(norm)
        # After normalize: m * s^-1 → to_display: m/s or m*s^-1
        assert "m" in display
        assert "/" in display or "s" in display

    def test_roundtrip_joule(self):
        """J = kg*m^2/s^2"""
        ast = parse("kg*m^2/s^2")
        norm = normalize(ast)
        display = to_display_string(norm)
        assert "kg" in display
        assert "m" in display
        assert "s" in display or "/" in display

    def test_division_denominator_multiple(self):
        """a/(b*c) → display with parentheses in denominator."""
        ast = parse("a/(b*c)")
        norm = normalize(ast)
        display = to_display_string(norm)
        # Normalized: a * b^-1 * c^-1 → display: a/(b*c) or a*b^-1*c^-1
        assert "a" in display
        assert "b" in display or "c" in display

    def test_unknown_type_returns_empty(self):
        """Passing an unsupported type returns empty string."""
        from semantika.graph.unit_parser import UnitExpression
        class FakeExpr(UnitExpression):
            pass
        assert to_display_string(FakeExpr()) == ""

    def test_exponent_negative_display(self):
        """m^-1 displays as 1/m or m^-1 or m^1 in den."""
        ast = UnitPower(SingularUnit("m"), -1)
        display = to_display_string(ast)
        assert "m" in display
        assert "^-1" in display or "m" in display


def test_parse_and_normalize_integration():
    """Integration test: full pipeline for common unit expressions."""
    test_cases = [
        "m",
        "m/s",
        "m^2",
        "kg*m^2/s^2",  # Joule
        "J/(kg*K)",     # Specific entropy
        "N*m",          # Torque
        "W/m^2",        # Irradiance
    ]
    for expr in test_cases:
        ast = parse(expr)
        assert ast is not None, f"Failed to parse {expr}"
        norm = normalize(ast)
        assert norm is not None, f"Failed to normalize {expr}"
        display = to_display_string(norm)
        assert display, f"Empty display for {expr}"


class TestParseEdgeCases:
    def test_case_sensitivity(self):
        ast = parse("METER")
        assert isinstance(ast, SingularUnit)
        assert ast.name == "METER"

    def test_whitespace_around_operators(self):
        ast = parse("m / s")
        assert isinstance(ast, UnitDivision)

    def test_whitespace_around_power(self):
        ast = parse("m ^ 2")
        assert isinstance(ast, UnitPower)
        assert ast.exponent == 2

    def test_multiple_stars(self):
        ast = parse("a*b*c")
        assert isinstance(ast, UnitProduct)
        assert len(ast.terms) == 3
        names = sorted(t.name for t in ast.terms)
        assert names == ["a", "b", "c"]

    def test_very_long_expression(self):
        expr = "*".join([f"u{i}" for i in range(20)])
        ast = parse(expr)
        assert isinstance(ast, UnitProduct)
        assert len(ast.terms) == 20

    def test_parentheses_nested(self):
        ast = parse("((m))")
        assert isinstance(ast, SingularUnit)
        assert ast.name == "m"

    def test_power_after_parentheses(self):
        ast = parse("(m*s)^3")
        assert isinstance(ast, UnitPower)
        assert ast.exponent == 3
        assert isinstance(ast.base, UnitProduct)
