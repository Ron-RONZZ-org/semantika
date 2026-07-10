/**
 * Optimistic update helpers for list tabs.
 *
 * Provides snapshot/rollback utilities for optimistic UI updates.
 * The pattern is:
 *
 *   1. Snapshot current state + apply optimistic change to tab data
 *   2. Fire the API call in the background
 *   3. On success: no-op (UI already reflects the change)
 *   4. On failure: restore from snapshot + show error banner via `onError`
 *
 * Usage (list tab):
 * ```js
 *   import { opt } from "./optimisticStore.svelte.js";
 *
 *   async deleteSelectedFn(ids) {
 *     const rollback = opt.removeFromTab(tabStore.active.id, ids, getKey, "nodes");
 *     try {
 *       for (const id of ids) {
 *         await fetch(`/api/v1/graph/nodes/${id}`, { method: "DELETE" });
 *       }
 *     } catch (err) {
 *       rollback();
 *       banner.show(`Delete failed: ${err.message}`, "error");
 *       throw err; // let the selection manager exit selection mode
 *     }
 *   }
 * ```
 */

import { tabStore } from "./tabStore.svelte.js";

/**
 * Extract items array from a tab's data blob.
 * Handles the common shapes: plain array, `{nodes: [...]}`, `{data: [...]}`.
 *
 * @param {any} data — tab data blob
 * @param {string} field — preferred field name (e.g. "nodes", "predicates", "triples")
 * @returns {Array<object>}
 */
function _extractItems(data, field) {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object") {
    if (Array.isArray(data[field])) return data[field];
    if (Array.isArray(data.data)) return data.data;
  }
  return [];
}

/**
 * Build a new data blob with `replacement` as the items array,
 * preserving the original shape (plain array, `{nodes: [...]}`, etc.).
 *
 * @param {any} original — original tab data blob
 * @param {string} field — preferred field name
 * @param {Array<object>} replacement — the new items array
 * @returns {any} data blob in the same shape as original
 */
function _replaceItems(original, field, replacement) {
  if (Array.isArray(original)) return replacement;
  if (original && typeof original === "object") {
    if (Array.isArray(original[field])) {
      return { ...original, [field]: replacement };
    }
    return { ...original, data: replacement };
  }
  return replacement;
}

export const opt = {
  /**
   * Optimistically remove items from a tab's data array.
   *
   * @param {string} tabId — the tab to update
   * @param {string[]} ids — item identifiers to remove
   * @param {(item: object) => string} getKey — extracts the unique key from an item
   * @param {string} [field="data"] — the field in tab data holding the array
   * @returns {() => void} rollback function — call if the API fails
   */
  removeFromTab(tabId, ids, getKey, field = "data") {
    const tab = tabStore.tabs.find((t) => t.id === tabId);
    if (!tab) return () => {};

    const idSet = new Set(ids);

    // Snapshot the FULL original data blob for rollback (preserves order, shape)
    const originalData = tab.data;

    const items = _extractItems(tab.data, field);
    const remaining = items.filter((item) => !idSet.has(getKey(item)));

    // Apply optimistic update
    tabStore.update(tabId, _replaceItems(tab.data, field, remaining));

    // Return rollback function that restores the original data in full
    return () => {
      const currentTab = tabStore.tabs.find((t) => t.id === tabId);
      if (currentTab) tabStore.update(tabId, originalData);
    };
  },

  /**
   * Apply an arbitrary mutation to a tab's data and provide rollback.
   *
   * @param {string} tabId — the tab to update
   * @param {(oldData: any) => any} mutator — receives a clone of the current data,
   *   must return the new data blob
   * @returns {{ rollback: () => void } | null} — null if tab not found
   */
  mutateTab(tabId, mutator) {
    const tab = tabStore.tabs.find((t) => t.id === tabId);
    if (!tab) return null;

    const oldData = tab.data;
    const newData = mutator(oldData);
    tabStore.update(tabId, newData);

    return {
      rollback: () => {
        const currentTab = tabStore.tabs.find((t) => t.id === tabId);
        if (currentTab) tabStore.update(tabId, oldData);
      },
    };
  },
};
