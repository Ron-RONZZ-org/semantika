<script>
  /** Node list tab — selection, batch delete, focused row, API-backed. */

  import { tabStore } from "./tabStore.svelte.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    getLabel,
  } from "./listTabShared.svelte.js";
  import { getLocale } from "./userConfig.svelte.js";

  let { data = [] } = $props();

  let nodes = $derived(
    Array.isArray(data) ? data
    : Array.isArray(data?.nodes) ? data.nodes
    : Array.isArray(data?.data) ? data.data
    : []
  );
  let showSearch = $state(false);
  let searchQuery = $state("");
  let searchTimeout;

  function handleNew() {
    tabStore.open("form", "Add Node", {
      form: "node-add", commandPath: ["node", "add"],
      initialData: { _returnType: "node-list", _returnTitle: "Nodes" },
    }, { idKey: "node-add" });
  }

  async function fetchNodes(query) {
    try {
      let items;
      if (query && query.length >= 2) {
        const params = new URLSearchParams({ q: query, limit: "100" });
        const resp = await fetch(`/api/v1/graph/nodes/search?${params}`);
        if (!resp.ok) return;
        const result = await resp.json();
        items = result.results || result.data || result;
      } else {
        const params = new URLSearchParams({ limit: "100" });
        const resp = await fetch(`/api/v1/graph/nodes?${params}`);
        if (!resp.ok) return;
        const result = await resp.json();
        items = result.nodes || result.results || result.data || result;
      }
      tabStore.update(tabStore.active.id, { nodes: items, data: items });
    } catch { /* silent */ }
  }

  let sel = createSelectionManager(
    () => nodes,
    (id) => openNode(id),
    async (ids) => {
      for (const id of ids) {
        await fetch(`/api/v1/graph/nodes/${encodeURIComponent(id)}`, { method: "DELETE" });
      }
    },
    () => fetchNodes(searchQuery),
    { onNew: handleNew },
  );

  let uuidCopy = createCopyState();

  async function openNode(id) {
    if (!id) return;
    try {
      const resp = await fetch(`/api/v1/graph/nodes/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const node = await resp.json();
      tabStore.open("status", node.label || id, { nodes: [node], ...node }, {
        idKey: `node-${id}`, replaceable: false,
      });
    } catch { /* silent */ }
  }

  function handleSearchInput(e) {
    const val = e.target.value;
    searchQuery = val;
    clearTimeout(searchTimeout);
    if (val.length === 0 || val.length >= 2) {
      searchTimeout = setTimeout(() => fetchNodes(val), 300);
    }
  }

  function closeSearch() {
    showSearch = false;
    searchQuery = "";
    if (searchQuery.length > 0) fetchNodes("");
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
        if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return; }
        tabStore.close(tabStore.active?.id);
        return;
    }
    sel.handleKeydown(e);
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

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
      <button class="btn-small" onclick={handleNew}>+ New</button>
      <button class="btn-small" onclick={() => { showSearch = true; requestAnimationFrame(() => document.querySelector('.nl-search-input')?.focus()); }}>
        / Search</button>
      <button class="btn-small" onclick={() => sel.toggleSelectionMode()}>v Select</button>
    {/if}
    <span class="hint">{showSearch ? "Esc close" : "/ search \u00b7 n new \u00b7 v select"}</span>
  </div>

  <div class="list" role="listbox" aria-label="Nodes" aria-multiselectable="true">
    {#each nodes as node, i (node.node_id)}
      <div id="row-{CSS.escape(node.node_id)}" class="row"
        class:selected={sel.isSelected(node.node_id)}
        class:focused={i === sel.focusedIndex}
        role="option" aria-selected={sel.isSelected(node.node_id)}
        onclick={(e) => sel.handleRowClick(e, node.node_id)}>
        <span class="label">{getLabel(node.labels, getLocale()) || node.node_id}</span>
        <span class="id">{node.node_id}</span>
        <span class="actions">
          <button class="btn-icon" title="Copy ID" onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(node.node_id); }}>
            {uuidCopy.copiedKey === node.node_id ? "\u2713" : "\u2349"}
          </button>
        </span>
      </div>
    {:else}
      <p class="empty">No nodes.</p>
    {/each}
  </div>

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
  .btn-icon { background: none; border: none; color: var(--clr-sub); cursor: pointer; padding: 0 4px; font-size: 0.85rem; }
  .btn-icon:hover { color: #e0e0e0; }
  .hint { margin-left: auto; color: var(--clr-dim); font-size: 0.68rem; }
  .list { flex: 1; overflow-y: auto; padding: 0; }
  .row { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.75rem; border-bottom: 1px solid #2a2a3e; cursor: pointer; }
  .row:hover { background: #22223a; }
  .row.selected { background: #2a2a4a; }
  .row.focused { outline: 1px solid #7c7c9a; outline-offset: -1px; }
  .label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #e0e0e0; font-weight: 600; }
  .id { color: var(--clr-sub); font-size: 0.78rem; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .actions { flex-shrink: 0; }
  .empty { color: var(--clr-muted); text-align: center; padding: 2rem; }
</style>
