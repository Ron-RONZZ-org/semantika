import { describe, it, expect, vi, beforeEach } from "vitest";

const mockTree = [
  {
    name: "node",
    description: "Manage nodes",
    params: [],
    flags: [],
    children: [
      {
        name: "add",
        description: "Add a node",
        params: [{ name: "node_id", required: true, type: "string" }],
        flags: [{ name: "label", short: "l", type: "string", help: "Node label" }],
      },
      {
        name: "list",
        description: "List nodes",
        params: [{ name: "limit", required: false, type: "number" }],
        flags: [{ name: "format", short: "f", type: "string", help: "Output format" }],
      },
      {
        name: "delete",
        description: "Delete a node",
        params: [{ name: "node_id", required: true, type: "string" }],
        flags: [],
      },
    ],
  },
  {
    name: "note",
    description: "Manage notes",
    params: [],
    flags: [],
    children: [
      { name: "add", description: "Add a note", params: [], flags: [] },
    ],
  },
  {
    name: "triple",
    description: "Manage triples",
    params: [],
    flags: [],
    children: [
      { name: "add", description: "Add triple", params: [], flags: [] },
      { name: "list", description: "List triples", params: [], flags: [] },
    ],
  },
  {
    name: "export",
    description: "Export graph",
    params: [{ name: "format", required: false, type: "string" }],
    flags: [
      { name: "format", short: "f", type: "string", help: "Export format" },
      { name: "no-optimize", type: "boolean", help: "Skip optimization" },
    ],
  },
];

const mockPromptCommands = [
  { name: "summarize", description: "Summarize recent activity" },
  { name: "weekly", description: "Weekly review" },
];

let getCompletions;
let getPromptCompletions;

beforeEach(async () => {
  vi.resetModules();
  globalThis.fetch = vi.fn((url) => {
    if (url === "/api/v1/command/tree") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockTree) });
    }
    if (url === "/api/v1/prompt-commands/list") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockPromptCommands) });
    }
    return Promise.resolve({ ok: false });
  });

  const engine = await import("../commandEngine.js");
  getCompletions = engine.getCompletions;
  getPromptCompletions = engine.getPromptCompletions;

  // Wait for async init functions (initCommandTree, initPromptCommands) to complete
  await vi.waitFor(
    () => {
      const result = getCompletions("!");
      if (result.completions.length === 0) throw new Error("Tree not yet initialized");
    },
    { timeout: 2000, interval: 50 },
  );
});

describe("getCompletions", () => {
  it("! returns all root commands with ! prefix", () => {
    const result = getCompletions("!");
    expect(result.completions).toContain("!node");
    expect(result.completions).toContain("!triple");
    expect(result.completions).toContain("!note");
    expect(result.completions).toContain("!export");
    expect(result.level).toBe("root");
  });

  it("!no matches commands starting with 'no'", () => {
    const result = getCompletions("!no");
    expect(result.completions).toContain("!node");
    expect(result.completions).toContain("!note");
    expect(result.level).toBe("root");
    // Should NOT include unrelated commands
    expect(result.completions).not.toContain("!triple");
  });

  it("!node (trailing space) returns children of node", () => {
    const result = getCompletions("!node ");
    expect(result.completions).toContain("add");
    expect(result.completions).toContain("list");
    expect(result.completions).toContain("delete");
    expect(result.level).toBe("child");
  });

  it("!node ad matches child commands starting with 'ad'", () => {
    const result = getCompletions("!node ad");
    expect(result.completions).toEqual(["add"]);
    expect(result.level).toBe("child");
  });

  it("!node list -- shows flag suggestions", () => {
    const result = getCompletions("!node list --");
    expect(result.completions).toContain("--format");
    expect(result.level).toBe("params");
  });

  it("!node list --f filters flag suggestions by prefix", () => {
    const result = getCompletions("!node list --f");
    expect(result.completions).toEqual(["--format"]);
    expect(result.level).toBe("params");
  });

  it("!node add -- shows flags for add command", () => {
    const result = getCompletions("!node add --");
    expect(result.completions).toContain("--label");
    expect(result.level).toBe("params");
  });

  it("returns empty completions for unknown command", () => {
    const result = getCompletions("!unknown");
    expect(result.completions).toEqual([]);
  });

  it("returns empty completions for unmatched flag prefix", () => {
    // !node list --x where no flag starts with "x"
    const result = getCompletions("!node list --x");
    expect(result.completions).toEqual([]);
    expect(result.level).toBe("params");
  });

  it("!node list (partial) suggests completing 'list'", () => {
    // "list" is a partial (no trailing space), so it matches as a child
    const result = getCompletions("!node list");
    expect(result.completions).toEqual(["list"]);
    expect(result.level).toBe("child");
  });

  it("!/ returns no completions (virtual / node was removed)", () => {
    // The virtual / node was removed from commandTree so typing !/
    // should not suggest prompt commands in ! mode.
    const result = getCompletions("!/");
    expect(result.completions).toEqual([]);
  });
});

describe("getPromptCompletions", () => {
  it("/ returns all prompt commands", () => {
    const result = getPromptCompletions("/");
    expect(result.completions).toContain("/summarize");
    expect(result.completions).toContain("/weekly");
  });

  it("/sum matches prompt commands starting with 'sum'", () => {
    const result = getPromptCompletions("/sum");
    expect(result.completions).toEqual(["/summarize"]);
  });

  it("returns empty for exact match (no exact re-suggestion)", () => {
    const result = getPromptCompletions("/summarize");
    expect(result.completions).toEqual([]);
  });

  it("returns empty for non-prompt input", () => {
    const result = getPromptCompletions("hello");
    expect(result.completions).toEqual([]);
    expect(result.hints).toEqual([]);
  });
});
