import { describe, it, expect, vi, beforeEach } from "vitest";

let tabStore;

beforeEach(async () => {
  vi.resetModules();
  const mod = await import("../tabStore.svelte.js");
  tabStore = mod.tabStore;
});

describe("tabStore", () => {
  it("tabs starts with home tab only", () => {
    expect(tabStore.tabs).toHaveLength(1);
    expect(tabStore.tabs[0].id).toBe("home");
    expect(tabStore.tabs[0].type).toBe("home");
    expect(tabStore.tabs[0].title).toBe("Home");
    expect(tabStore.tabs[0].closable).toBe(false);
    expect(tabStore.tabs[0].pinned).toBe(true);
  });

  it("active returns home tab initially", () => {
    expect(tabStore.active.id).toBe("home");
    expect(tabStore.active.title).toBe("Home");
    expect(tabStore.active.type).toBe("home");
  });

  it("activeIndex is 0 for home", () => {
    expect(tabStore.activeIndex).toBe(0);
  });

  it("count is 1 initially", () => {
    expect(tabStore.count).toBe(1);
  });

  it("isHome is true when home is active", () => {
    expect(tabStore.isHome).toBe(true);
  });

  it("open creates a new tab and sets it active", () => {
    const id = tabStore.open("node-list", "Nodes", { nodes: [1, 2] });
    expect(tabStore.tabs).toHaveLength(2);
    expect(tabStore.active.id).toBe(id);
    expect(tabStore.active.type).toBe("node-list");
    expect(tabStore.active.title).toBe("Nodes");
    expect(tabStore.active.data).toEqual({ nodes: [1, 2] });
    expect(tabStore.active.closable).toBe(true);
    expect(tabStore.active.pinned).toBe(false);
    expect(id).toMatch(/^tab-/);
  });

  it("open inserts new tab AFTER the active tab", () => {
    // Open first tab after home
    const id1 = tabStore.open("type-a", "Tab A", null);
    expect(tabStore.tabs.map((t) => t.id)).toEqual(["home", id1]);

    // Open second tab — it should be inserted after the active tab (id1)
    const id2 = tabStore.open("type-b", "Tab B", null);
    expect(tabStore.tabs.map((t) => t.id)).toEqual(["home", id1, id2]);

    // Switch to home and open tab C — should be inserted after home (index 0)
    tabStore.goHome();
    const id3 = tabStore.open("type-c", "Tab C", null);
    expect(tabStore.tabs.map((t) => t.id)).toEqual(["home", id3, id1, id2]);
  });

  it("open with idKey reuses existing tab with same idKey", () => {
    const id1 = tabStore.open("node-list", "Nodes", { nodes: [1] }, { idKey: "mylist" });
    const id2 = tabStore.open("node-list", "Updated Nodes", { nodes: [1, 2] }, { idKey: "mylist" });
    expect(id2).toBe(id1);
    expect(tabStore.tabs).toHaveLength(2);
    expect(tabStore.active.title).toBe("Updated Nodes");
    expect(tabStore.active.data).toEqual({ nodes: [1, 2] });
  });

  it("open with idKey creates new tab when idKey does not exist", () => {
    const id1 = tabStore.open("node-list", "Nodes", { nodes: [1] }, { idKey: "list-a" });
    const id2 = tabStore.open("unit-list", "Units", { units: ["u1"] }, { idKey: "list-b" });
    expect(id1).not.toBe(id2);
    expect(tabStore.tabs).toHaveLength(3);
  });

  it("close removes a tab", () => {
    const id = tabStore.open("node-list", "Nodes", null);
    expect(tabStore.tabs).toHaveLength(2);
    tabStore.close(id);
    expect(tabStore.tabs).toHaveLength(1);
    expect(tabStore.tabs[0].id).toBe("home");
  });

  it("close on non-existent tab does nothing", () => {
    const startLen = tabStore.tabs.length;
    tabStore.close("nonexistent-id");
    expect(tabStore.tabs).toHaveLength(startLen);
  });

  it("close on home tab does nothing", () => {
    tabStore.close("home");
    expect(tabStore.tabs).toHaveLength(1);
    expect(tabStore.active.id).toBe("home");
  });

  it("closing active tab switches to nearest tab", () => {
    const id1 = tabStore.open("type-a", "Tab A", null);
    const id2 = tabStore.open("type-b", "Tab B", null);

    // Close active tab (id2) — should switch to id1 (nearest)
    expect(tabStore.active.id).toBe(id2);
    tabStore.close(id2);
    expect(tabStore.active.id).toBe(id1);
  });

  it("closing the only non-home tab switches back to home", () => {
    const id = tabStore.open("node-list", "Nodes", null);
    expect(tabStore.active.id).toBe(id);
    tabStore.close(id);
    expect(tabStore.active.id).toBe("home");
    expect(tabStore.isHome).toBe(true);
  });

  it("setActive switches to an existing tab by id", () => {
    const id = tabStore.open("node-list", "Nodes", null);
    expect(tabStore.active.id).toBe(id);
    tabStore.setActive("home");
    expect(tabStore.active.id).toBe("home");
    tabStore.setActive(id);
    expect(tabStore.active.id).toBe(id);
  });

  it("setActive does nothing for invalid id", () => {
    tabStore.setActive("nonexistent");
    expect(tabStore.active.id).toBe("home");
  });

  it("setActiveIndex switches by index", () => {
    const id = tabStore.open("node-list", "Nodes", null);
    tabStore.setActiveIndex(0);
    expect(tabStore.active.id).toBe("home");
    tabStore.setActiveIndex(1);
    expect(tabStore.active.id).toBe(id);
  });

  it("setActiveIndex does nothing for out-of-range index", () => {
    const initial = tabStore.active.id;
    tabStore.setActiveIndex(-1);
    expect(tabStore.active.id).toBe(initial);
    tabStore.setActiveIndex(99);
    expect(tabStore.active.id).toBe(initial);
  });

  it("update modifies existing tab data and title", () => {
    const id = tabStore.open("node-list", "Nodes", { nodes: [1] });
    tabStore.update(id, { nodes: [1, 2, 3] }, "Updated Nodes");
    const tab = tabStore.tabs.find((t) => t.id === id);
    expect(tab.data).toEqual({ nodes: [1, 2, 3] });
    expect(tab.title).toBe("Updated Nodes");
  });

  it("update preserves tab type and id", () => {
    const id = tabStore.open("node-list", "Nodes", { nodes: [1] });
    tabStore.update(id, { nodes: [2] });
    const tab = tabStore.tabs.find((t) => t.id === id);
    expect(tab.type).toBe("node-list");
    expect(tab.id).toBe(id);
  });

  it("closeAll resets to just home tab", () => {
    tabStore.open("type-a", "Tab A", null);
    tabStore.open("type-b", "Tab B", null);
    expect(tabStore.count).toBe(3);
    tabStore.closeAll();
    expect(tabStore.tabs).toHaveLength(1);
    expect(tabStore.tabs[0].id).toBe("home");
    expect(tabStore.active.id).toBe("home");
  });

  it("goHome sets home as active", () => {
    tabStore.open("node-list", "Nodes", null);
    expect(tabStore.isHome).toBe(false);
    tabStore.goHome();
    expect(tabStore.isHome).toBe(true);
    expect(tabStore.active.id).toBe("home");
  });
});
