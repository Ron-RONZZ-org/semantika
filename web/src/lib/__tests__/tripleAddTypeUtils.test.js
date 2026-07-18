import { describe, it, expect } from "vitest";
import {
  interpretFlag,
  parseFlagFromValue,
  resolveObjectType,
  OBJECT_TYPE_LABELS,
  getBoolSuggestions,
  getFlagSuggestions,
  TYPE_FLAG_MAP,
} from "../tripleAddTypeUtils.js";

// ── interpretFlag ────────────────────────────────────────────────────────

describe("interpretFlag", () => {
  it("interprets 'string' → literal with no datatype", () => {
    expect(interpretFlag("string")).toEqual({
      object_type: "literal",
      object_datatype: null,
    });
  });

  it("interprets 'str' (abbreviation) same as 'string'", () => {
    expect(interpretFlag("str")).toEqual({
      object_type: "literal",
      object_datatype: null,
    });
  });

  it("interprets 'int' → literal with xsd:integer", () => {
    expect(interpretFlag("int")).toEqual({
      object_type: "literal",
      object_datatype: "xsd:integer",
    });
  });

  it("interprets 'float' → literal with xsd:decimal", () => {
    expect(interpretFlag("float")).toEqual({
      object_type: "literal",
      object_datatype: "xsd:decimal",
    });
  });

  it("interprets 'bool' → literal with xsd:boolean", () => {
    expect(interpretFlag("bool")).toEqual({
      object_type: "literal",
      object_datatype: "xsd:boolean",
    });
  });

  it("interprets 'url' → literal with xsd:anyURI", () => {
    expect(interpretFlag("url")).toEqual({
      object_type: "literal",
      object_datatype: "xsd:anyURI",
    });
  });

  it("interprets 'katex' → literal with text/katex", () => {
    expect(interpretFlag("katex")).toEqual({
      object_type: "literal",
      object_datatype: "text/katex",
    });
  });

  it("is case-insensitive", () => {
    expect(interpretFlag("INT")).toEqual(interpretFlag("int"));
    expect(interpretFlag("Str")).toEqual(interpretFlag("str"));
    expect(interpretFlag("URL")).toEqual(interpretFlag("url"));
  });

  it("returns null for unknown flags", () => {
    expect(interpretFlag("invalid")).toBeNull();
    expect(interpretFlag("")).toBeNull();
    expect(interpretFlag("foobar")).toBeNull();
  });
});

// ── parseFlagFromValue ──────────────────────────────────────────────────

describe("parseFlagFromValue", () => {
  it("returns no flag for empty string", () => {
    expect(parseFlagFromValue("")).toEqual({ flag: null, rest: "" });
  });

  it("returns no flag for plain text", () => {
    expect(parseFlagFromValue("hello")).toEqual({ flag: null, rest: "hello" });
    expect(parseFlagFromValue("Alice")).toEqual({ flag: null, rest: "Alice" });
    expect(parseFlagFromValue("123")).toEqual({ flag: null, rest: "123" });
  });

  it("handles --flag at end with no space (still typing — efficiency hack)", () => {
    // The user is still typing the flag word; no interpretation
    expect(parseFlagFromValue("--int")).toEqual({ flag: null, rest: "--int" });
    expect(parseFlagFromValue("--str")).toEqual({ flag: null, rest: "--str" });
    expect(parseFlagFromValue("--")).toEqual({ flag: null, rest: "--" });
  });

  it("parses --flag followed by space (flag complete)", () => {
    expect(parseFlagFromValue("--int ")).toEqual({ flag: "int", rest: "" });
    expect(parseFlagFromValue("--str ")).toEqual({ flag: "str", rest: "" });
  });

  it("parses --flag followed by space and value", () => {
    expect(parseFlagFromValue("--int 42")).toEqual({ flag: "int", rest: "42" });
    expect(parseFlagFromValue("--str hello")).toEqual({ flag: "str", rest: "hello" });
    expect(parseFlagFromValue("--url https://example.com")).toEqual({
      flag: "url",
      rest: "https://example.com",
    });
  });

  it("parses --flag with multi-word value", () => {
    expect(parseFlagFromValue("--str hello world")).toEqual({
      flag: "str",
      rest: "hello world",
    });
  });

  it("captures unknown flags too", () => {
    expect(parseFlagFromValue("--foobar baz")).toEqual({
      flag: "foobar",
      rest: "baz",
    });
  });

  it("is case-insensitive for the flag word", () => {
    expect(parseFlagFromValue("--INT 42")).toEqual({ flag: "int", rest: "42" });
    expect(parseFlagFromValue("--Str hello")).toEqual({ flag: "str", rest: "hello" });
  });

  it("does NOT match '-- ' (dash-dash-space with no word)", () => {
    expect(parseFlagFromValue("-- ")).toEqual({ flag: null, rest: "-- " });
  });

  it("does NOT match '--int42' (no space between flag and text)", () => {
    // Without a space after the flag word, we consider the user still typing
    expect(parseFlagFromValue("--int42")).toEqual({ flag: null, rest: "--int42" });
    expect(parseFlagFromValue("--strHello")).toEqual({ flag: null, rest: "--strHello" });
  });

  it("does NOT match leading whitespace", () => {
    expect(parseFlagFromValue("  --int 42")).toEqual({ flag: null, rest: "  --int 42" });
  });

  it("does NOT match flags with hyphens in the word", () => {
    // \w+ captures only up to the hyphen, then needs \s+ but gets '-'
    expect(parseFlagFromValue("--flag-with-hyphen val")).toEqual({ flag: null, rest: "--flag-with-hyphen val" });
  });

  it("preserves trailing content including spaces after rest", () => {
    expect(parseFlagFromValue("--int 42 ")).toEqual({ flag: "int", rest: "42 " });
    expect(parseFlagFromValue("--str hello world ")).toEqual({ flag: "str", rest: "hello world " });
  });
});

// ── resolveObjectType ──────────────────────────────────────────────────

describe("resolveObjectType", () => {
  it("returns 'node' for node type", () => {
    expect(resolveObjectType({ object_type: "node", object_datatype: null })).toBe("node");
  });

  it("returns 'literal' for plain string", () => {
    expect(resolveObjectType({ object_type: "literal", object_datatype: null })).toBe("literal");
  });

  it("returns 'int' for xsd:integer", () => {
    expect(resolveObjectType({ object_type: "literal", object_datatype: "xsd:integer" })).toBe("int");
  });

  it("returns 'float' for xsd:decimal", () => {
    expect(resolveObjectType({ object_type: "literal", object_datatype: "xsd:decimal" })).toBe("float");
  });

  it("returns 'bool' for xsd:boolean", () => {
    expect(resolveObjectType({ object_type: "literal", object_datatype: "xsd:boolean" })).toBe("bool");
  });

  it("returns 'url' for xsd:anyURI", () => {
    expect(resolveObjectType({ object_type: "literal", object_datatype: "xsd:anyURI" })).toBe("url");
  });

  it("returns 'katex' for text/katex", () => {
    expect(resolveObjectType({ object_type: "literal", object_datatype: "text/katex" })).toBe("katex");
  });

  it("returns unknown literal type as-is", () => {
    expect(resolveObjectType({ object_type: "literal", object_datatype: "xsd:custom" })).toBe("literal");
  });

  it("returns non-literal object_type directly (e.g. 'url' typed as object_type)", () => {
    // In practice object_type is always "node" or "literal", but the function
    // handles any value defensively
    expect(resolveObjectType({ object_type: "url", object_datatype: null })).toBe("url");
    expect(resolveObjectType({ object_type: "custom", object_datatype: null })).toBe("custom");
  });

  it("returns 'url' for xsd:anyURI even when object_type has unexpected casing", () => {
    // object_type is always lowercase in practice, but the check is strict
    expect(resolveObjectType({ object_type: "literal", object_datatype: "xsd:anyURI" })).toBe("url");
  });
});

// ── Integration: parseFlagFromValue + interpretFlag ─────────────────────

describe("integration: parseFlagFromValue + interpretFlag", () => {
  it("parses and interprets a complete --flag value chain", () => {
    // Simulates what handleObjectInput does
    const testCases = [
      { input: "--string hello", expectedFlag: "string", expectedType: "literal", expectedDt: null, expectedRest: "hello" },
      { input: "--int 42",       expectedFlag: "int", expectedType: "literal", expectedDt: "xsd:integer", expectedRest: "42" },
      { input: "--float 3.14",   expectedFlag: "float", expectedType: "literal", expectedDt: "xsd:decimal", expectedRest: "3.14" },
      { input: "--bool true",    expectedFlag: "bool", expectedType: "literal", expectedDt: "xsd:boolean", expectedRest: "true" },
      { input: "--url https://a.com", expectedFlag: "url", expectedType: "literal", expectedDt: "xsd:anyURI", expectedRest: "https://a.com" },
      { input: "--katex E=mc^2", expectedFlag: "katex", expectedType: "literal", expectedDt: "text/katex", expectedRest: "E=mc^2" },
    ];

    for (const tc of testCases) {
      const { flag, rest } = parseFlagFromValue(tc.input);
      expect(flag).toBe(tc.expectedFlag);
      const typeInfo = interpretFlag(flag);
      expect(typeInfo).not.toBeNull();
      expect(typeInfo.object_type).toBe(tc.expectedType);
      expect(typeInfo.object_datatype).toBe(tc.expectedDt);
      expect(rest).toBe(tc.expectedRest);
    }
  });

  it("handles abbreviation in integration (--str = --string)", () => {
    const { flag, rest } = parseFlagFromValue("--str abbr");
    expect(flag).toBe("str");
    const typeInfo = interpretFlag(flag);
    expect(typeInfo.object_type).toBe("literal");
    expect(typeInfo.object_datatype).toBeNull();
    expect(rest).toBe("abbr");
  });

  it("unknown flag in integration returns null from interpretFlag", () => {
    const { flag, rest } = parseFlagFromValue("--foobar value");
    expect(flag).toBe("foobar");
    const typeInfo = interpretFlag(flag);
    expect(typeInfo).toBeNull();
    expect(rest).toBe("value");
  });

  it("efficiency hack: no space means no parsing", () => {
    const { flag, rest } = parseFlagFromValue("--int");
    expect(flag).toBeNull();
    expect(rest).toBe("--int");
    // interpretFlag is never called because flag is null
  });

  it("efficiency hack: --int (no space) prevents interpretFlag from being called", () => {
    const { flag } = parseFlagFromValue("--int");
    expect(flag).toBeNull(); // No flag → interpretFlag won't be reached
  });

  it("regular node ID value passes through untouched", () => {
    const { flag, rest } = parseFlagFromValue("ALICE");
    expect(flag).toBeNull();
    expect(rest).toBe("ALICE");
    const typeInfo = flag ? interpretFlag(flag) : null;
    expect(typeInfo).toBeNull();
  });
});

// ── OBJECT_TYPE_LABELS ──────────────────────────────────────────────────

describe("OBJECT_TYPE_LABELS", () => {
  it("has labels for all types", () => {
    const expected = { node: "Node", literal: "Str", int: "Int", float: "Float", bool: "Bool", url: "URL", katex: "KaTeX" };
    expect(OBJECT_TYPE_LABELS).toEqual(expected);
  });
});

// ── getBoolSuggestions ────────────────────────────────────────────────────

describe("getBoolSuggestions", () => {
  it("returns true and false suggestions", () => {
    const suggestions = getBoolSuggestions();
    expect(suggestions).toEqual([
      { id: "true", label: "True" },
      { id: "false", label: "False" },
    ]);
  });

  it("returns a fresh array each call", () => {
    expect(getBoolSuggestions()).not.toBe(getBoolSuggestions());
  });
});

// ── getFlagSuggestions ───────────────────────────────────────────────────

describe("getFlagSuggestions", () => {
  it("returns all keys from TYPE_FLAG_MAP prefixed with --", () => {
    const suggestions = getFlagSuggestions();
    const expectedKeys = Object.keys(TYPE_FLAG_MAP).map(k => `--${k}`);
    // Should contain all flag keys (order doesn't matter for contains)
    for (const key of expectedKeys) {
      expect(suggestions).toContain(key);
    }
  });

  it("returns sorted results", () => {
    const suggestions = getFlagSuggestions();
    for (let i = 1; i < suggestions.length; i++) {
      expect(suggestions[i - 1].localeCompare(suggestions[i])).toBeLessThanOrEqual(0);
    }
  });

  it("contains --str and --string (abbreviation and full form)", () => {
    const suggestions = getFlagSuggestions();
    expect(suggestions).toContain("--str");
    expect(suggestions).toContain("--string");
  });

  it("deduplicates entries (no duplicate --flag values)", () => {
    const suggestions = getFlagSuggestions();
    const unique = new Set(suggestions);
    expect(unique.size).toBe(suggestions.length);
  });
});
