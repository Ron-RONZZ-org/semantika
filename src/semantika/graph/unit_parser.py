"""Pure expression parser for unit expressions.

Grammar::

    expression  → product ("/" product)*
    product     → factor ("*" factor)*
    factor      → WORD ("^" INTEGER)? | INTEGER | "(" expression ")"

Ported from A-semantika's ``_unit_parser.py`` — pure functions, no DB access.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar


# ── AST node types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class UnitExpression:
    """Base class for unit expression AST nodes."""
    pass


@dataclass(frozen=True)
class SingularUnit(UnitExpression):
    """A named unit (e.g. meter, joule, kelvin)."""
    name: str


@dataclass(frozen=True)
class UnitPower(UnitExpression):
    """A unit raised to an integer power."""
    base: UnitExpression
    exponent: int


@dataclass(frozen=True)
class UnitProduct(UnitExpression):
    """Product of two or more units (flattened, sorted)."""
    terms: tuple[UnitExpression, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class UnitDivision(UnitExpression):
    """Division of numerator by denominator."""
    numerator: UnitExpression
    denominator: UnitExpression


# ── Lexer tokens ────────────────────────────────────────────────────────

_TOKEN_PATTERN = re.compile(r"""
    (?P<WORD>[a-zA-Z_][a-zA-Z0-9_]*)   |
    (?P<INTEGER>-?\d+)                   |
    (?P<STAR>\*)                         |
    (?P<SLASH>/)                         |
    (?P<CARET>\^)                        |
    (?P<LPAREN>\()                       |
    (?P<RPAREN>\))                       |
    (?P<WS>\s+)                          |
    (?P<ERROR>.+?)
""", re.VERBOSE)


class ParseError(ValueError):
    """Raised when a unit expression cannot be parsed."""
    pass


def _tokenize(expr: str) -> list[tuple[str, str]]:
    """Tokenize a unit expression string."""
    tokens: list[tuple[str, str]] = []
    for m in _TOKEN_PATTERN.finditer(expr):
        kind = m.lastgroup
        assert kind is not None
        if kind == "WS":
            continue
        if kind == "ERROR":
            raise ParseError(
                f"Unrecognised character {m.group()!r} in unit expression "
                f"at position {m.start()}"
            )
        tokens.append((kind, m.group()))
    return tokens


# ── Parser ──────────────────────────────────────────────────────────────


class _Parser:
    """Recursive-descent parser for unit expressions."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected_kind: str | None = None) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of expression")
        if expected_kind is not None and tok[0] != expected_kind:
            raise ParseError(f"Expected {expected_kind!r} but got {tok[0]!r} ({tok[1]!r})")
        self.pos += 1
        return tok

    def parse(self) -> UnitExpression:
        left = self._parse_product()
        while self.peek() is not None and self.peek()[0] == "SLASH":
            self.consume("SLASH")
            right = self._parse_product()
            left = UnitDivision(numerator=left, denominator=right)
        return left

    def _parse_product(self) -> UnitExpression:
        factors: list[UnitExpression] = [self._parse_factor()]
        while self.peek() is not None and self.peek()[0] == "STAR":
            self.consume("STAR")
            factors.append(self._parse_factor())
        if len(factors) == 1:
            return factors[0]
        return UnitProduct(terms=_flatten_and_sort(factors))

    def _parse_factor(self) -> UnitExpression:
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of expression")

        if tok[0] == "WORD":
            self.consume("WORD")
            name = tok[1]
            exponent = self._parse_exponent()
            if exponent is not None:
                return UnitPower(SingularUnit(name), exponent)
            return SingularUnit(name)

        if tok[0] == "INTEGER":
            self.consume("INTEGER")
            name = tok[1]
            exponent = self._parse_exponent()
            if exponent is not None:
                return UnitPower(SingularUnit(name), exponent)
            return SingularUnit(name)

        if tok[0] == "LPAREN":
            self.consume("LPAREN")
            inner = self.parse()
            self.consume("RPAREN")
            exponent = self._parse_exponent()
            if exponent is not None:
                return UnitPower(inner, exponent)
            return inner

        raise ParseError(f"Unexpected token {tok[0]!r} ({tok[1]!r})")

    def _parse_exponent(self) -> int | None:
        if self.peek() is not None and self.peek()[0] == "CARET":
            self.consume("CARET")
            tok = self.consume("INTEGER")
            return int(tok[1])
        return None


# ── Normalisation helpers ───────────────────────────────────────────────


def _sort_key(expr: UnitExpression) -> tuple:
    if isinstance(expr, SingularUnit):
        return (0, expr.name.lower())
    if isinstance(expr, UnitPower):
        return (1, _sort_key(expr.base), expr.exponent)
    if isinstance(expr, UnitProduct):
        return (2, tuple(_sort_key(t) for t in expr.terms))
    return (99,)


def _invert_power(expr: UnitExpression) -> UnitExpression:
    if isinstance(expr, UnitPower):
        if expr.exponent == -1:
            return expr.base
        return UnitPower(base=expr.base, exponent=-expr.exponent)
    return UnitPower(base=expr, exponent=-1)


def _flatten_and_sort(factors: list[UnitExpression]) -> tuple[UnitExpression, ...]:
    flat: list[UnitExpression] = []
    for f in factors:
        if isinstance(f, UnitProduct):
            flat.extend(f.terms)
        else:
            flat.append(f)
    flat.sort(key=_sort_key)
    return tuple(flat)


# ── Public API ──────────────────────────────────────────────────────────


def parse(expr: str) -> UnitExpression:
    """Parse a unit expression string into an AST."""
    stripped = expr.strip()
    if not stripped:
        raise ValueError("Cannot parse empty unit expression")
    tokens = _tokenize(stripped)
    if not tokens:
        raise ValueError("Cannot parse empty unit expression")
    parser = _Parser(tokens)
    result = parser.parse()
    if parser.peek() is not None:
        remaining = " ".join(t[1] for t in parser.tokens[parser.pos:])
        raise ParseError(f"Unexpected trailing content: {remaining!r}")
    return result


def normalize(expr: UnitExpression) -> UnitExpression:
    """Return a canonical (normalised) form of a unit expression.

    Converts ``UnitDivision`` to uniform product-of-powers form
    (``a/b → a * b^-1``) for structural deduplication.
    """
    if isinstance(expr, SingularUnit):
        return expr
    if isinstance(expr, UnitPower):
        return UnitPower(base=normalize(expr.base), exponent=expr.exponent)
    if isinstance(expr, UnitProduct):
        terms = _flatten_and_sort([normalize(t) for t in expr.terms])
        filtered = [t for t in terms
                    if not (isinstance(t, SingularUnit) and t.name == "1")]
        if not filtered:
            return SingularUnit("1")
        if len(filtered) == 1:
            return filtered[0]
        return UnitProduct(terms=filtered)
    if isinstance(expr, UnitDivision):
        num = normalize(expr.numerator)
        den = normalize(expr.denominator)
        num_terms = list(num.terms) if isinstance(num, UnitProduct) else [num]
        den_raw = list(den.terms) if isinstance(den, UnitProduct) else [den]
        den_inv = [_invert_power(t) for t in den_raw]
        all_terms = _flatten_and_sort(num_terms + den_inv)
        filtered = [t for t in all_terms
                    if not (isinstance(t, SingularUnit) and t.name == "1")]
        if not filtered:
            return SingularUnit("1")
        if len(filtered) == 1:
            return filtered[0]
        return UnitProduct(terms=filtered)
    return expr


def to_display_string(expr: UnitExpression) -> str:
    """Convert a normalised unit expression to a human-readable string."""
    if isinstance(expr, SingularUnit):
        return expr.name
    if isinstance(expr, UnitPower):
        base = to_display_string(expr.base)
        if expr.exponent == 1:
            return base
        return f"{base}^{expr.exponent}"
    if isinstance(expr, UnitProduct):
        num_parts: list[str] = []
        den_parts: list[str] = []
        for t in expr.terms:
            if isinstance(t, UnitPower) and t.exponent < 0:
                inv = UnitPower(base=t.base, exponent=-t.exponent)
                den_parts.append(to_display_string(inv))
            else:
                num_parts.append(to_display_string(t))
        if not den_parts:
            return "*".join(num_parts)
        num_str = "*".join(num_parts) if num_parts else "1"
        den_str = "*".join(den_parts)
        if len(den_parts) > 1:
            den_str = f"({den_str})"
        return f"{num_str}/{den_str}"
    if isinstance(expr, UnitDivision):
        return to_display_string(normalize(expr))
    return ""
