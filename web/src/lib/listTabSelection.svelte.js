/**
 * Selection + keyboard navigation manager for list tabs.
 *
 * Ported from lighterbird's listTabSelection.svelte.js.
 * Uses Svelte 5 runes ($state, $derived).
 *
 * TODO: Extract to lightercore as shared library.
 */

import { registerShortcuts } from "./keyboardShortcuts.svelte.js";

// Standard list tab shortcuts (registered once globally)
registerShortcuts("list-tab-standard", [
  { key: "v", desc: "Toggle selection mode", category: "List" },
  { key: "n", desc: "New item", category: "List" },
  { key: "Delete", desc: "Delete selected items", category: "List" },
  { key: "/", desc: "Toggle search/filter bar", category: "List" },
  { key: "\u2191/\u2193", desc: "Navigate rows", category: "List" },
  { key: "Space", desc: "Toggle focused item", category: "List" },
  { key: "Esc", desc: "Exit selection mode", category: "List" },
]);

/**
 * Clipboard copy state for any key.
 * Shows `copiedKey` for 1.2s then clears.
 */
export function createCopyState() {
  let copiedKey = $state("");

  function copyToClipboard(key) {
    navigator.clipboard.writeText(key).then(() => {
      copiedKey = key;
      setTimeout(() => {
        if (copiedKey === key) copiedKey = "";
      }, 1200);
    }).catch(() => {});
  }

  return {
    get copiedKey() { return copiedKey; },
    copyToClipboard,
  };
}

/**
 * Create a selection manager for list tabs.
 *
 * @param {() => Array<{node_id?: string, predicate_id?: string}>} getItems
 * @param {(key: string) => void} onOpen Called when user activates an item in view mode
 * @param {(keys: string[]) => Promise<void>} onDeleteSelected
 * @param {() => Promise<void>} onRefresh
 * @param {object} [opts]
 * @param {(e: KeyboardEvent) => boolean} [opts.onBeforeKeydown]
 * @param {() => void} [opts.onNew]
 */
export function createSelectionManager(getItems, onOpen, onDeleteSelected, onRefresh, opts = {}) {
  let selectionMode = $state(false);
  let selectedKeys = $state(new Set());
  let focusedIndex = $state(-1);
  let anchorIndex = $state(-1);
  let confirmDelete = $state(false);

  let numSelected = $derived(selectedKeys.size);

  function getKey(i) {
    const item = getItems()[i];
    return item ? (item.node_id ?? item.predicate_id) : null;
  }

  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      selectedKeys = new Set();
      focusedIndex = -1;
      anchorIndex = -1;
    } else if (getItems().length > 0 && focusedIndex === -1) {
      focusedIndex = 0;
    }
  }

  function toggleItem(key) {
    const next = new Set(selectedKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    selectedKeys = next;
  }

  function isSelected(key) {
    return selectedKeys.has(key);
  }

  function selectRange(from, to) {
    const items = getItems();
    const start = Math.min(from, to);
    const end = Math.max(from, to);
    const next = new Set(selectedKeys);
    for (let i = start; i <= end; i++) {
      const key = getKey(i);
      if (key) next.add(key);
    }
    selectedKeys = next;
  }

  function handleRowClick(e, key) {
    if (selectionMode) {
      if (e.shiftKey && anchorIndex >= 0) {
        const idx = getItems().findIndex((it) => (it.node_id ?? it.predicate_id) === key);
        if (idx >= 0) {
          selectRange(anchorIndex, idx);
          anchorIndex = idx;
        }
      } else {
        toggleItem(key);
        const idx = getItems().findIndex((it) => (it.node_id ?? it.predicate_id) === key);
        if (idx >= 0 && anchorIndex < 0) anchorIndex = idx;
      }
    } else if (onOpen) {
      onOpen(key);
    }
  }

  async function deleteSelected() {
    const keys = [...selectedKeys];
    if (keys.length === 0) return;
    try {
      if (onDeleteSelected) await onDeleteSelected(keys);
      selectedKeys = new Set();
      selectionMode = false;
      if (onRefresh) await onRefresh();
    } catch (err) {
      // Error handling deferred to the caller
    }
  }

  function focusRow(index) {
    const items = getItems();
    if (index < 0) index = 0;
    if (index >= items.length) index = items.length - 1;
    focusedIndex = index;
    const key = getKey(index);
    if (key) {
      const el = document.getElementById(`row-${CSS.escape(key)}`);
      if (el) el.scrollIntoView({ block: "nearest" });
    }
  }

  function handleKeydown(e) {
    if (opts.onBeforeKeydown) {
      if (opts.onBeforeKeydown(e)) return;
    }

    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return;

    if (confirmDelete) {
      if (e.key === "Escape") { confirmDelete = false; e.preventDefault(); }
      return;
    }

    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;

    switch (e.key) {
      case "v":
        if (plain) { toggleSelectionMode(); e.preventDefault(); }
        return;
      case "Escape":
        if (selectionMode) { toggleSelectionMode(); e.preventDefault(); }
        return;
      case "n":
        if (plain && !selectionMode && opts.onNew) {
          opts.onNew();
          e.preventDefault();
        }
        return;
    }

    if (!selectionMode) return;

    const shift = e.shiftKey;
    const items = getItems();

    function navRow(idx) {
      if (shift && anchorIndex >= 0) selectRange(anchorIndex, idx);
      focusRow(idx);
      if (!shift) anchorIndex = idx;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (focusedIndex < items.length - 1) navRow(focusedIndex + 1);
        return;
      case "ArrowUp":
        e.preventDefault();
        if (focusedIndex > 0) navRow(focusedIndex - 1);
        return;
      case "Home":
        e.preventDefault();
        if (shift && anchorIndex >= 0) selectRange(anchorIndex, 0);
        focusRow(0);
        if (!shift) anchorIndex = 0;
        return;
      case "End":
        e.preventDefault();
        if (shift && anchorIndex >= 0) selectRange(anchorIndex, items.length - 1);
        focusRow(items.length - 1);
        if (!shift) anchorIndex = items.length - 1;
        return;
      case " ":
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < items.length) {
          const key = getKey(focusedIndex);
          if (key) toggleItem(key);
          if (anchorIndex < 0) anchorIndex = focusedIndex;
        }
        return;
      case "Delete":
        e.preventDefault();
        if (numSelected > 0) confirmDelete = true;
        return;
    }
  }

  return {
    get selectionMode() { return selectionMode; },
    set selectionMode(v) { selectionMode = v; },
    get selectedKeys() { return selectedKeys; },
    get focusedIndex() { return focusedIndex; },
    get numSelected() { return numSelected; },
    get confirmDelete() { return confirmDelete; },
    set confirmDelete(v) { confirmDelete = v; },

    toggleSelectionMode,
    toggleItem,
    isSelected,
    handleRowClick,
    deleteSelected,
    focusRow,
    handleKeydown,
  };
}
