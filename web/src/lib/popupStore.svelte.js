import { tabStore } from "./tabStore.svelte.js";

let _dataCache = $state({
  nodes: [],
  predicates: [],
  triples: [],
  units: [],
});
let _persistentDataType = $state(null);

function _cacheData(data) {
  if (!data) return;
  const update = {};
  if ("nodes" in data) update.nodes = data.nodes;
  if ("predicates" in data) update.predicates = data.predicates;
  if ("triples" in data) update.triples = data.triples;
  if ("units" in data) update.units = data.units;
  if (Object.keys(update).length > 0) {
    _dataCache = {
      nodes: "nodes" in update ? update.nodes : _dataCache.nodes,
      predicates: "predicates" in update ? update.predicates : _dataCache.predicates,
      triples: "triples" in update ? update.triples : _dataCache.triples,
      units: "units" in update ? update.units : _dataCache.units,
    };
  }
}

function _closeLoadingTabs() {
  const ids = tabStore.tabs.filter((t) => t.type === "loading").map((t) => t.id);
  for (const id of ids) {
    tabStore.close(id);
  }
}

export const popup = {
  get current() {
    const a = tabStore.active;
    if (a && a.type !== "home") return a;
    return null;
  },

  get persistentDataType() {
    return _persistentDataType;
  },

  show(type, title, data) {
    _closeLoadingTabs();
    const idKey = type.endsWith("-list") ? type : null;
    tabStore.open(type, title, data, { idKey });
    _persistentDataType = null;
    _cacheData(data);
  },

  showPersistent(type, title, data, dataType) {
    _closeLoadingTabs();
    tabStore.open(type, title, data, { idKey: `persistent-${dataType}` });
    _persistentDataType = dataType;
    _cacheData(data);
  },

  updatePersistent(data) {
    const active = tabStore.active;
    if (active) {
      tabStore.update(active.id, data);
    }
    _cacheData(data);
  },

  showLoading(title) {
    tabStore.open("loading", title, null, { closable: false });
  },

  close() {
    const active = tabStore.active;
    if (active && active.closable) {
      tabStore.close(active.id);
    }
    _persistentDataType = null;
  },

  get cache() {
    return _dataCache;
  },

  updateCache(data) {
    if (!data) return;
    _dataCache = {
      nodes: "nodes" in data ? data.nodes : _dataCache.nodes,
      predicates: "predicates" in data ? data.predicates : _dataCache.predicates,
      triples: "triples" in data ? data.triples : _dataCache.triples,
      units: "units" in data ? data.units : _dataCache.units,
    };
  },
};
