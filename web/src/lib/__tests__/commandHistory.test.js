import { describe, it, expect, vi, beforeEach } from "vitest";

// Provide localStorage polyfill for node test environment
// (createCommandHistory reads/writes localStorage on init and on push)
if (typeof globalThis.localStorage === "undefined") {
  const store = {};
  globalThis.localStorage = {
    getItem: (key) => store[key] ?? null,
    setItem: (key, value) => { store[key] = String(value); },
    removeItem: (key) => { delete store[key]; },
    clear: () => { Object.keys(store).forEach(k => delete store[k]); },
    get length() { return Object.keys(store).length; },
    key: (i) => Object.keys(store)[i] ?? null,
  };
}

let history;

beforeEach(async () => {
  localStorage.clear();
  vi.resetModules();
  const mod = await import("../commandHistory.svelte.js");
  history = mod.history;
});

describe("history", () => {
  it("entries is initially empty", () => {
    expect(history.entries).toEqual([]);
  });

  it("index is initially -1", () => {
    expect(history.index).toBe(-1);
  });

  it("push adds entry at front", () => {
    history.push("!node list");
    expect(history.entries).toEqual(["!node list"]);
    expect(history.index).toBe(-1);
  });

  it("push prepends newer entries", () => {
    history.push("!node list");
    history.push("!triple add");
    expect(history.entries).toEqual(["!triple add", "!node list"]);
  });

  it("push ignores empty string", () => {
    history.push("!node list");
    history.push("");
    expect(history.entries).toEqual(["!node list"]);
  });

  it("push ignores whitespace-only string", () => {
    history.push("!node list");
    history.push("   ");
    expect(history.entries).toEqual(["!node list"]);
  });

  it("back returns most recent entry", () => {
    history.push("!node list");
    history.push("!triple add");
    expect(history.back()).toBe("!triple add");
  });

  it("back and forward navigate through history", () => {
    history.push("first");
    history.push("second");
    history.push("third");

    // Navigate back through all entries
    expect(history.back()).toBe("third");
    expect(history.back()).toBe("second");
    expect(history.back()).toBe("first");

    // Forward
    expect(history.forward()).toBe("second");
    expect(history.forward()).toBe("third");

    // Forward at newest returns empty string
    expect(history.forward()).toBe("");
  });

  it("back when empty returns empty string", () => {
    expect(history.back()).toBe("");
  });

  it("forward moves forward through history after going back", () => {
    history.push("cmd1");
    history.push("cmd2");
    // entries: ["cmd2", "cmd1"], index: -1

    expect(history.back()).toBe("cmd2"); // index: 0
    expect(history.back()).toBe("cmd1"); // index: 1
    expect(history.forward()).toBe("cmd2"); // index: 0
    expect(history.forward()).toBe(""); // index: -1, at newest
  });

  it("reset sets index back to -1", () => {
    history.push("cmd");
    history.back();
    expect(history.index).toBe(0);
    history.reset();
    expect(history.index).toBe(-1);
  });

  it("push after back resets index", () => {
    history.push("cmd1");
    history.push("cmd2");
    history.back(); // index = 0 (cmd2)
    history.push("cmd3");
    expect(history.index).toBe(-1);
    expect(history.entries[0]).toBe("cmd3");
  });

  it("push caps at 100 entries", () => {
    for (let i = 0; i < 105; i++) {
      history.push(`cmd-${i}`);
    }
    expect(history.entries).toHaveLength(100);
    expect(history.entries[0]).toBe("cmd-104");
    expect(history.entries[99]).toBe("cmd-5");
  });
});
