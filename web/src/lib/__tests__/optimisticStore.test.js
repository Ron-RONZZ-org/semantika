import { describe, it, expect, vi, beforeEach } from "vitest";

let opt;
let tabStore;

beforeEach(async () => {
  vi.resetModules();
  const mod = await import("../optimisticStore.svelte.js");
  opt = mod.opt;
  const tabMod = await import("../tabStore.svelte.js");
  tabStore = tabMod.tabStore;
});

describe("opt.removeFromTab", () => {
  it("removes items from a plain-array tab and provides working rollback", () => {
    const tabId = tabStore.open("node-list", "Nodes", [
      { node_id: "n1", labels: { en: "Node 1" } },
      { node_id: "n2", labels: { en: "Node 2" } },
      { node_id: "n3", labels: { en: "Node 3" } },
    ]);

    const getKey = (item) => item.node_id;
    const rollback = opt.removeFromTab(tabId, ["n1", "n3"], getKey, "data");

    // Items removed immediately
    const tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data).toHaveLength(1);
    expect(tab.data[0].node_id).toBe("n2");

    // Rollback restores original
    rollback();
    const restored = tabStore.tabs.find((t) => t.id === tabId);
    expect(restored.data).toHaveLength(3);
    expect(restored.data.map((n) => n.node_id)).toEqual(["n1", "n2", "n3"]);
  });

  it("removes items from a {nodes: [...]} tab and provides working rollback", () => {
    const tabId = tabStore.open("node-list", "Nodes", {
      nodes: [
        { node_id: "n1" },
        { node_id: "n2" },
      ],
    });

    const getKey = (item) => item.node_id;
    const rollback = opt.removeFromTab(tabId, ["n1"], getKey, "nodes");

    const tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data.nodes).toHaveLength(1);
    expect(tab.data.nodes[0].node_id).toBe("n2");

    rollback();
    const restored = tabStore.tabs.find((t) => t.id === tabId);
    expect(restored.data.nodes).toHaveLength(2);
  });

  it("removes items from a {data: [...]} wrapped tab", () => {
    const tabId = tabStore.open("node-list", "Nodes", {
      data: [
        { node_id: "n1" },
        { node_id: "n2" },
        { node_id: "n3" },
      ],
    });

    const getKey = (item) => item.node_id;
    const rollback = opt.removeFromTab(tabId, ["n2"], getKey, "data");

    const tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data.data).toHaveLength(2);

    rollback();
    const restored = tabStore.tabs.find((t) => t.id === tabId);
    expect(restored.data.data).toHaveLength(3);
  });

  it("handles non-existent tab id gracefully", () => {
    const rollback = opt.removeFromTab("nonexistent", ["n1"], (item) => item.node_id);
    expect(typeof rollback).toBe("function");
    // Calling the no-op rollback should not throw
    expect(() => rollback()).not.toThrow();
  });

  it("handles empty ids array (no-op remove)", () => {
    tabStore.open("node-list", "Nodes", [
      { node_id: "n1" },
      { node_id: "n2" },
    ]);

    const active = tabStore.active;
    const rollback = opt.removeFromTab(active.id, [], (item) => item.node_id);

    const tab = tabStore.tabs.find((t) => t.id === active.id);
    expect(tab.data).toHaveLength(2);
    // Rollback should be harmless
    expect(() => rollback()).not.toThrow();
  });

  it("rollback restores the exact original order (full snapshot restore)", () => {
    const items = [
      { node_id: "n1" },
      { node_id: "n2" },
      { node_id: "n3" },
      { node_id: "n4" },
    ];
    const tabId = tabStore.open("node-list", "Nodes", items);

    const getKey = (item) => item.node_id;
    const rollback = opt.removeFromTab(tabId, ["n2", "n4"], getKey);

    // Only n1 and n3 remain after optimistic removal
    let tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data.map((n) => n.node_id)).toEqual(["n1", "n3"]);

    // Rollback restores the exact original array (order preserved via snapshot)
    rollback();
    tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data.map((n) => n.node_id)).toEqual(["n1", "n2", "n3", "n4"]);
  });

  it("getKey default (item.node_id) works when field matches", () => {
    const tabId = tabStore.open("predicate-list", "Predicates", [
      { predicate_id: "p1" },
      { predicate_id: "p2" },
    ]);

    const getKey = (item) => item.predicate_id;
    const rollback = opt.removeFromTab(tabId, ["p1"], getKey);

    const tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data).toHaveLength(1);
    expect(tab.data[0].predicate_id).toBe("p2");

    rollback();
    const restored = tabStore.tabs.find((t) => t.id === tabId);
    expect(restored.data).toHaveLength(2);
  });

  it("rollback restores tab closed by then (no error)", () => {
    const tabId = tabStore.open("node-list", "Nodes", [{ node_id: "n1" }]);
    const getKey = (item) => item.node_id;
    const rollback = opt.removeFromTab(tabId, ["n1"], getKey);

    // Close the tab
    tabStore.close(tabId);

    // Rollback should not throw since the tab is gone
    expect(() => rollback()).not.toThrow();
  });
});

describe("opt.mutateTab", () => {
  it("applies a mutation and provides working rollback", () => {
    const tabId = tabStore.open("node-list", "Nodes", { nodes: [{ id: "n1" }], count: 1 });

    const result = opt.mutateTab(tabId, (oldData) => ({
      ...oldData,
      count: 2,
    }));

    let tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data.count).toBe(2);

    result.rollback();
    tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data.count).toBe(1);
  });

  it("returns null for non-existent tab", () => {
    const result = opt.mutateTab("nonexistent", (d) => d);
    expect(result).toBeNull();
  });

  it("mutator receives current data and can replace the entire blob", () => {
    const tabId = tabStore.open("node-list", "Nodes", { nodes: [{ id: "n1" }] });

    opt.mutateTab(tabId, () => ({ nodes: [{ id: "n2" }] }));

    const tab = tabStore.tabs.find((t) => t.id === tabId);
    expect(tab.data.nodes).toHaveLength(1);
    expect(tab.data.nodes[0].id).toBe("n2");
  });
});
