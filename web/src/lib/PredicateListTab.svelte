<script>
  /** Predicate list tab — selection, batch delete, infinite scroll, sort. */

  import { tabStore } from "./tabStore.svelte.js";
  import { banner } from "./bannerStore.svelte.js";
  import { opt } from "./optimisticStore.svelte.js";
  import ScrollList from "@lightercore/ui/ScrollList.svelte";
  import { createHighlightManager } from "@lightercore/ui/highlight.svelte.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    getLabel,
  } from "./listTabShared.svelte.js";
  import { getLocale } from "./userConfig.svelte.js";

  let { data = [] } = $props();

  /** All fetched predicates (append-only cumulative list). */
  let allPredicates = $state([]);
  let total = $state(0);
  let hasMore = $state(true);
  let loading = $state(false);
  let pageSize = 50;

  let showSearch = $state(false);
  let searchQuery = $state("");
  let searchTimeout;

  // ── Predicate sort modes ──────────────────────────────────────────────
  const PREDICATE_SORT_MODES = [
    { column: "predicate_id", label: "Alphabetical", direction: "asc", icon: "A" },
    { column: "predicate_id", label: "Alphabetical", direction: "desc", icon: "Z" },
    { column: "created_at",   label: "Date created", direction: "desc", icon: "↓" },
    { column: "created_at",   label: "Date created", direction: "asc", icon: "↑" },
  ];

  let sortIndex = $state(0);
  let sortMode = $derived(PREDICATE_SORT_MODES[sortIndex]);

  function cycleSort() {
    sortIndex = (sortIndex + 1) % PREDICATE_SORT_MODES.length;
  }

  function sortComparator(a, b) {
    const col = sortMode.column;
    let valA, valB;
    if (col === "predicate_id") {
      valA = (a.predicate_id || "").toLowerCase();
      valB = (b.predicate_id || "").toLowerCase();
    } else if (col === "created_at") {
      valA = a.created_at || "";
      valB = b.created_at || "";
    } else {
      valA = String(a[col] ?? "");
      valB = String(b[col] ?? "");
    }
    const cmp = valA < valB ? -1 : valA > valB ? 1 : 0;
    return sortMode.direction === "desc" ? -cmp : cmp;
  }

  /** Visible predicates after sorting. */
  let displayPredicates = $derived(
    allPredicates.toSorted(sortComparator),
  );

  // ── Actions ───────────────────────────────────────────────────────────

  function handleNew() {
    tabStore.open("form", "Add Predicate", {
      form: "predicate-add",
      commandPath: ["predicate", "add"],
      initialData: {},
      returnType: "predicate-list",
      returnTitle: "Predicates",
      returnTokens: ["predicate", "list"],
    }, { idKey: "predicate-add" });
  }

  /** Fetch a page of predicates from the API. */
  async function loadPage(offset) {
    const params = new URLSearchParams({
      limit: String(pageSize),
      offset: String(offset),
      order_by: sortMode.column,
      direction: sortMode.direction,
    });
    try {
      const resp = await fetch(`/api/v1/graph/predicates?${params}`);
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  /** Initial load or re-fetch (reset all). */
  async function resetAndLoad() {
    allPredicates = [];
    total = 0;
    hasMore = true;
    loading = true;
    try {
      const result = await loadPage(0);
      if (result) {
        allPredicates = result.predicates || [];
        total = result.total || 0;
        hasMore = allPredicates.length < total;
      } else {
        hasMore = false;
      }
    } finally {
      loading = false;
    }
  }

  /** Load next page (infinite scroll). */
  async function loadMore() {
    if (loading || !hasMore) return;
    loading = true;
    try {
      const result = await loadPage(allPredicates.length);
      if (result) {
        const newItems = result.predicates || [];
        allPredicates = [...allPredicates, ...newItems];
        total = result.total || 0;
        hasMore = allPredicates.length < total;
      } else {
        hasMore = false;
      }
    } finally {
      loading = false;
    }
  }

  /** Initialize from provided data, or fetch first page. */
  function init() {
    const d = data;
    const items = Array.isArray(d) ? d
      : Array.isArray(d?.predicates) ? d.predicates
      : Array.isArray(d?.data) ? d.data
      : null;
    if (items && items.length > 0) {
      allPredicates = items;
      total = d?.total || items.length;
      hasMore = allPredicates.length < total;
    } else {
      resetAndLoad();
    }
  }

  $effect(init);

  /** Highlight newly created predicate after form submit redirect. */
  createHighlightManager({
    getData: () => data,
    getItems: () => allPredicates,
    idField: "predicate_id",
    rowPrefix: "row-",
  });

  /** Re-fetch when sort mode changes (actual user action, not data reload). */
  $effect(() => {
    const key = `${sortMode.column}|${sortMode.direction}`;
    // Only re-fetch when the sort mode itself changes, not when allPredicates
    // is populated by init() or by a prior fetch response.
    if (allPredicates.length > 0 && key !== _prevSortKey) {
      _prevSortKey = key;
      resetAndLoad();
    }
  });

  async function fetchSearch(query) {
    try {
      const params = new URLSearchParams({ q: query, limit: "100" });
      const resp = await fetch(`/api/v1/graph/predicates/search?${params}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const items = result.results || result.data || result;
      allPredicates = items;
      total = items.length;
      hasMore = false;
    } catch { /* silent */ }
  }

  let sel = createSelectionManager(
    () => displayPredicates,
    (id) => openPredicate(id),
    async (ids) => {
      // 1. Optimistic removal: remove items from tab data immediately
      const activeId = tabStore.active?.id;
      const rollback = activeId
        ? opt.removeFromTab(activeId, ids, (item) => item.predicate_id, "predicates")
        : () => {};
      // 2. Fire API calls in background
      try {
        for (const id of ids) {
          const resp = await fetch(`/api/v1/graph/predicates/${encodeURIComponent(id)}`, { method: "DELETE" });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail?.error || err.detail || `HTTP ${resp.status}`);
          }
        }
        // Remove deleted items from allPredicates
        const deletedSet = new Set(ids);
        allPredicates = allPredicates.filter((p) => !deletedSet.has(p.predicate_id));
      } catch (err) {
        // 3. On failure: rollback + banner error
        rollback();
        banner.show(`Delete failed: ${err.message}`, "error");
        throw err;
      }
    },
    () => {}, // no-op refresh: data already updated optimistically
    { onNew: handleNew, getKey: (item) => item.predicate_id },
  );

  let uuidCopy = createCopyState();

  async function openPredicate(id) {
    if (!id) return;
    try {
      const resp = await fetch(`/api/v1/graph/predicates/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const pred = result.predicate;
      const triples = result.triples || [];
      const label = getLabel(pred?.labels, getLocale()) || id;
      tabStore.open("status", label, { ...pred, triples }, {
        idKey: `pred-${id}`, replaceable: false,
      });
    } catch { /* silent */ }
  }

  function handleSearchInput(e) {
    const val = e.target.value;
    searchQuery = val;
    clearTimeout(searchTimeout);
    if (val.length === 0) {
      resetAndLoad();
      return;
    }
    if (val.length >= 2) {
      searchTimeout = setTimeout(() => fetchSearch(val), 300);
    }
  }

  function closeSearch() {
    showSearch = false;
    searchQuery = "";
    resetAndLoad();
  }

  function handleWindowKeydown(e) {
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return;

    if (sel.confirmDelete) {
      if (e.key === "Escape") { sel.confirmDelete = false; e.preventDefault(); }
      return;
    }

    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
    switch (e.key) {
      case "v":
        if (plain && !sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); }
        return;
      case "s":
        if (plain && !sel.selectionMode && !showSearch) { cycleSort(); e.preventDefault(); }
        return;
      case "/":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".pl-search-input")?.focus());
          else closeSearch();
          e.preventDefault();
        }
        return;
      case "Escape":
        if (showSearch) { closeSearch(); e.preventDefault(); return; }
        if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return; }
        tabStore.close(tabStore.active?.id);
        return;
    }
    sel.handleKeydown(e);
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="predicate-list">
  {#if showSearch}
    <div class="search-bar">
      <input class="pl-search-input" type="text" placeholder="Search predicates..."
        value={searchQuery} oninput={handleSearchInput}
        onkeydown={(e) => { if (e.key === "Escape") { e.stopPropagation(); closeSearch(); } }} />
      <button class="btn-small" onclick={closeSearch}>✕</button>
    </div>
  {/if}

  <div class="toolbar">
    {#if sel.selectionMode}
      <span class="sel-info">{sel.numSelected} selected</span>
      <button class="btn-small" onclick={() => sel.toggleSelectionMode()}>Cancel</button>
      <button class="btn-small danger" onclick={() => { sel.confirmDelete = true; }}
        disabled={sel.numSelected === 0}>Delete</button>
    {:else}
      <button class="btn-small" onclick={handleNew}>+ New</button>
      <button class="btn-small" onclick={() => { showSearch = true; requestAnimationFrame(() => document.querySelector('.pl-search-input')?.focus()); }}>
        / Search</button>
      <button class="btn-small" onclick={() => sel.toggleSelectionMode()}>v Select</button>
      <button class="btn-small btn-sort" onclick={() => cycleSort()} title="Cycle sort mode">
        Sort {sortMode.icon}</button>
    {/if}
  </div>

  <ScrollList
    items={displayPredicates}
    hasMore={hasMore && !showSearch}
    {loading}
    getKey={(p) => p.predicate_id}
    onLoadMore={loadMore}
    emptyMessage="No predicates."
  >
    {#snippet children(predicate, i)}
      <div id="row-{CSS.escape(predicate.predicate_id)}" class="row"
        class:selected={sel.isSelected(predicate.predicate_id)}
        class:focused={i === sel.focusedIndex}
        role="option" aria-selected={sel.isSelected(predicate.predicate_id)}
        tabindex="-1"
        onclick={(e) => sel.handleRowClick(e, predicate.predicate_id)}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); sel.handleRowClick(e, predicate.predicate_id); } }}>
        <span class="label">{getLabel(predicate.labels, getLocale()) || predicate.predicate_id}</span>
        <span class="id">{predicate.predicate_id}</span>
        <span class="actions">
          <button class="btn-icon copy-btn" title="Copy ID" onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(predicate.predicate_id); }}>
            {#if uuidCopy.copiedKey === predicate.predicate_id}
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            {:else}
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><rect x="10" y="10" width="11" height="11" rx="1.5" opacity="0.5"/><rect x="5" y="4" width="11" height="11" rx="1.5"/></svg>
            {/if}
          </button>
        </span>
      </div>
    {/snippet}
  </ScrollList>

  {#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} predicate{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await sel.deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}
</div>

<style>
  .predicate-list { display: flex; flex-direction: column; height: 100%; font-family: monospace; font-size: 0.85rem; position: relative; }
  .search-bar { display: flex; gap: 4px; padding: 0.5rem; border-bottom: 1px solid #333; }
  .search-bar input { flex: 1; padding: 0.3rem 0.5rem; background: #2a2a3e; border: 1px solid #444; border-radius: 4px; color: #e0e0e0; font-family: monospace; }
  .toolbar { display: flex; align-items: center; gap: 6px; padding: 0.4rem 0.75rem; border-bottom: 1px solid #2a2a3e; background: #1a1a2e; flex-shrink: 0; }
  .sel-info { color: var(--clr-sub); font-size: 0.8rem; }
  .btn-small { padding: 0.2rem 0.5rem; background: #2a2a3e; border: 1px solid #444; border-radius: 3px; color: #e0e0e0; cursor: pointer; font-family: monospace; font-size: 0.78rem; }
  .btn-small:hover { background: #3a3a4e; }
  .btn-small.danger { border-color: #a33; color: #f77; }
  .btn-small.danger:hover { background: #3a1a1a; }
  .btn-small:disabled { opacity: 0.4; cursor: default; }
  .btn-small.btn-sort { border-color: #3a5a5a; color: #7cf; }
  .btn-icon { background: none; border: none; color: var(--clr-sub); cursor: pointer; padding: 0 4px; font-size: 0.85rem; }
  .btn-icon:hover { color: #e0e0e0; }
  .row { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.75rem; border-bottom: 1px solid #2a2a3e; cursor: pointer; }
  .row:hover { background: #22223a; }
  .row.selected { background: #2a2a4a; }
  .row.focused { outline: 1px solid #7c7c9a; outline-offset: -1px; }
  .label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #e0e0e0; font-weight: 600; }
  .id { color: var(--clr-sub); font-size: 0.78rem; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .actions { flex-shrink: 0; }

  /* Highlight flash for newly created predicates */
  :global(.hc-highlight-flash) { animation: hc-pulse 2s ease-out; }
  @keyframes hc-pulse { 0%, 100% { background-color: transparent; } 30% { background-color: rgba(60, 180, 75, 0.25); } }
</style>
