<script>
  /** Node list tab — selection, batch delete, infinite scroll, sort, filter. */

  import { tabStore } from "./tabStore.svelte.js";
  import { banner } from "./bannerStore.svelte.js";
  import { opt } from "./optimisticStore.svelte.js";
  import ScrollList from "@lightercore/ui/ScrollList.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    getLabel,
  } from "./listTabShared.svelte.js";
  import { getLocale } from "./userConfig.svelte.js";
  import {
    createSortState,
    createFilterState,
  } from "./listSort.svelte.js";

  let { data = [] } = $props();
  let initialData = data;

  /** All fetched nodes (append-only cumulative list). */
  let allNodes = $state([]);
  let total = $state(0);
  let hasMore = $state(true);
  let loading = $state(false);
  let pageSize = 50;

  let showSearch = $state(false);
  let searchQuery = $state("");
  let searchTimeout;
  let showNewDropdown = $state(false);
  let showFilters = $state(false);

  /** Sort state — cycles created_at↓ → created_at↑ → node_id↑ → node_id↓ */
  let sort = createSortState("node_id", "asc");

  /** Filter state — which node categories to show. */
  const FILTER_CATEGORIES = ["seeded", "unit", "concept"];
  let filter = createFilterState(FILTER_CATEGORIES);

  const nodeTypes = [
    { label: "Node (general)", command: ["node", "add", "concept"], formType: "node-add", icon: "\u25CB" },
    { label: "Photo", command: ["node", "add", "photo"], formType: "node-add-photo", icon: "\u{1F5BC}" },
    { label: "Video", command: ["node", "add", "video"], formType: "node-add-video", icon: "\u{1F3AC}" },
    { label: "Document", command: ["node", "add", "file"], formType: "node-add-file", icon: "\u{1F4C4}" },
    { label: "Source Code", command: ["node", "add", "code"], formType: "node-add-code", icon: "\u{1F4BB}" },
  ];

  const BUILTIN_TYPE_IDS = new Set(["PHOTO", "VIDEO", "DOCUMENT", "SOURCE_CODE"]);
  const UNIT_PATTERN = /^(unit:|:UnitType|:SingularUnit|:PrefixedUnit|:CompoundUnit|:UnitProduct|:UnitPower)/;

  /** Classify a node into a filter category. */
  function classifyNode(node) {
    const id = node?.node_id || "";
    if (BUILTIN_TYPE_IDS.has(id)) return "seeded";
    if (UNIT_PATTERN.test(id)) return "unit";
    return "concept";
  }

  /** Visible nodes after filtering and sorting. */
  let displayNodes = $derived(
    allNodes
      .filter((n) => filter.isVisible(classifyNode(n)))
      .toSorted(sort.comparator),
  );

  function handleNew(type) {
    showNewDropdown = false;
    tabStore.open("form", type.label, {
      form: type.formType, commandPath: type.command,
      initialData: { _returnType: "node-list", _returnTitle: "Nodes" },
    }, { idKey: type.formType });
  }

  /** Fetch a page of nodes from the command endpoint. */
  async function loadPage(offset) {
    const params = new URLSearchParams({
      limit: String(pageSize),
      offset: String(offset),
      order_by: sort.mode.column,
      direction: sort.mode.direction,
    });
    try {
      const resp = await fetch(`/api/v1/graph/nodes?${params}`);
      if (!resp.ok) return null;
      const result = await resp.json();
      return result;
    } catch {
      return null;
    }
  }

  /** Initial load or re-fetch (reset all). */
  async function resetAndLoad() {
    allNodes = [];
    total = 0;
    hasMore = true;
    loading = true;
    try {
      const result = await loadPage(0);
      if (result) {
        allNodes = result.nodes || [];
        total = result.total || 0;
        hasMore = allNodes.length < total;
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
      const result = await loadPage(allNodes.length);
      if (result) {
        const newItems = result.nodes || [];
        allNodes = [...allNodes, ...newItems];
        total = result.total || 0;
        hasMore = allNodes.length < total;
      } else {
        hasMore = false;
      }
    } finally {
      loading = false;
    }
  }

  /** Initialize from provided data, or fetch first page. */
  function init() {
    const items = Array.isArray(initialData) ? initialData
      : Array.isArray(initialData?.nodes) ? initialData.nodes
      : Array.isArray(initialData?.data) ? initialData.data
      : null;
    if (items && items.length > 0) {
      allNodes = items;
      total = initialData?.total || items.length;
      hasMore = allNodes.length < total;
    } else {
      resetAndLoad();
    }
  }

  $effect(init);

  /** Re-fetch when sort mode changes. */
  $effect(() => {
    // Read sort.mode to track dependency
    const _mode = sort.mode;
    // Skip initial effect run (init handles that)
    if (allNodes.length > 0) {
      resetAndLoad();
    }
  });

  async function fetchSearch(query) {
    try {
      let items;
      const params = new URLSearchParams({ q: query, limit: "100" });
      const resp = await fetch(`/api/v1/graph/nodes/search?${params}`);
      if (!resp.ok) return;
      const result = await resp.json();
      items = result.results || result.data || result;
      allNodes = items;
      total = items.length;
      hasMore = false;
    } catch { /* silent */ }
  }

  let sel = createSelectionManager(
    () => displayNodes,
    (id) => openNode(id),
    async (ids) => {
      const activeId = tabStore.active?.id;
      const rollback = activeId
        ? opt.removeFromTab(activeId, ids, (item) => item.node_id, "nodes")
        : () => {};
      try {
        for (const id of ids) {
          const resp = await fetch(`/api/v1/graph/nodes/${encodeURIComponent(id)}`, { method: "DELETE" });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail?.error || err.detail || `HTTP ${resp.status}`);
          }
        }
        // Remove deleted items from allNodes
        const deletedSet = new Set(ids);
        allNodes = allNodes.filter((n) => !deletedSet.has(n.node_id));
      } catch (err) {
        rollback();
        banner.show(`Delete failed: ${err.message}`, "error");
        throw err;
      }
    },
    () => {},
    { onNew: () => handleNew(nodeTypes[0]), getKey: (item) => item.node_id },
  );

  let uuidCopy = createCopyState();

  async function openNode(id) {
    if (!id) return;
    try {
      const resp = await fetch(`/api/v1/graph/nodes/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const node = result.node;
      const triples = result.triples || [];
      const label = getLabel(node?.labels, getLocale()) || id;
      tabStore.open("status", label, { ...node, triples }, {
        idKey: `node-${id}`, replaceable: false,
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

  function handleDocClick(e) {
    if (showNewDropdown && !e.target.closest('.new-dropdown-container')) {
      showNewDropdown = false;
    }
    if (showFilters && !e.target.closest('.filter-panel') && !e.target.closest('.btn-filter')) {
      showFilters = false;
    }
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
        if (plain && !sel.selectionMode && !showSearch) { sort.cycle(); e.preventDefault(); }
        return;
      case "f":
        if (plain && !sel.selectionMode && !showSearch) { showFilters = !showFilters; e.preventDefault(); }
        return;
      case "/":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".nl-search-input")?.focus());
          else closeSearch();
          e.preventDefault();
        }
        return;
      case "Escape":
        if (showSearch) { closeSearch(); e.preventDefault(); return; }
        if (showFilters) { showFilters = false; e.preventDefault(); return; }
        if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return; }
        tabStore.close(tabStore.active?.id);
        return;
    }
    sel.handleKeydown(e);
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} onclick={handleDocClick} />

<div class="node-list">
  {#if showSearch}
    <div class="search-bar">
      <input class="nl-search-input" type="text" placeholder="Search nodes..."
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
      <div class="new-dropdown-container">
        <button class="btn-small" onclick={() => { showNewDropdown = !showNewDropdown; }}>+ New ▾</button>
        {#if showNewDropdown}
          <div class="new-dropdown" role="menu">
            {#each nodeTypes as nt}
              <button class="dropdown-item" role="menuitem" onclick={() => handleNew(nt)}>
                <span class="dropdown-icon">{nt.icon}</span>
                <span>{nt.label}</span>
              </button>
            {/each}
          </div>
        {/if}
      </div>
      <button class="btn-small" onclick={() => { showSearch = true; requestAnimationFrame(() => document.querySelector('.nl-search-input')?.focus()); }}>
        / Search</button>
      <button class="btn-small" onclick={() => sel.toggleSelectionMode()}>v Select</button>
      <button class="btn-small btn-sort" onclick={() => sort.cycle()} title="Cycle sort mode">
        Sort {sort.mode.icon}</button>
      <button class="btn-small btn-filter" class:active={showFilters} onclick={() => { showFilters = !showFilters; }}>
        Filter</button>
    {/if}
  </div>

  {#if showFilters}
    <div class="filter-panel">
      <label class="filter-label">
        <input type="checkbox" checked={filter.isVisible("seeded")}
          onchange={() => filter.toggle("seeded")} />
        Seeded (PHOTO, VIDEO, …)
      </label>
      <label class="filter-label">
        <input type="checkbox" checked={filter.isVisible("unit")}
          onchange={() => filter.toggle("unit")} />
        Units
      </label>
      <label class="filter-label">
        <input type="checkbox" checked={filter.isVisible("concept")}
          onchange={() => filter.toggle("concept")} />
        Concepts
      </label>
    </div>
  {/if}

  <ScrollList
    items={displayNodes}
    hasMore={hasMore && !showSearch}
    {loading}
    getKey={(n) => n.node_id}
    onLoadMore={loadMore}
    emptyMessage="No nodes."
  >
    {#snippet children(node, i)}
      <div id="row-{CSS.escape(node.node_id)}" class="row"
        class:selected={sel.isSelected(node.node_id)}
        class:focused={i === sel.focusedIndex}
        role="option" aria-selected={sel.isSelected(node.node_id)}
        tabindex="-1"
        onclick={(e) => sel.handleRowClick(e, node.node_id)}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); sel.handleRowClick(e, node.node_id); } }}>
        <span class="node-type-badge type-{classifyNode(node).charAt(0)}">{classifyNode(node).charAt(0).toUpperCase()}</span>
        <span class="label">{getLabel(node.labels, getLocale()) || node.node_id}</span>
        <span class="id">{node.node_id}</span>
        <span class="actions">
          <button class="btn-icon copy-btn" title="Copy ID" onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(node.node_id); }}>
            {#if uuidCopy.copiedKey === node.node_id}
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
      message="Delete {sel.numSelected} node{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await sel.deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}
</div>

<style>
  .node-list { display: flex; flex-direction: column; height: 100%; font-family: monospace; font-size: 0.85rem; position: relative; }
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
  .btn-small.btn-filter { border-color: #5a4a3a; color: #fa7; }
  .btn-small.btn-filter.active { background: #3a2a1a; border-color: #8a6a3a; }
  .btn-icon { background: none; border: none; color: var(--clr-sub); cursor: pointer; padding: 0 4px; font-size: 0.85rem; }
  .btn-icon:hover { color: #e0e0e0; }
  .row { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.75rem; border-bottom: 1px solid #2a2a3e; cursor: pointer; }
  .row:hover { background: #22223a; }
  .row.selected { background: #2a2a4a; }
  .row.focused { outline: 1px solid #7c7c9a; outline-offset: -1px; }
  .label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #e0e0e0; font-weight: 600; }
  .id { color: var(--clr-sub); font-size: 0.78rem; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .actions { flex-shrink: 0; }
  .new-dropdown-container { position: relative; display: inline-block; }
  .new-dropdown { position: absolute; top: 100%; left: 0; min-width: 180px; background: #1a1a2e; border: 1px solid #444; border-radius: 4px; z-index: 100; margin-top: 2px; padding: 4px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }
  .dropdown-item { display: flex; align-items: center; gap: 8px; width: 100%; padding: 0.3rem 0.75rem; background: none; border: none; color: #e0e0e0; cursor: pointer; font-family: monospace; font-size: 0.78rem; text-align: left; }
  .dropdown-item:hover { background: #2a2a4e; }
  .dropdown-icon { font-size: 0.9rem; width: 20px; text-align: center; }

  /* Filter panel */
  .filter-panel {
    display: flex; gap: 0.5rem; padding: 0.4rem 0.75rem;
    border-bottom: 1px solid #2a2a3e; background: #1e1e34;
    flex-wrap: wrap;
  }
  .filter-label {
    display: flex; align-items: center; gap: 4px;
    color: #e0e0e0; font-size: 0.78rem; cursor: pointer;
  }
  .filter-label input { accent-color: #7c7c9a; }

  /* Node type badge */
  .node-type-badge {
    display: inline-block; width: 16px; height: 16px; line-height: 16px;
    text-align: center; font-size: 0.65rem; font-weight: 700;
    border-radius: 3px; flex-shrink: 0; text-transform: uppercase;
  }
  .type-s { background: #2a4a3a; color: #4f8; }
  .type-u { background: #3a2a4a; color: #a7f; }
  .type-c { background: #2a3a4a; color: #7cf; }
</style>