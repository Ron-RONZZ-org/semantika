<script>
  /**
   * Tab showing all customizable prompt files with edit/reset actions.
   *
   * Props:
   *   data (optional) — pre-fetched prompt list
   */
  import { banner } from "./bannerStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";

  let { data = null } = $props();

  /** @type {Array<{name:string, relative_path:string, category:string, exists:boolean, is_modified:boolean, path:string}>} */
  let prompts = $state(data?.prompts || []);
  let loading = $state(!data);
  let error = $state("");

  /** @type {string|null} */
  let editingName = $state(null);
  let editingContent = $state("");
  let editingDefault = $state("");
  let saving = $state(false);

  // Fetch prompts on mount if not provided
  if (!data) {
    fetchPrompts();
  }

  async function fetchPrompts() {
    loading = true;
    error = "";
    try {
      const resp = await fetch("/api/v1/llm/prompts/list");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      prompts = await resp.json();
    } catch (err) {
      error = err.message || String(err);
      prompts = [];
    } finally {
      loading = false;
    }
  }

  async function handleReset(name) {
    if (!confirm(`Reset "${name}" to its default content?`)) return;
    try {
      const resp = await fetch(`/api/v1/llm/prompts/${encodeURIComponent(name)}/reset`, {
        method: "POST",
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      banner.show(`Prompt "${name}" reset to default`, "success");
      await fetchPrompts(); // refresh list
    } catch (err) {
      banner.show(`Reset failed: ${err.message}`, "error", 5000);
    }
  }

  async function handleResetAll() {
    if (!confirm("Reset ALL prompt files to their defaults?")) return;
    try {
      const resp = await fetch("/api/v1/llm/prompts/list");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const all = await resp.json();
      for (const p of all) {
        if (p.is_modified) {
          await fetch(`/api/v1/llm/prompts/${encodeURIComponent(p.name)}/reset`, {
            method: "POST",
          });
        }
      }
      banner.show("All prompts reset to defaults", "success");
      await fetchPrompts();
    } catch (err) {
      banner.show(`Reset all failed: ${err.message}`, "error", 5000);
    }
  }

  function startEdit(p) {
    editingName = p.name;
    editingDefault = null; // we don't fetch default here
    openEditDialog(p.name);
  }

  async function openEditDialog(name) {
    try {
      const resp = await fetch(`/api/v1/llm/prompts/${encodeURIComponent(name)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      editingName = name;
      editingContent = data.current || data.default;
      editingDefault = data.default;
    } catch (err) {
      banner.show(`Failed to load prompt: ${err.message}`, "error", 5000);
      editingName = null;
    }
  }

  async function handleSave() {
    if (!editingName) return;
    saving = true;
    try {
      const resp = await fetch(`/api/v1/llm/prompts/${encodeURIComponent(editingName)}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editingContent }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      banner.show(`Prompt "${editingName}" saved`, "success");
      editingName = null;
      await fetchPrompts();
    } catch (err) {
      banner.show(`Save failed: ${err.message}`, "error", 5000);
    } finally {
      saving = false;
    }
  }

  function cancelEdit() {
    editingName = null;
  }

  function handleView(name) {
    tabStore.open({ type: "status", title: `Prompt: ${name}`, data: {} });
    // Load via command instead
    const { execute } = import.meta.glob("/lib/commandExecutor.js", { eager: true });
    execute(`!llm prompt view ${name}`);
  }

  let modifiedCount = $derived(prompts.filter(p => p.is_modified).length);
  let totalCount = $derived(prompts.length);
</script>

<div class="prompt-list-tab">
  <div class="list-header">
    <h3>Custom Prompt Files</h3>
    <div class="header-actions">
      {#if modifiedCount > 0}
        <button class="btn btn-reset-all" onclick={handleResetAll} title="Reset all modified prompts to defaults">
          Reset All Modified
        </button>
      {/if}
      <span class="badge" class:has-modified={modifiedCount > 0}>
        {modifiedCount}/{totalCount} modified
      </span>
    </div>
  </div>

  {#if loading}
    <p class="loading">Loading prompts…</p>
  {:else if error}
    <p class="error">Error: {error}</p>
  {:else if prompts.length === 0}
    <p class="empty">No prompts registered.</p>
  {:else}
    <div class="prompt-table">
      {#each prompts as p (p.name)}
        <div class="prompt-row" class:row-modified={p.is_modified}>
          <div class="prompt-info">
            <span class="prompt-name">{p.name}</span>
            <span class="prompt-category">{p.category}</span>
            <span class="prompt-path">{p.relative_path}</span>
          </div>
          <div class="prompt-status">
            {#if p.is_modified}
              <span class="modified-badge" title="Content differs from shipped default">!modified</span>
            {:else if p.exists}
              <span class="default-badge">default</span>
            {:else}
              <span class="missing-badge">not created</span>
            {/if}
          </div>
          <div class="prompt-actions">
            <button class="btn btn-view" onclick={() => handleView(p.name)} title="View content">View</button>
            <button class="btn btn-edit" onclick={() => startEdit(p)} title="Edit content">Edit</button>
            <button class="btn btn-reset" onclick={() => handleReset(p.name)} title="Reset to default">
              Reset
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}

  {#if editingName !== null}
    <!-- Edit dialog overlay -->
    <div class="edit-overlay" onclick={cancelEdit} role="dialog" aria-modal="true" aria-label="Edit prompt">
      <div class="edit-dialog" onclick={(e) => e.stopPropagation()}>
        <div class="edit-header">
          <h3>Edit: {editingName}</h3>
          <button class="btn-close" onclick={cancelEdit}>✕</button>
        </div>
        <textarea
          class="edit-textarea"
          bind:value={editingContent}
          rows="20"
          spellcheck="false"
        ></textarea>
        <div class="edit-actions">
          <button class="btn btn-save" onclick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button class="btn btn-cancel" onclick={cancelEdit}>Cancel</button>
          <button class="btn btn-reset" onclick={() => { editingContent = editingDefault; }} title="Restore default">
            Restore Default
          </button>
        </div>
      </div>
    </div>
  {/if}

  <div class="footer-hint">
    <p>Prompt files are stored in your config directory. Changes take effect immediately — no restart needed.</p>
  </div>
</div>

<style>
  .prompt-list-tab { padding: 1rem; }
  .list-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 1rem;
  }
  .list-header h3 { margin: 0; font-size: 1rem; color: #e0e0e0; }
  .header-actions { display: flex; align-items: center; gap: 0.75rem; }
  .badge {
    font-size: 0.78rem; color: #82829a; background: #1e1e30;
    padding: 2px 8px; border-radius: 8px;
  }
  .badge.has-modified { color: #dbdb8f; background: #2a2a1e; }

  .loading, .error, .empty { color: #82829a; font-size: 0.85rem; padding: 1rem; text-align: center; }
  .error { color: #d45; }

  .prompt-table { display: flex; flex-direction: column; gap: 2px; }
  .prompt-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.6rem 0.75rem;
    background: #1a1a28;
    border-radius: 4px;
    gap: 1rem;
  }
  .prompt-row.row-modified { border-left: 3px solid #dbdb8f; }
  .prompt-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
  .prompt-name { font-size: 0.9rem; color: #e0e0e0; font-weight: 500; }
  .prompt-category { font-size: 0.72rem; color: #6a6a8a; }
  .prompt-path { font-size: 0.7rem; color: #5a5a7a; font-family: monospace; }
  .prompt-status { flex-shrink: 0; }
  .modified-badge { font-size: 0.72rem; color: #dbdb8f; background: #2a2a1e; padding: 1px 6px; border-radius: 4px; font-weight: 600; }
  .default-badge { font-size: 0.72rem; color: #6a9a6a; }
  .missing-badge { font-size: 0.72rem; color: #6a6a6a; }
  .prompt-actions { display: flex; gap: 0.4rem; flex-shrink: 0; }

  .btn {
    padding: 0.25rem 0.6rem; border: 1px solid #444; border-radius: 4px;
    background: #2a2a3e; color: #e0e0e0; cursor: pointer;
    font-size: 0.75rem; white-space: nowrap;
  }
  .btn:hover { background: #3a3a5a; }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-view { background: #2a2a3e; border-color: #555; }
  .btn-edit { background: #2a3a4a; border-color: #3a6a8a; }
  .btn-reset { background: #3a2a2a; border-color: #7a3a3a; }
  .btn-reset-all { background: #3a3a1e; border-color: #7a7a3a; font-size: 0.72rem; }
  .btn-save { background: #2a4a3a; border-color: #3a7a4a; }
  .btn-cancel { background: #3a3a3a; border-color: #555; }
  .btn-close { background: none; border: none; color: #888; cursor: pointer; font-size: 1rem; }
  .btn-close:hover { color: #e0e0e0; }

  .footer-hint { margin-top: 1rem; }
  .footer-hint p { font-size: 0.72rem; color: #5a5a7a; text-align: center; }

  /* Edit dialog */
  .edit-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center; z-index: 100;
  }
  .edit-dialog {
    background: #1e1e32; border: 1px solid #444; border-radius: 8px;
    padding: 1rem; width: 90%; max-width: 700px;
    max-height: 85vh; display: flex; flex-direction: column;
  }
  .edit-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 0.5rem;
  }
  .edit-header h3 { margin: 0; font-size: 0.95rem; color: #e0e0e0; }
  .edit-textarea {
    flex: 1; min-height: 300px;
    background: #111; color: #a0d0a0; border: 1px solid #333; border-radius: 4px;
    padding: 0.75rem; font-family: monospace; font-size: 0.8rem;
    resize: vertical; outline: none; line-height: 1.5;
  }
  .edit-textarea:focus { border-color: #5a5a8a; }
  .edit-actions {
    display: flex; gap: 0.5rem; justify-content: flex-end;
    margin-top: 0.75rem;
  }
</style>
