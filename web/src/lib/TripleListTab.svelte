<script>
  /** Triple list tab — filterable by subject/predicate, API-backed. */

  import { tabStore } from "./tabStore.svelte.js";
  import { banner } from "./bannerStore.svelte.js";
  import { opt } from "./optimisticStore.svelte.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    getLabel,
  } from "./listTabShared.svelte.js";
  import { getLocale } from "./userConfig.svelte.js";

  let { data = [] } = $props();
  let triples = $derived(
    Array.isArray(data) ? data
    : Array.isArray(data?.triples) ? data.triples
    : Array.isArray(data?.data) ? data.data
    : []
  );
  let showSearch = $state(false);
  let searchQuery = $state("");
  let searchTimeout;

  function handleNew() {
    tabStore.open("form", "Add Triple", {
      form: "triple-add", commandPath: ["triple", "add"],
      initialData: { _returnType: "triple-list", _returnTitle: "Triples" },
    }, { idKey: "triple-add" });
  }

  async function fetchTriples(query) {
    try {
      let items;
      if (query && query.length >= 2) {
        const params = new URLSearchParams({ subject: query, limit: "100" });
        const resp = await fetch(`/api/v1/query/triples/search?${params}`);
        if (!resp.ok) return;
        const result = await resp.json();
        items = result.triples || result.results || result.data || result;
      } else {
        const params = new URLSearchParams({ limit: "100" });
        const resp = await fetch(`/api/v1/graph/triples?${params}`);
        if (!resp.ok) return;
        const result = await resp.json();
        items = result.triples || result.results || result.data || result;
      }
      tabStore.update(tabStore.active.id, { triples: items, data: items });
    } catch { /* silent */ }
  }

  function tripleKey(t) {
    return `${t.subject_id}|${t.predicate_id}|${t.object_value}|${t.object_type || "node"}`;
  }

  let sel = createSelectionManager(
    () => triples.map(t => ({ node_id: tripleKey(t) })),
    (key) => {
      const t = triples.find(t => tripleKey(t) === key);
      if (t) openTripleDetail(t);
    },
    async (keys) => {
      // 1. Optimistic removal: remove triples from tab data immediately
      const activeId = tabStore.active?.id;
      const rollback = activeId
        ? opt.removeFromTab(activeId, keys, (t) => tripleKey(t), "triples")
        : () => {};
      // 2. Fire API calls in background
      try {
        for (const key of keys) {
          const t = triples.find(t => tripleKey(t) === key);
          if (t) {
            const params = new URLSearchParams({
              subject: t.subject_id, predicate: t.predicate_id, object: t.object_value,
            });
            const resp = await fetch(`/api/v1/graph/triples?${params}`, { method: "DELETE" });
            if (!resp.ok) {
              const err = await resp.json().catch(() => ({}));
              throw new Error(err.detail?.error || err.detail || `HTTP ${resp.status}`);
            }
          }
        }
      } catch (err) {
        // 3. On failure: rollback + banner error
        rollback();
        banner.show(`Delete failed: ${err.message}`, "error");
        throw err;
      }
    },
    () => {}, // no-op refresh: data already updated optimistically
    { onNew: handleNew, getKey: (item) => item.node_id },
  );

  let uuidCopy = createCopyState();

  async function openNode(id) {
    if (!id) return;
    try {
      const resp = await fetch(`/api/v1/graph/nodes/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const node = result.node || result;
      const label = getLabel(node?.labels, getLocale()) || id;
      tabStore.open("status", label, { ...node, triples: result.triples || [] }, {
        idKey: `node-${id}`, replaceable: false,
      });
    } catch { /* silent */ }
  }

  async function openPredicate(id) {
    if (!id) return;
    try {
      const resp = await fetch(`/api/v1/graph/predicates/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const pred = result.predicate || result;
      const label = getLabel(pred?.labels, getLocale()) || id;
      tabStore.open("status", label, { ...pred, triples: result.triples || [] }, {
        idKey: `pred-${id}`, replaceable: false,
      });
    } catch { /* silent */ }
  }

  async function openTripleDetail(triple) {
    if (!triple) return;
    // Fetch full data for subject, predicate, and object (if node)
    const [subjRes, predRes] = await Promise.all([
      fetch(`/api/v1/graph/nodes/${encodeURIComponent(triple.subject_id)}`).catch(() => null),
      fetch(`/api/v1/graph/predicates/${encodeURIComponent(triple.predicate_id)}`).catch(() => null),
    ]);
    const subjData = subjRes?.ok ? await subjRes.json() : null;
    const predData = predRes?.ok ? await predRes.json() : null;

    let objData = null;
    if (triple.object_type === "node") {
      const objRes = await fetch(`/api/v1/graph/nodes/${encodeURIComponent(triple.object_value)}`).catch(() => null);
      objData = objRes?.ok ? await objRes.json() : null;
    }

    tabStore.open("triple-detail", `${triple.subject_id} → ${triple.predicate_id} → ${triple.object_value}`, {
      triple,
      subject: subjData?.node || subjData || { node_id: triple.subject_id },
      predicate: predData?.predicate || predData || { predicate_id: triple.predicate_id },
      object: objData?.node || objData || { node_id: triple.object_value, _literal: triple.object_type !== "node" ? triple.object_value : null },
      _subject_label: triple._subject_label || triple.subject_id,
      _predicate_label: triple._predicate_label || triple.predicate_id,
      _object_label: triple._object_label || (triple.object_type !== "node" ? triple.object_value : triple.object_value),
    }, { idKey: `triple-${tripleKey(triple)}`, replaceable: false });
  }



  function objectTypeBadge(t) {
    if (t.object_type === "node") return "node";
    if (t.object_datatype === "text/katex") return "katex";
    if (t.object_datatype === "xsd:integer") return "int";
    if (t.object_datatype === "xsd:decimal") return "float";
    if (t.object_datatype === "xsd:boolean") return "bool";
    if (t.object_lang) return t.object_lang;
    return "str";
  }

  function objectTypeClass(t) {
    return "badge-" + objectTypeBadge(t);
  }

  function handleSearchInput(e) {
    const val = e.target.value;
    searchQuery = val;
    clearTimeout(searchTimeout);
    if (val.length === 0 || val.length >= 2) {
      searchTimeout = setTimeout(() => fetchTriples(val), 300);
    }
  }

  function closeSearch() {
    showSearch = false;
    searchQuery = "";
    if (searchQuery.length > 0) fetchTriples("");
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
          if (showSearch) requestAnimationFrame(() => document.querySelector(".tl-search-input")?.focus());
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

<div class="triple-list">
  {#if showSearch}
    <div class="search-bar">
      <input class="tl-search-input" type="text" placeholder="Filter by subject..."
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
      <button class="btn-small" onclick={handleNew}>n New</button>
      <button class="btn-small" onclick={() => { showSearch = true; requestAnimationFrame(() => document.querySelector('.tl-search-input')?.focus()); }}>
        / Search</button>
      <button class="btn-small" onclick={() => sel.toggleSelectionMode()}>v Select</button>
    {/if}
  </div>

  <div class="list" role="listbox" aria-label="Triples" aria-multiselectable="true">
    {#each triples as triple, i (tripleKey(triple))}
      {@const key = tripleKey(triple)}
      {@const subjLabel = triple._subject_label || triple.subject_id}
      {@const predLabel = triple._predicate_label || triple.predicate_id}
      {@const objLabel = triple.object_type === "node" ? (triple._object_label || triple.object_value) : triple.object_value}
      <div id="row-{CSS.escape(key)}" class="row"
        class:selected={sel.isSelected(key)}
        class:focused={i === sel.focusedIndex}
        role="option" aria-selected={sel.isSelected(key)}
        tabindex="-1"
        onclick={(e) => sel.handleRowClick(e, key)}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); sel.handleRowClick(e, key); } }}>
        <span class="label-arc">
          <span class="entity-link s-link" role="button" tabindex="-1" title="Open subject node"
            onclick={(e) => { e.stopPropagation(); openNode(triple.subject_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.subject_id); } }}>
            {subjLabel}
          </span>
          <span class="arrow">→</span>
          <span class="entity-link p-link" role="button" tabindex="-1" title="Open predicate"
            onclick={(e) => { e.stopPropagation(); openPredicate(triple.predicate_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openPredicate(triple.predicate_id); } }}>
            {predLabel}
          </span>
          <span class="arrow">→</span>
          <span class="entity-link o-link" role="button" tabindex="-1"
            title={triple.object_type === "node" ? "Open object node" : ""}
            onclick={(e) => { if (triple.object_type === "node") { e.stopPropagation(); openNode(triple.object_value); } }}
            onkeydown={(e) => { if ((e.key === "Enter" || e.key === " ") && triple.object_type === "node") { e.stopPropagation(); openNode(triple.object_value); } }}>
            {objLabel}
          </span>
        </span>
        <span class="arc-sep"></span>
        <span class="id-arc">
          <span class="entity-link s-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openNode(triple.subject_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.subject_id); } }}>
            {triple.subject_id}
          </span>
          <span class="arrow">→</span>
          <span class="entity-link p-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openPredicate(triple.predicate_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openPredicate(triple.predicate_id); } }}>
            {triple.predicate_id}
          </span>
          <span class="arrow">→</span>
          <span class="entity-link o-link" role="button" tabindex="-1"
            onclick={(e) => { if (triple.object_type === "node") { e.stopPropagation(); openNode(triple.object_value); } }}
            onkeydown={(e) => { if ((e.key === "Enter" || e.key === " ") && triple.object_type === "node") { e.stopPropagation(); openNode(triple.object_value); } }}>
            {triple.object_value}
          </span>
        </span>
        <span class="badge {objectTypeClass(triple)}">{objectTypeBadge(triple)}</span>
        <span class="actions">
          <button class="btn-icon copy-btn" title="Copy key" onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(key); }}>
            {#if uuidCopy.copiedKey === key}
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            {:else}
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><rect x="10" y="10" width="11" height="11" rx="1.5" opacity="0.5"/><rect x="5" y="4" width="11" height="11" rx="1.5"/></svg>
            {/if}
          </button>
        </span>
      </div>
    {:else}
      <p class="empty">No triples.</p>
    {/each}
  </div>

  {#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} triple{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await sel.deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}
</div>

<style>
  .triple-list { display: flex; flex-direction: column; height: 100%; font-family: monospace; font-size: 0.85rem; position: relative; }
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
  .list { flex: 1; overflow-y: auto; padding: 0; }
  .row { display: flex; align-items: center; gap: 0.3rem; padding: 0.3rem 0.75rem; border-bottom: 1px solid #2a2a3e; cursor: pointer; }
  .row:hover { background: #22223a; }
  .row.selected { background: #2a2a4a; }
  .row.focused { outline: 1px solid #7c7c9a; outline-offset: -1px; }
  .label-arc { flex: 1; min-width: 0; display: flex; align-items: center; gap: 0.25rem; overflow: hidden; }
  .id-arc { display: flex; align-items: center; gap: 0.2rem; flex-shrink: 0; max-width: 45%; color: var(--clr-dim); font-size: 0.78rem; overflow: hidden; }
  .arc-sep { flex-shrink: 0; width: 1.5rem; }
  .entity-link { cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 2px; border-radius: 2px; transition: background 0.1s; }
  .entity-link:hover { background: rgba(255,255,255,0.08); text-decoration: underline; }
  .s-link { color: #7cf; font-weight: 600; }
  .p-link { color: #fa7; }
  .o-link { color: #e0e0e0; }
  .id-arc .s-link { color: #5ab; }
  .id-arc .p-link { color: #d85; }
  .id-arc .o-link { color: #aaa; }
  .arrow { color: var(--clr-dim); flex-shrink: 0; }
  .badge { font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; flex-shrink: 0; text-transform: uppercase; }
  .badge-node { background: #1a3a5a; color: #7cf; }
  .badge-str { background: #2a3a2a; color: #7f7; }
  .badge-int { background: #3a2a3a; color: #f7f; }
  .badge-float { background: #3a3a1a; color: #ff7; }
  .badge-bool { background: #2a2a3a; color: #aaf; }
  .badge-katex { background: #3a1a1a; color: #f77; }
  .badge-fr, .badge-en, .badge-de, .badge-es, .badge-eo { background: #2a3a3a; color: #7ff; }
  .actions { flex-shrink: 0; }
  .empty { color: var(--clr-muted); text-align: center; padding: 2rem; }
</style>
