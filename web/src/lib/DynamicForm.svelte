<script>
  import { findNode } from "./commandTree.js";
  import FormField from "./FormField.svelte";

  let { commandPath = [], initialData = {}, onsubmit = async () => {} } = $props();

  let node = $derived(findNode(commandPath));
  let params = $derived(node?.params || []);
  let flags = $derived(node?.flags || []);
  let submitting = $state(false);
  let formErrors = $state({});
  let fieldValues = $state({});

  // Track which option in each group is active
  let activeGroup = $state({});

  $effect(() => {
    const vals = { ...initialData };
    for (const p of params) { if (!(p.name in vals)) vals[p.name] = ""; }
    for (const f of flags) {
      if (f.type === "flag") vals[f.name] = initialData[f.name] || false;
      else if (!(f.name in vals)) vals[f.name] = "";
    }
    fieldValues = vals;

    // Set initial active group members
    const groups = {};
    for (const f of flags) {
      if (f.group) {
        if (!groups[f.group]) groups[f.group] = f.name;
        // If initial data has a value for this group member, prefer it
        if (initialData[f.name]) groups[f.group] = f.name;
      }
    }
    activeGroup = groups;
  });

  function setField(name, val) {
    fieldValues = { ...fieldValues, [name]: val };
    if (formErrors[name]) { const next = { ...formErrors }; delete next[name]; formErrors = next; }
  }

  function setActiveGroup(group, name) {
    // Clear other values in this group
    const next = { ...fieldValues };
    for (const f of flags) {
      if (f.group === group && f.name !== name) {
        next[f.name] = f.type === "flag" ? false : "";
      }
    }
    fieldValues = next;
    activeGroup = { ...activeGroup, [group]: name };
  }

  function isSensitive(name) { return /password|secret|key|token/i.test(name); }

  function fieldType(flagDef) {
    if (flagDef.type === "number") return "number";
    if (flagDef.type === "date") return "date";
    if (flagDef.type === "flag") return "checkbox";
    if (flagDef.type === "code") return "textarea";
    if (isSensitive(flagDef.name)) return "password";
    return "text";
  }

  /** Collect grouped fields — each group gets rendered as a toggle, non-grouped fields render inline. */
  let groupedFlags = $derived.by(() => {
    const groups = {};
    const standalone = [];
    for (const f of flags) {
      if (f.group) {
        if (!groups[f.group]) groups[f.group] = [];
        groups[f.group].push(f);
      } else {
        standalone.push(f);
      }
    }
    return { groups, standalone };
  });

  /** Determine if a group has a toggle (multiple members) or is a single optional field. */
  let hasRequired = $derived(params.some(p => p.required));

  /** Preview: open rendered code in a popup overlay */
  let previewContent = $state("");
  let previewLanguage = $state("");
  let showPreview = $state(false);

  function openPreview() {
    const code = fieldValues["code"] || "";
    const lang = fieldValues["lang"] || "";
    if (!code.trim()) return;
    previewContent = code;
    previewLanguage = lang;
    showPreview = true;
  }

  function closePreview() {
    showPreview = false;
    previewContent = "";
    previewLanguage = "";
  }

  // Global keyboard shortcut: Ctrl+Shift+P or Cmd+Shift+P for preview
  function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "P") {
      // Only if the code field has content
      if (fieldValues["code"] && fieldValues["code"].trim()) {
        e.preventDefault();
        openPreview();
      }
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errors = {}; const flags_out = {}; let remaining = [];
    for (let i = 0; i < params.length; i++) {
      const val = (fieldValues[params[i].name] || "").trim();
      if (params[i].required && !val) errors[params[i].name] = `${params[i].name} is required`;
      remaining.push(val);
    }
    for (const f of flags) {
      let val = fieldValues[f.name];
      if (f.type === "flag") { if (val) flags_out[f.name] = "true"; }
      else if (val && val !== "") flags_out[f.name] = val;
    }
    formErrors = errors;
    if (Object.keys(errors).length > 0) return;
    submitting = true;
    try { await onsubmit({ tokens: commandPath, flags: flags_out, remaining }); }
    finally { submitting = false; }
  }

</script>

<svelte:window onkeydown={handleKeydown} />

<form onsubmit={handleSubmit} class="dynamic-form">
  {#if params.length > 0}
    <div class="section-label required-section">Required</div>
    {#each params as p}
      <FormField label={p.name} hint={p.help || p.placeholder || ""} required={true} error={formErrors[p.name]}>
        {#if p.type === "flag"}
          <label class="checkbox-label">
            <input type="checkbox" checked={fieldValues[p.name] || false}
              onchange={(e) => setField(p.name, e.target.checked)} disabled={submitting} />
            {p.help || p.name}
          </label>
        {:else if p.type === "code"}
          <textarea id={p.name} value={fieldValues[p.name] || ""}
            oninput={(e) => setField(p.name, e.target.value)}
            disabled={submitting} placeholder={p.placeholder || ""}
            rows="10" class="code-textarea"></textarea>
        {:else if p.suggestions && p.suggestions.length > 0}
          <input type={fieldType(p)} id={p.name} value={fieldValues[p.name] || ""}
            oninput={(e) => setField(p.name, e.target.value)}
            disabled={submitting} placeholder={p.placeholder || ""} list={p.name + "-list"} />
          <datalist id={p.name + "-list"}>
            {#each p.suggestions as s}
              <option value={s} />
            {/each}
          </datalist>
        {:else}
          <input type={fieldType(p)} id={p.name} value={fieldValues[p.name] || ""}
            oninput={(e) => setField(p.name, e.target.value)}
            disabled={submitting} placeholder={p.placeholder || ""} />
        {/if}
      </FormField>
    {/each}
  {/if}

  {#if flags.length > 0}
    <div class="section-label optional-section">Optional</div>

    {#each Object.entries(groupedFlags.groups) as [groupName, members]}
      <div class="field-group">
        <div class="group-toggle">
          {#each members as m}
            <button type="button" class="toggle-btn"
              class:active={activeGroup[groupName] === m.name}
              onclick={() => setActiveGroup(groupName, m.name)}>
              {m.help || m.name}
            </button>
          {/each}
        </div>
        {#each members as m}
          {#if activeGroup[groupName] === m.name}
            <FormField label={m.name} hint={m.help || m.placeholder || ""}>
              {#if m.type === "flag"}
                <label class="checkbox-label">
                  <input type="checkbox" checked={fieldValues[m.name] || false}
                    onchange={(e) => setField(m.name, e.target.checked)} disabled={submitting} />
                  {m.help || m.name}
                </label>
              {:else if m.type === "code"}
                <textarea id={m.name} value={fieldValues[m.name] || ""}
                  oninput={(e) => setField(m.name, e.target.value)}
                  disabled={submitting} placeholder={m.placeholder || ""}
                  rows="10" class="code-textarea"></textarea>
                {#if fieldValues[m.name] && fieldValues[m.name].trim()}
                  <button type="button" class="preview-btn" onclick={openPreview}>
                    &#9654; Preview (Ctrl+Shift+P)
                  </button>
                {/if}
              {:else if m.suggestions && m.suggestions.length > 0}
                <input type={fieldType(m)} id={m.name} value={fieldValues[m.name] || ""}
                  oninput={(e) => setField(m.name, e.target.value)}
                  disabled={submitting} placeholder={m.placeholder || ""} list={m.name + "-list"} />
                <datalist id={m.name + "-list"}>
                  {#each m.suggestions as s}
                    <option value={s} />
                  {/each}
                </datalist>
              {:else}
                <input type={fieldType(m)} id={m.name} value={fieldValues[m.name] || ""}
                  oninput={(e) => setField(m.name, e.target.value)}
                  disabled={submitting} placeholder={m.placeholder || ""} />
              {/if}
            </FormField>
          {/if}
        {/each}
      </div>
    {/each}

    {#each groupedFlags.standalone as f}
      <FormField label={f.name} hint={f.help || f.placeholder || ""} error={formErrors[f.name]}>
        {#if f.type === "flag"}
          <label class="checkbox-label">
            <input type="checkbox" checked={fieldValues[f.name] || false}
              onchange={(e) => setField(f.name, e.target.checked)} disabled={submitting} />
            {f.help || f.name}
          </label>
        {:else if f.type === "code"}
          <textarea id={f.name} value={fieldValues[f.name] || ""}
            oninput={(e) => setField(f.name, e.target.value)}
            disabled={submitting} placeholder={f.placeholder || ""}
            rows="10" class="code-textarea"></textarea>
        {:else if f.suggestions && f.suggestions.length > 0}
          <input type={fieldType(f)} id={f.name} value={fieldValues[f.name] || ""}
            oninput={(e) => setField(f.name, e.target.value)}
            disabled={submitting} placeholder={f.placeholder || ""} list={f.name + "-list"} />
          <datalist id={f.name + "-list"}>
            {#each f.suggestions as s}
              <option value={s} />
            {/each}
          </datalist>
        {:else}
          <input type={fieldType(f)} id={f.name} value={fieldValues[f.name] || ""}
            oninput={(e) => setField(f.name, e.target.value)}
            disabled={submitting} placeholder={f.placeholder || ""} />
        {/if}
      </FormField>
    {/each}
  {/if}

  <div class="form-actions">
    <button type="submit" disabled={submitting}>{submitting ? "Saving\u2026" : "Save"}</button>
  </div>
</form>

<!-- Code Preview Modal -->
{#if showPreview}
  <div class="preview-overlay" onclick={closePreview} role="presentation">
    <div class="preview-dialog" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Code Preview">
      <div class="preview-header">
        <span class="preview-title">Code Preview {previewLanguage ? `(${previewLanguage})` : ""}</span>
        <button type="button" class="preview-close" onclick={closePreview}>&#x2715;</button>
      </div>
      <pre class="preview-code"><code>{previewContent}</code></pre>
    </div>
  </div>
{/if}

<style>
  .dynamic-form { display: flex; flex-direction: column; gap: 0.75rem; padding: 1rem; }

  .section-label { font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; padding: 0.25rem 0; margin-top: 0.25rem; }
  .required-section { color: #c44; }
  .optional-section { color: #7c7c9a; }

  .field-group { display: flex; flex-direction: column; gap: 0.5rem;
    padding: 0.5rem; border: 1px solid #3a3a4e; border-radius: 6px; }

  .group-toggle { display: flex; gap: 0.25rem; }
  .toggle-btn { padding: 0.3rem 0.75rem; border: 1px solid #444; border-radius: 4px;
    background: #2a2a3e; color: #9a9aba; cursor: pointer; font-size: 0.78rem;
    font-family: monospace; transition: all 0.1s; }
  .toggle-btn:hover { border-color: #7c7c9a; color: #e0e0e0; }
  .toggle-btn.active { background: #3a5a7a; border-color: #5a8aba; color: #e0e0e0; }

  .checkbox-label { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; font-size: 0.9rem; color: #e0e0e0; }

  .code-textarea { width: 100%; padding: 0.5rem; border: 1px solid #444; border-radius: 4px;
    font-size: 0.82rem; background: #1a1a2e; color: #e0e0e0; outline: none;
    font-family: monospace; line-height: 1.4; resize: vertical; box-sizing: border-box; }
  .code-textarea:focus { border-color: #7c7c9a; }

  .preview-btn { padding: 0.3rem 0.75rem; border: 1px solid #5a8aba; border-radius: 4px;
    background: #2a3a5e; color: #8aba; cursor: pointer; font-size: 0.75rem;
    font-family: monospace; align-self: flex-start; transition: background 0.1s; }
  .preview-btn:hover { background: #3a5a7a; }

  .form-actions { display: flex; gap: 0.5rem; padding-top: 0.5rem; }
  .form-actions button { padding: 0.4rem 1rem; background: #3a6a3a; color: #e0e0e0;
    border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
  .form-actions button:hover { background: #4a8a4a; }
  .form-actions button:disabled { opacity: 0.5; }

  /* Preview modal */
  .preview-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7);
    display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .preview-dialog { background: #1a1a2e; border: 1px solid #444; border-radius: 10px;
    max-width: 80vw; max-height: 80vh; display: flex; flex-direction: column; overflow: hidden; }
  .preview-header { display: flex; align-items: center; justify-content: space-between;
    padding: 0.5rem 1rem; border-bottom: 1px solid #333; }
  .preview-title { font-size: 0.85rem; color: #e0e0e0; font-family: monospace; }
  .preview-close { background: none; border: none; color: #9a9aba; cursor: pointer;
    font-size: 1.1rem; padding: 0.25rem; }
  .preview-close:hover { color: #e0e0e0; }
  .preview-code { margin: 0; padding: 1rem; overflow: auto; font-size: 0.82rem;
    line-height: 1.5; color: #e0e0e0; font-family: monospace;
    white-space: pre-wrap; word-break: break-word; }

  :global(.dynamic-form input[type="text"]),
  :global(.dynamic-form input[type="number"]),
  :global(.dynamic-form input[type="password"]),
  :global(.dynamic-form input[type="date"]) {
    padding: 0.4rem 0.6rem; border: 1px solid #444; border-radius: 4px; font-size: 0.85rem;
    background: #2a2a3e; color: #e0e0e0; outline: none;
  }
  :global(.dynamic-form input:focus) {
    border-color: #7c7c9a;
  }
</style>
