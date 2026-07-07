import { describe, it, expect } from "vitest";
import { parseCommand, hasTrailingSpace, parsePromptCommand } from "../parser.js";

describe("parseCommand", () => {
  it("empty string returns empty tokens and flags", () => {
    const result = parseCommand("");
    expect(result.tokens).toEqual([]);
    expect(result.flags).toEqual({});
  });

  it("! only returns empty tokens since bang is stripped", () => {
    const result = parseCommand("!");
    expect(result.tokens).toEqual([]);
    expect(result.flags).toEqual({});
  });

  it("!node list (no trailing space) — 'list' is partial", () => {
    // Without trailing space, last word is partial (user still typing)
    const result = parseCommand("!node list");
    expect(result.tokens).toEqual(["node"]);
    expect(result.flags).toEqual({});
    expect(result.partial).toBe("list");
  });

  it("!node list (with trailing space) — 'list' is committed", () => {
    const result = parseCommand("!node list ");
    expect(result.tokens).toEqual(["node", "list"]);
    expect(result.flags).toEqual({});
    expect(result.partial).toBe("");
  });

  it("!node add --node-id foo parses flag preserving hyphens", () => {
    const result = parseCommand("!node add --node-id foo");
    expect(result.tokens).toEqual(["node", "add"]);
    // Flag names keep their hyphens — parser does not camelCase
    expect(result.flags).toEqual({ "node-id": "foo" });
  });

  it('!node add --node-id="foo bar" handles double-quoted flag value', () => {
    const result = parseCommand('!node add --node-id="foo bar"');
    expect(result.tokens).toEqual(["node", "add"]);
    expect(result.flags).toEqual({ "node-id": "foo bar" });
  });

  it("handles = syntax for flag assignment", () => {
    const result = parseCommand("!node add --node-id=foo");
    expect(result.tokens).toEqual(["node", "add"]);
    expect(result.flags).toEqual({ "node-id": "foo" });
  });

  it("handles multiple flags", () => {
    const result = parseCommand("!node add --node-id foo --label bar");
    expect(result.tokens).toEqual(["node", "add"]);
    expect(result.flags).toEqual({ "node-id": "foo", label: "bar" });
  });

  it("--flag with a value sets flags entry", () => {
    const result = parseCommand("!graph export --no-optimize true");
    expect(result.tokens).toEqual(["graph", "export"]);
    expect(result.flags).toEqual({ "no-optimize": "true" });
  });

  it("--flag without value at end is partial (not yet committed)", () => {
    const result = parseCommand("!graph export --no-optimize");
    expect(result.tokens).toEqual(["graph", "export"]);
    expect(result.flags).toEqual({});
    expect(result.partial).toBe("--no-optimize");
  });

  it("--flag with trailing space in original input still treated as partial (trimmed away)", () => {
    // input.trim() removes trailing space, so withoutBang has no trailing space
    const result = parseCommand("!graph export --no-optimize ");
    expect(result.tokens).toEqual(["graph", "export"]);
    expect(result.flags).toEqual({});
    expect(result.partial).toBe("--no-optimize");
  });

  it("handles partial token as last unfinished word", () => {
    const result = parseCommand("!node ad");
    expect(result.tokens).toEqual(["node"]);
    expect(result.partial).toBe("ad");
  });

  it("!triple add sub pred 42 with extra tokens and multi-word values", () => {
    // Multiple positional tokens, last is committed due to trailing space
    const result = parseCommand("!triple add sub pred 42 ");
    expect(result.tokens).toEqual(["triple", "add", "sub", "pred", "42"]);
    expect(result.flags).toEqual({});
  });
});

describe("hasTrailingSpace", () => {
  it("returns true when input ends with space", () => {
    expect(hasTrailingSpace("hello ")).toBe(true);
  });

  it("returns false when input ends without space", () => {
    expect(hasTrailingSpace("hello")).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(hasTrailingSpace("")).toBe(false);
  });
});

describe("parsePromptCommand", () => {
  it("parses /weekly 7 productivity", () => {
    const result = parsePromptCommand("/weekly 7 productivity");
    expect(result).toEqual({ name: "weekly", args: ["7", "productivity"] });
  });

  it("parses /weekly with no args", () => {
    const result = parsePromptCommand("/weekly");
    expect(result).toEqual({ name: "weekly", args: [] });
  });

  it("returns null for input without /", () => {
    expect(parsePromptCommand("hello")).toBeNull();
  });

  it("handles // — strips only first /, rest is parsed as name", () => {
    // The parser does not special-case //; it strips the leading / and
    // parses the remainder as a prompt command.
    const result = parsePromptCommand("//not a prompt");
    expect(result).not.toBeNull();
    // The rest after first / is "/not a prompt", which splits into
    // ["/not", "a", "prompt"], so name = "/not"
    expect(result.name).toBe("/not");
    expect(result.args).toEqual(["a", "prompt"]);
  });

  it("handles slash only", () => {
    const result = parsePromptCommand("/");
    expect(result).toEqual({ name: "", args: [] });
  });
});
