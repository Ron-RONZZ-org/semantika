/** Shared keyboard shortcut registry.
 *
 * Ported from lighterbird's ``keyboardShortcuts.svelte.js``.
 */

const _registry = new Map();

export function registerShortcuts(scope, items) {
  let map = _registry.get(scope);
  if (!map) { map = new Map(); _registry.set(scope, map); }
  for (const item of items) map.set(item.key.toLowerCase(), item);
}

export function getAllShortcuts() {
  const groups = new Map();
  groups.set("Navigation", [
    { key: "Alt + 1-9", desc: "Switch to tab by position" },
    { key: "Alt + N/P", desc: "Next / previous tab" },
    { key: "q / Esc", desc: "Close current tab" },
    { key: "i", desc: "Focus command input" },
  ]);
  groups.set("General", [
    { key: "h", desc: "Toggle help overlay" },
    { key: "!command", desc: "Run a command" },
  ]);
  for (const [, map] of _registry) {
    for (const [, shortcut] of map) {
      const category = shortcut.category || "Other";
      if (!groups.has(category)) groups.set(category, []);
      const keyLabel = shortcut.modifiers ? `${shortcut.modifiers} + ${shortcut.key}` : shortcut.key;
      groups.get(category).push({ key: keyLabel, desc: shortcut.desc });
    }
  }
  return [...groups].map(([category, keys]) => ({ category, keys }));
}

export function getScopeShortcuts(scope) {
  const map = _registry.get(scope);
  return map ? [...map.values()] : [];
}

export function normalizeKey(key) { return key.toLowerCase(); }

export function isInputFocused(e) {
  const tag = e.target?.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || e.target?.isContentEditable;
}
