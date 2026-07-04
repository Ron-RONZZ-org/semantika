/** Reactive store tracking which open form tabs have unsaved changes.
 *
 * Ported from lighterbird's ``dirtyFormStore.svelte.js``.
 */

let _dirtyForms = $state(new Map());

export const dirtyFormStore = {
  get dirtyForms() { return _dirtyForms; },
  isDirty(tabId) { return _dirtyForms.get(tabId) ?? false; },
  setDirty(tabId, dirty) {
    const next = new Map(_dirtyForms);
    if (dirty) next.set(tabId, true); else next.delete(tabId);
    _dirtyForms = next;
  },
  clear(tabId) {
    const next = new Map(_dirtyForms);
    next.delete(tabId);
    _dirtyForms = next;
  },
  get hasAnyDirty() {
    for (const v of _dirtyForms.values()) if (v) return true;
    return false;
  },
};
