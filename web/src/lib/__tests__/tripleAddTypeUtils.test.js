import { describe, it, expect } from "vitest";
import {
  interpretFlag,
  parseFlagFromValue,
  resolveObjectType,
  OBJECT_TYPE_LABELS,
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
});

// ── OBJECT_TYPE_LABELS ──────────────────────────────────────────────────

describe("OBJECT_TYPE_LABELS", () => {
  it("has labels for all types", () => {
    const expected = { node: "Node", literal: "Str", int: "Int", float: "Float", bool: "Bool", url: "URL", katex: "KaTeX" };
    expect(OBJECT_TYPE_LABELS).toEqual(expected);
  });
});
