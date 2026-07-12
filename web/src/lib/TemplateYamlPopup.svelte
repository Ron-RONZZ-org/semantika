<script>
  /**
   * Fallback popup showing generated template YAML.
   *
   * The primary /template flow now uses tool-calling + HITL to save
   * templates via `!template save`. This popup is only shown when
   * tool-calling is unavailable (e.g. LLM provider doesn't support it)
   * and the user must save the YAML manually.
   *
   * Props:
   *   data.yaml         — the YAML content
   *   data.description  — user's description (for re-generation)
   */
  let { data = {} } = $props();
  let yaml = $derived(data?.yaml || "");
  let description = $derived(data?.description || "");
  let saving = $state(false);
  let saved = $state(false);
  let saveError = $state("");

  async function handleSave() {
    saving = true;
    saveError = "";
    try {
      const resp = await fetch("/api/v1/triple-templates/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml }),
      });
      const result = await resp.json();
      if (!resp.ok) {
        const msg = result.detail || `HTTP ${resp.status}`;
        throw new Error(msg);
      }
      saved = true;
    } catch (err) {
      saveError = err.message || String(err);
    } finally {
      saving = false;
    }
  }
</script>

<div class="template-yaml-popup">
  <div class="yaml-header">
    <h3>Generated Template (fallback)</h3>
    <div class="actions">
      {#if saved}
        <span class="saved-badge">Saved</span>
      {:else}
        <button class="btn btn-save" onclick={handleSave} disabled={saving}>
          {saving ? "Saving\u2026" : "Save Manually"}
        </button>
      {/if}
    </div>
  </div>

  {#if saveError}
    <p class="error-msg">Save failed: {saveError}</p>
  {/if}

  {#if saved}
    <p class="success-msg">Template saved! Use <code>!template use &#x200b;{extractName(yaml)}</code> to apply it.</p>
  {:else}
    <p class="hint">
      The LLM could not use tools to save this template automatically.
      Review the YAML below and click <strong>Save Manually</strong> to persist it,
      or run <code>/template</code> again with a different LLM provider that supports tool-calling.
    </p>
  {/if}

  <pre class="yaml-block"><code>{yaml}</code></pre>
</div>

<script module>
  function extractName(yaml) {
    const match = yaml.match(/^name:\s*(\S+)/m);
    return match ? match[1] : "template-name";
  }
</script>

<style>
  .template-yaml-popup { padding: 1rem; }
  .yaml-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 0.75rem;
  }
  .yaml-header h3 { margin: 0; font-size: 1rem; color: #e0e0e0; }
  .actions { display: flex; gap: 0.5rem; }
  .btn {
    padding: 0.35rem 0.8rem; border: none; border-radius: 4px;
    cursor: pointer; font-size: 0.8rem; transition: background 0.1s;
  }
  .btn:disabled { opacity: 0.5; }
  .btn-save {
    background: #3a6a3a; color: #e0e0e0;
  }
  .btn-save:hover:not(:disabled) { background: #4a8a4a; }
  .saved-badge { color: #4a8a4a; font-weight: bold; font-size: 0.85rem; }
  .hint { font-size: 0.78rem; color: #82829a; margin: 0 0 0.75rem; }
  .hint code { background: #222; padding: 1px 4px; border-radius: 3px; }
  .success-msg { color: #4a8a4a; font-size: 0.85rem; margin-bottom: 0.75rem; }
  .success-msg code { background: #222; padding: 1px 4px; border-radius: 3px; }
  .error-msg { color: #d45; font-size: 0.8rem; margin-bottom: 0.5rem; }
  .yaml-block {
    background: #111; color: #a0d0a0; padding: 1rem; border-radius: 6px;
    overflow-x: auto; font-size: 0.78rem; line-height: 1.5;
    max-height: 400px; overflow-y: auto;
  }
  .yaml-block code { font-family: monospace; white-space: pre; }
</style>
