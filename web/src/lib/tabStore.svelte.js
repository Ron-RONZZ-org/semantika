/** Reactive tab store — manages multiple open tabs, with pinned home tab.
 *
 * Ported from lighterbird's ``tabStore.svelte.js``.
 */

const HOME_TAB = {
  id: "home",
  type: "home",
  title: "Home",
  data: null,
  idKey: "home",
  closable: false,
  pinned: true,
};

let _tabs = $state([HOME_TAB]);
let _activeId = $state(HOME_TAB.id);
let _nextId = 1;

function genId() {
  return `tab-${_nextId++}-${Date.now()}`;
}

export const tabStore = {
  get tabs() { return _tabs; },
  get active() { return _tabs.find((t) => t.id === _activeId) || HOME_TAB; },
  get activeIndex() { return _tabs.findIndex((t) => t.id === _activeId); },
  get count() { return _tabs.length; },

  open(type, title, data, opts = {}) {
    const { idKey, closable = true } = opts;
    if (idKey) {
      const existing = _tabs.find((t) => t.idKey === idKey && t.id !== HOME_TAB.id);
      if (existing) {
        _activeId = existing.id;
        _tabs = _tabs.map((t) => (t.id === existing.id ? { ...t, title, data } : t));
        return existing.id;
      }
    }
    const tab = { id: genId(), type, title, data, idKey: idKey || null, closable, pinned: false };
    const activeIdx = _tabs.findIndex((t) => t.id === _activeId);
    if (activeIdx >= 0) {
      _tabs = [..._tabs.slice(0, activeIdx + 1), tab, ..._tabs.slice(activeIdx + 1)];
    } else {
      _tabs = [..._tabs, tab];
    }
    _activeId = tab.id;
    return tab.id;
  },

  close(id) {
    if (id === HOME_TAB.id) return;
    const idx = _tabs.findIndex((t) => t.id === id);
    if (idx === -1) return;
    const newTabs = _tabs.filter((t) => t.id !== id);
    _tabs = newTabs;
    if (id === _activeId) {
      _activeId = newTabs.length > 0 ? newTabs[Math.min(idx, newTabs.length - 1)].id : HOME_TAB.id;
    }
  },

  setActive(id) { if (_tabs.find((t) => t.id === id)) _activeId = id; },
  setActiveIndex(index) {
    if (index >= 0 && index < _tabs.length) _activeId = _tabs[index].id;
  },
  update(id, data, title) {
    _tabs = _tabs.map((t) => t.id === id ? { ...t, data, ...(title !== undefined ? { title } : {}) } : t);
  },
  closeAll() { _tabs = [HOME_TAB]; _activeId = HOME_TAB.id; },
  goHome() { _activeId = HOME_TAB.id; },
  get isHome() { return _activeId === HOME_TAB.id; },
};
