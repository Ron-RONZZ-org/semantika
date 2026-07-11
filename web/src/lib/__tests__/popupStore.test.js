import { describe, it, expect, vi, beforeEach } from "vitest";

let popup;
let tabStore;

beforeEach(async () => {
  vi.resetModules();
  const popupMod = await import("../popupStore.svelte.js");
  popup = popupMod.popup;
  // Also grab tabStore for direct assertions
  const tabMod = await import("../tabStore.svelte.js");
  tabStore = tabMod.tabStore;
});

describe("popup", () => {
  it("current returns null when home is active", () => {
    expect(popup.current).toBeNull();
  });

  it("show opens a tab with correct type and title", () => {
    popup.show("node-detail", "Node Detail", { nodeId: "n1" });
    expect(popup.current).not.toBeNull();
    expect(popup.current.type).toBe("node-detail");
    expect(popup.current.title).toBe("Node Detail");
    expect(popup.current.data).toEqual({ nodeId: "n1" });
  });

  it("show with -list type sets idKey so subsequent show reuses the tab", () => {
    popup.show("node-list", "Nodes", { nodes: [1] });
    const firstId = popup.current.id;

    popup.show("node-list", "Updated", { nodes: [1, 2] });
    const secondId = popup.current.id;

    expect(secondId).toBe(firstId);
    expect(popup.current.title).toBe("Updated");
    expect(popup.current.data).toEqual({ nodes: [1, 2] });
  });

  it("show without -list type always opens a new tab", () => {
    popup.show("node-detail", "Detail", { nodeId: "n1" });
    const firstId = popup.current.id;

    popup.show("node-detail", "Detail", { nodeId: "n1" });
    const secondId = popup.current.id;

    // Without -list suffix, no idKey is set, so a new tab is created
    expect(firstId).not.toBe(secondId);
    expect(tabStore.tabs).toHaveLength(3); // home + 2 detail tabs
  });

  it("close closes the current popup tab", () => {
    popup.show("node-detail", "Detail", null);
    expect(popup.current).not.toBeNull();
    popup.close();
    expect(popup.current).toBeNull();
    expect(tabStore.active.id).toBe("home");
  });

  it("close does nothing when home is active", () => {
    expect(popup.current).toBeNull();
    popup.close();
    expect(tabStore.active.id).toBe("home");
  });

  it("showPersistent opens tab with persistent idKey", () => {
    popup.showPersistent("chat", "Chat Session", { messages: ["hi"] }, "chat-session");
    expect(popup.current).not.toBeNull();
    expect(popup.current.type).toBe("chat");
    expect(popup.current.title).toBe("Chat Session");
    expect(popup.current.data).toEqual({ messages: ["hi"] });
  });

  it("showPersistent reuses tab for same dataType", () => {
    popup.showPersistent("chat", "Session 1", { msgs: [1] }, "my-chat");
    const firstId = popup.current.id;

    popup.showPersistent("chat", "Session 2", { msgs: [1, 2] }, "my-chat");
    const secondId = popup.current.id;

    expect(secondId).toBe(firstId);
    expect(popup.current.title).toBe("Session 2");
    expect(popup.current.data).toEqual({ msgs: [1, 2] });
  });

  it("cache is initially empty", () => {
    expect(popup.cache).toEqual({});
  });

  it("cache is populated after show with data", () => {
    popup.show("node-list", "Nodes", { nodes: [{ id: "n1", name: "N1" }] });
    expect(popup.cache.nodes).toEqual([{ id: "n1", name: "N1" }]);
  });

  it("cache stores different data types separately", () => {
    popup.show("node-list", "Nodes", {
      nodes: [{ id: "n1" }],
      triples: [{ s: "n1", p: "p1", o: "n2" }],
    });
    expect(popup.cache.nodes).toEqual([{ id: "n1" }]);
    expect(popup.cache.triples).toEqual([{ s: "n1", p: "p1", o: "n2" }]);
    // predicates was never set — only keys present after updateCache
    expect(popup.cache.predicates).toBeUndefined();
  });

  it("updateCache merges new data into cache", () => {
    popup.show("node-list", "Nodes", { nodes: [{ id: "n1" }] });
    popup.updateCache({ predicates: [{ id: "p1" }] });
    expect(popup.cache.nodes).toEqual([{ id: "n1" }]);
    expect(popup.cache.predicates).toEqual([{ id: "p1" }]);
  });

  it("updateCache with no data does nothing", () => {
    const cache = popup.cache;
    popup.updateCache(null);
    expect(popup.cache).toBe(cache);
  });

  it("persistentDataType is set by showPersistent and null by show", () => {
    expect(popup.persistentDataType).toBeNull();

    popup.showPersistent("chat", "Chat", null, "chat-type");
    expect(popup.persistentDataType).toBe("chat-type");

    popup.show("node-list", "Nodes", null);
    expect(popup.persistentDataType).toBeNull();
  });

  it("show closes loading tabs before opening new ones", () => {
    tabStore.open("loading", "Loading...", null, { closable: false });

    // Total should be 2 (home + loading)
    expect(tabStore.tabs).toHaveLength(2);

    popup.show("node-list", "Nodes", null);

    // Loading tab should be gone, only home + new tab
    expect(tabStore.tabs).toHaveLength(2);
    expect(popup.current.type).toBe("node-list");
  });
});
