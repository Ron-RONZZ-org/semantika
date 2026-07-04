/** Tab store — reactive tab state management. */
import { writable, derived } from "svelte/store";

export const tabs = writable([]);
export const activeTabId = writable("home");

export function openTab(type, title, data, opts = {}) {
  const id = opts.id || `${type}-${Date.now()}`;
  const closable = opts.closable !== false;
  const persistent = opts.persistent || false;

  tabs.update((t) => {
    // If persistent and exists, replace
    if (persistent) {
      const existing = t.find((tab) => tab.id === id);
      if (existing) {
        existing.data = data;
        activeTabId.set(id);
        return t;
      }
    }
    const tab = { id, type, title, data, closable, persistent };
    t = [...t, tab];
    activeTabId.set(id);
    return t;
  });
}

export function closeTab(id) {
  tabs.update((t) => t.filter((tab) => tab.id !== id));
  activeTabId.update((current) => (current === id ? "home" : current));
}

export function getTab(id) {
  let found = null;
  tabs.subscribe((t) => { found = t.find((tab) => tab.id === id); })();
  return found;
}
