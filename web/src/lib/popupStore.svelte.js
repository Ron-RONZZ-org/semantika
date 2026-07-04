import { tabStore } from "./tabStore.svelte.js";

let _dataCache = $state({
  accounts: [],
  calendars: [],
  contacts: [],
  todos: [],
  journal: [],
  events: [],
  folders: [],
});
let _persistentDataType = $state(null);

function _cacheData(data) {
  if (!data) return;
  const update = {};
  if (data.accounts) update.accounts = data.accounts;
  if (data.calendars) update.calendars = data.calendars;
  if (data.contacts) update.contacts = data.contacts;
  if (data.todos) update.todos = data.todos;
  if (data.entries) update.journal = data.entries;
  if (data.events) update.events = data.events;
  if (data.folders) update.folders = data.folders;
  if (Object.keys(update).length > 0) {
    _dataCache = {
      accounts: update.accounts ?? _dataCache.accounts,
      calendars: update.calendars ?? _dataCache.calendars,
      contacts: update.contacts ?? _dataCache.contacts,
      todos: update.todos ?? _dataCache.todos,
      journal: update.journal ?? _dataCache.journal,
      events: update.events ?? _dataCache.events,
      folders: update.folders ?? _dataCache.folders,
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
    const idKey = type.endsWith("-list") ? type
                : type === "email" ? `email-${data?.uuid}`
                : null;
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
      accounts: data.accounts ?? _dataCache.accounts,
      calendars: data.calendars ?? _dataCache.calendars,
      contacts: data.contacts ?? _dataCache.contacts,
      todos: data.todos ?? _dataCache.todos,
      journal: data.journal ?? _dataCache.journal,
      events: data.events ?? _dataCache.events,
      folders: data.folders ?? _dataCache.folders,
    };
  },
};
